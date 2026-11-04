import unittest
from unittest.mock import Mock
from publisher_app.platforms.liaoshangbao_monitor import LiaoshangbaoMonitorClient
from publisher_app.platforms.liaoshangbao_monitor_adapter import LiaoshangbaoMonitorAdapter
from unittest.mock import patch


class FollowingTests(unittest.TestCase):
    def test_unified_adapter_following_and_article_mapping(self):
        client = LiaoshangbaoMonitorAdapter(dict(uid='123',sid='test',cookies={'session':'cookie'}))
        self.assertEqual(client.user_id,'123')
        self.assertEqual(client.session.cookies.get('session'),'cookie')
        with patch.object(client,'following_records',return_value=[dict(user_id='789',s_user_id='encoded',name='商家')]):
            self.assertEqual(client.following(),{'encoded':'商家'})
        with patch.object(LiaoshangbaoMonitorClient,'latest',return_value=[dict(id=20,s_id='articlecode',title='完整标题🔥',short_msg='副标题',price=20,all_zk=8,on_seld_top=1,create_time='2026-11-04 18:00:00')]):
            row = client.latest('encoded')[0]
        self.assertEqual(row['planId'],'20')
        self.assertEqual(row['planTitle'],'完整标题🔥')
        self.assertEqual(row['planSubtitle'],'副标题')
        self.assertEqual(row['priceReal'],'16.00')
        self.assertTrue(row['top'])
        self.assertEqual(row['s_id'],'articlecode')

    def test_initial_100_and_later_only_new_ids(self):
        client = LiaoshangbaoMonitorClient(uid='user',sid='test')
        old_pin = dict(id=0,on_seld_top=1,create_time='2020-01-01 00:00:00')
        rows = [dict(id=i,on_seld_top=0,create_time='2026-11-04 10:{:02d}:00'.format(i%60)) for i in range(1,101)]
        client.article_page = Mock(side_effect=lambda soid,index: ([old_pin]+rows[:60],3) if index==1 else (rows[60:],3))
        initial,fresh,baseline = client.poll_articles('shop')
        self.assertTrue(baseline)
        self.assertEqual(len(initial),100)
        self.assertNotIn(0,[row['id'] for row in initial])
        self.assertEqual(fresh,[])
        self.assertEqual(client.article_page.call_count,2)
        client.article_page = Mock(return_value=([dict(id=999,on_seld_top=0,create_time='2026-11-04 12:00:00')]+rows,1))
        _,fresh,baseline = client.poll_articles('shop')
        self.assertFalse(baseline)
        self.assertEqual([row['id'] for row in fresh],[999])
        self.assertEqual(client.poll_articles('shop')[1],[])

    def test_articles_use_encoded_merchant_id_and_sort_by_time(self):
        client = LiaoshangbaoMonitorClient(uid='user',sid='test')
        result = dict(status=200,success=False,msg='1',data=[
            dict(id=1,s_id='encoded1',title='旧置顶文章',create_time='2026-11-03 12:00:00',on_seld_top=1),
            dict(id=2,s_id='encoded2',title='新文章',create_time='2026-11-04 12:00:00')])
        client.session.get = Mock(return_value=Mock(json=Mock(return_value=result)))
        rows = client.latest('merchant-encoded')
        self.assertEqual([row['id'] for row in rows],[2,1])
        self.assertEqual(client.session.get.call_args.kwargs['params']['soid'],'merchant-encoded')

    def test_pagination_status_and_ids(self):
        client = LiaoshangbaoMonitorClient(uid='user',sid='test')
        pages = [dict(status=200,success=False,data=dict(lists=[dict(user_id=1,s_user_id='encoded1',name='同名')],maxPage=2)),
                 dict(status=200,success=False,data=dict(lists=[dict(user_id=2,s_user_id='encoded2',name='同名')],maxPage=2))]
        responses = [Mock(json=Mock(return_value=page)) for page in pages]
        client.session.get = Mock(side_effect=responses)
        records = client.following_records()
        self.assertEqual([row['user_id'] for row in records],['1','2'])
        self.assertEqual(records[1]['s_user_id'],'encoded2')
        self.assertEqual(client.session.get.call_args.kwargs['params']['index'],2)

    def test_failed_status_not_success_flag(self):
        client = LiaoshangbaoMonitorClient(uid='user',sid='test')
        client.session.get = Mock(return_value=Mock(json=Mock(return_value=dict(status=403,success=True,msg='登录失效'))))
        with self.assertRaises(RuntimeError): client.following_records()


if __name__ == '__main__': unittest.main()
