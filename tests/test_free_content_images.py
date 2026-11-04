import unittest
from unittest.mock import Mock

from publisher_app.platforms.liaoxiaobao import LiaoxiaobaoPlatform


class FreeImagesTests(unittest.TestCase):
    def test_free_and_paid_uploads_stay_separate_including_presale(self):
        for presale in (True, False):
            with self.subTest(presale=presale):
                platform = LiaoxiaobaoPlatform.__new__(LiaoxiaobaoPlatform)
                platform._upload = Mock(side_effect=lambda paths, category: [category + '/' + path for path in paths])
                platform._send = Mock(return_value='article-id')
                article = dict(title='标题', summary='简介', price=20, presale=presale,
                               free_content='免费文字', content='付费文字', tags=[], discount_enabled=True)
                platform.publish(article, ['paid.jpg'], free_images=['free1.jpg','free2.jpg'])
                payload = platform._send.call_args.args[1]
                self.assertEqual(payload['freeImages'], ['ARTICLE_FREE/free1.jpg','ARTICLE_FREE/free2.jpg'])
                if presale:
                    self.assertNotIn('paidImages',payload)
                else:
                    self.assertEqual(payload['paidImages'], ['ARTICLE_PAID/paid.jpg'])


if __name__ == '__main__':
    unittest.main()
