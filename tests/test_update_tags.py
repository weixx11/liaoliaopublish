import unittest
from unittest.mock import Mock

from publisher_app.platforms.yiliao import YiliaoPlatform
from publisher_app.platforms.liaoshangbao import LiaoshangbaoPlatform
from publisher_app.platforms.liaoxiaobao import LiaoxiaobaoPlatform


class UpdateTagsTests(unittest.TestCase):
    def test_yiliao_empty_free_content_does_not_overwrite_original(self):
        platform = YiliaoPlatform.__new__(YiliaoPlatform)
        platform.user = {'expertId':'expert'}
        platform._post = Mock(return_value={})
        for extra in ({},{'summary':'','free_content':''},{'summary':'  ','free_content':None}):
            platform._post.reset_mock()
            platform.update('123',dict(content='追加付费内容',**extra))
            fields = platform._post.call_args_list[0].args[1]
            self.assertNotIn('summary',fields)
            self.assertNotIn('freeContent',fields)
            self.assertEqual(platform._post.call_args_list[1].args,('sync_update',{'planId':'123'}))

    def test_subtitle_is_preserved_or_explicitly_updated(self):
        yiliao = YiliaoPlatform.__new__(YiliaoPlatform)
        yiliao.user = {'expertId':'expert'}
        yiliao._post = Mock(return_value={})
        lsb = LiaoshangbaoPlatform(uid='user',sid='session')
        lsb._post_multipart = Mock(return_value={'status':200})
        for extra in ({},{'subtitle':'原副标题'}):
            article = dict(title='标题',content='追加',summary='免费内容',price='20',**extra)
            yiliao.update('123',article)
            fields = yiliao._post.call_args_list[-2].args[1]
            self.assertEqual(fields.get('title2'),extra.get('subtitle'))
            if not extra: self.assertNotIn('title2',fields)
            lsb.update('id',article)
            subtitles = [value for key,value in lsb._post_multipart.call_args.args[1] if key in ('shortMsg','shortmsg')]
            self.assertEqual(subtitles,['原副标题']*2 if extra else [])

    def test_yiliao_omits_unknown_tags_and_sends_explicit_tags(self):
        platform = YiliaoPlatform.__new__(YiliaoPlatform)
        platform.user = {'expertId':'expert'}
        platform._post = Mock(return_value={})
        for extra in ({}, {'tags':'足球,篮球'}):
            platform._post.reset_mock()
            platform.update('123',dict(content='追加',**extra))
            fields = platform._post.call_args_list[0].args[1]
            self.assertEqual(fields.get('tags'),extra.get('tags'))
            if not extra: self.assertNotIn('tags',fields)

    def test_lsb_does_not_clear_label_when_unspecified(self):
        platform = LiaoshangbaoPlatform(uid='user',sid='session')
        platform._post_multipart = Mock(return_value={'status':200})
        for extra in ({}, {'label':'足球'}):
            platform.update('id',dict(title='标题',content='追加',price='20',**extra))
            labels = [value for key,value in platform._post_multipart.call_args.args[1] if key=='showLabel']
            self.assertEqual(labels, ['足球','足球'] if extra else [])

    def test_lxb_omits_unspecified_tags_and_normalizes_changes(self):
        platform = LiaoxiaobaoPlatform.__new__(LiaoxiaobaoPlatform)
        platform._upload = Mock(return_value=[])
        platform._send = Mock(return_value={})
        platform.update('id',dict(content='追加'))
        self.assertNotIn('tags',platform._send.call_args.args[1])
        platform.update('id',dict(content='追加',tags='足球，篮球'))
        self.assertEqual(platform._send.call_args.args[1]['tags'],['足球','篮球'])
        platform.update('id',dict(content='追加',title='新标题',summary='副标题'))
        payload = platform._send.call_args.args[1]
        self.assertEqual(payload['title'],'新标题')
        self.assertEqual(payload['summary'],'副标题')


if __name__ == '__main__':
    unittest.main()
