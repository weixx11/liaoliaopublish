import unittest
from unittest.mock import Mock
from publisher_app.platforms.liaoxiaobao_monitor import LiaoxiaobaoMonitorClient
from publisher_app.platforms.liaoxiaobao_monitor_adapter import LiaoxiaobaoMonitorAdapter
from unittest.mock import patch


class LatestPublicationTests(unittest.TestCase):
    def test_monitor_login_does_not_save_publisher_session(self):
        client=LiaoxiaobaoMonitorAdapter()
        client._login_credentials=Mock(return_value=dict(token='monitor-token',secret='key',iv='iv'))
        client._send=Mock(return_value=dict(userId=7,nickname='用户'))
        with patch('publisher_app.platforms.liaoxiaobao.save_session') as publish_save:
            saved=client.login('phone','password')
        publish_save.assert_not_called()
        self.assertEqual(saved['purpose'],'user_monitor')
        self.assertEqual(saved['user_id'],'7')

    def test_unified_adapter_fields_and_following(self):
        client = LiaoxiaobaoMonitorAdapter(dict(token='test',secret='key',iv='iv',user_id='123'))
        self.assertEqual(client.user_id,'123')
        with patch.object(client,'following_records',return_value=[dict(authorId=9,authorNickname='原名',authorRemarkName='备注')]):
            self.assertEqual(client.following(),{'9':'备注'})
        row = dict(articleNo='no1',publishTime='2026-11-04 19:00:00',title='完整标题🔥',summary='副标题',originalPrice=20,discountPrice=0,isPinned=True)
        with patch.object(LiaoxiaobaoMonitorClient,'latest',return_value=[row]):
            actual = client.latest('9')[0]
        self.assertEqual(actual['planId'],'no1')
        self.assertEqual(actual['planPublicTime'],row['publishTime'])
        self.assertEqual(actual['planTitle'],row['title'])
        self.assertEqual(actual['planSubtitle'],'副标题')
        self.assertEqual(actual['priceReal'],0)
        self.assertTrue(actual['top'])

    def client(self):
        return LiaoxiaobaoMonitorClient.__new__(LiaoxiaobaoMonitorClient)

    @staticmethod
    def row(number,**extra):
        return dict(articleNo=str(number),authorId='author',title=str(number),
                    publishTime=f'2026-11-04 {number//3600:02d}:{number//60%60:02d}:{number%60:02d}',
                    isListed=True,status=1,**extra)

    def test_later_page_newer_articles_are_in_top100(self):
        client = self.client()
        pages = [([self.row(i) for i in range(100)],2),([self.row(i) for i in range(100,120)],2)]
        client._records = Mock(side_effect=pages)
        rows = client.latest('author')
        self.assertEqual(len(rows),100)
        self.assertEqual(rows[0]['articleNo'],'119')
        self.assertEqual(rows[-1]['articleNo'],'20')
        self.assertEqual(client._records.call_count,2)

    def test_baseline_no_duplicates_and_failed_poll_keeps_seen(self):
        client = self.client()
        client._records = Mock(return_value=([self.row(1)],1))
        self.assertEqual(client.poll_articles('author')[1],[])
        self.assertEqual(client.poll_articles('author')[1],[])
        client._records = Mock(side_effect=RuntimeError('temporary'))
        with self.assertRaises(RuntimeError): client.poll_articles('author')
        client._records = Mock(return_value=([self.row(2),self.row(1)],1))
        self.assertEqual([row['articleNo'] for row in client.poll_articles('author')[1]],['2'])

    def test_wrong_author_rejected_and_unlisted_filtered(self):
        client = self.client()
        wrong = self.row(1); wrong['authorId']='wrong'
        client._records = Mock(return_value=([wrong],1))
        with self.assertRaises(ValueError): client.latest('author')
        unlisted = self.row(2); unlisted['isListed']=False
        client._records = Mock(return_value=([unlisted,self.row(1)],1))
        self.assertEqual(len(client.latest('author')),1)


if __name__ == '__main__': unittest.main()
