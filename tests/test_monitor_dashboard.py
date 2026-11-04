"""Offline widget checks: no credentials, network, or article writes."""
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from publisher_app.monitor_dashboard import MonitorView


class MonitorDashboardTests(unittest.TestCase):
    def test_subtitle_display_search_copy_and_refresh_without_new_post(self):
        self.view._accept_cycle(([(self.account,{'expert':'商家'})],[],[]))
        key=(self.account,'expert'); snapshot=dict(self.view.tasks[key])
        row=dict(planId=1,planTitle='主标题🔥',planSubtitle='副标题🏀',planPublicTime='2026-11-04 12:00:00')
        self.view._accept_cycle(([],[(key,snapshot,[row])],[]))
        article_key=('壹料','expert','1')
        self.assertEqual(self.view.feed[article_key][3],'主标题🔥 | 副标题🏀')
        self.view.keyword.set('副标题🏀')
        item=self.view.articles.get_children()[0]
        self.view.articles.selection_set(item)
        with patch.object(self.view,'clipboard_clear'),patch.object(self.view,'clipboard_append') as append:
            self.view._copy_titles()
        append.assert_called_once_with('主标题🔥 | 副标题🏀')
        row['planSubtitle']='更新副标题'
        self.view._accept_cycle(([],[(key,snapshot,[row])],[]))
        self.assertEqual(len(self.view.feed),1)
        self.assertEqual(self.view.feed[article_key][3],'主标题🔥 | 更新副标题')
        self.assertIn('新增 0 篇',self.view.logs.get('1.0','end'))
        row['planSubtitle']=''
        self.view._accept_cycle(([],[(key,snapshot,[row])],[]))
        self.assertEqual(self.view.feed[article_key][3],'主标题🔥')

    def test_merchant_search_filters_articles_tasks_and_bulk_scope(self):
        account=self.account
        self.view._accept_cycle(([(account,{'expert1':'足球商家','expert2':'篮球商家'})],[],[]))
        self.view.feed={('壹料','expert1','1'):('壹料','足球商家','2026-11-04 12:00:00','同一标题',10,10,''),
                        ('红料','expert3','2'):('红料','足球商家','2026-11-04 13:00:00','同一标题',20,20,'')}
        self.view.merchant_query.set('足球')
        self.assertEqual(len(self.view.merchants.get_children()),1)
        self.assertEqual(len(self.view.articles.get_children()),2)
        self.view._check_all_tasks(True)
        self.assertEqual(self.view._checked_keys(),[(account,'expert1')])
        self.assertTrue(self.view.tasks[(account,'expert2')]['enabled'])
        self.view.merchant_query.set('expert3')
        self.assertEqual(len(self.view.articles.get_children()),1)
        self.assertEqual(self.view.articles.item(self.view.articles.get_children()[0],'values')[0],'红料')
        self.view.merchant_query.set('没有此商家')
        self.assertEqual(len(self.view.articles.get_children()),0)
        self.view.merchant_query.set('')
        self.assertEqual(len(self.view.merchants.get_children()),2)
        self.assertEqual(len(self.view.articles.get_children()),2)

    def test_lxb_session_registration_and_restore(self):
        from publisher_app.platforms.liaoxiaobao_monitor_adapter import LiaoxiaobaoMonitorAdapter
        credentials = dict(token='test',secret='key',iv='iv',cookies={},platform='料小宝',purpose='user_monitor',user_id='123',name='料小宝用户')
        client = LiaoxiaobaoMonitorAdapter(credentials)
        client.login = Mock(return_value=credentials)
        self.view.lxb_monitor_phone = Mock(); self.view.lxb_monitor_phone.get.return_value='monitor-user'
        self.view.lxb_monitor_password = Mock(); self.view.lxb_monitor_password.get.return_value='password'
        with patch('publisher_app.monitor_dashboard.LiaoxiaobaoMonitorAdapter',return_value=client), patch('publisher_app.monitor_dashboard.save_session') as save, patch.object(self.view,'_submit',side_effect=lambda title,work,done:done(work())):
            self.view._login_lxb_monitor()
        key = '料小宝:123'
        self.assertIn(key,self.view.clients)
        self.assertEqual(self.view.account_data[key]['name'],'料小宝用户')
        saved = save.call_args.args[1]
        with patch('publisher_app.monitor_dashboard.load_session',side_effect=lambda name:saved if name=='H5监控账号' else {}),patch('publisher_app.monitor_dashboard.load_articles',return_value={}):
            restored = MonitorView(self.root)
        try:
            self.assertIn(key,restored.clients)
            self.assertEqual(restored.clients[key].user_id,'123')
        finally: restored.destroy()

    def test_legacy_copied_publisher_lxb_session_not_restored(self):
        saved = {'料小宝:123':dict(platform='料小宝',user_id='123',token='test',secret='key',iv='iv',name='发布账号')}
        with patch('publisher_app.monitor_dashboard.load_session',side_effect=lambda name:saved if name=='H5监控账号' else {}),patch('publisher_app.monitor_dashboard.load_articles',return_value={}):
            restored=MonitorView(self.root)
        try: self.assertNotIn('料小宝:123',restored.clients)
        finally: restored.destroy()

    def test_saved_lsb_monitor_account_restores(self):
        account = '料商宝:123'
        saved = {account:dict(platform='料商宝',user_id='123',uid='123',sid='test',name='用户',cookies={'test':'cookie'})}
        with patch('publisher_app.monitor_dashboard.load_session',side_effect=lambda key:saved if key=='H5监控账号' else {}), patch('publisher_app.monitor_dashboard.load_articles',return_value={}):
            restored = MonitorView(self.root)
        try:
            self.assertIn(account,restored.clients)
            self.assertEqual(restored.clients[account].user_id,'123')
            self.assertEqual(restored.clients[account].session.cookies.get('test'),'cookie')
            self.assertEqual(len(restored.accounts.get_children()),1)
            self.assertEqual(restored.selected_accounts,set())
        finally:
            restored.destroy()

    def test_lsb_initial_100_and_new_posts(self):
        from types import SimpleNamespace
        account = '料商宝:123'
        self.view.account_data[account] = dict(platform='料商宝',name='用户',user_id='123')
        self.view.clients[account] = SimpleNamespace(initial_limit=100)
        self.view.selected_accounts = {account}
        self.view._accept_cycle(([(account,{'encoded-shop':'商家'})],[],[]))
        key = (account,'encoded-shop')
        snapshot = dict(self.view.tasks[key])
        rows = [dict(planId=i,planTitle=f'文章{i}',planPublicTime=f'2026-11-04 12:{i//60:02d}:{i%60:02d}') for i in range(100)]
        self.view._accept_cycle(([],[(key,snapshot,rows)],[]))
        self.assertEqual(len(self.view.feed),100)
        self.view._accept_cycle(([],[(key,snapshot,rows)],[]))
        self.assertEqual(len(self.view.feed),100)
        self.view._accept_cycle(([],[(key,snapshot,[dict(planId=101,planTitle='新增',planPublicTime='2026-11-04 13:00:00')]+rows)],[]))
        self.assertEqual(len(self.view.feed),101)
        self.assertIn('新增 1 篇',self.view.logs.get('1.0','end'))

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.cache_writer = patch('publisher_app.monitor_dashboard.save_articles').start()
        self.addCleanup(patch.stopall)
        with patch('publisher_app.monitor_dashboard.load_session', return_value={}), patch('publisher_app.monitor_dashboard.load_articles', return_value={}):
            self.view = MonitorView(self.root)
        self.view.alert.set(False)
        self.account = '壹料:user1'
        self.view.account_data[self.account] = {'platform':'壹料', 'name':'测试用户'}
        self.view.selected_accounts = {self.account}

    def tearDown(self):
        self.root.destroy()

    def test_following_refresh_preserves_pause_and_removes_unfollowed(self):
        self.view._accept_cycle(([(self.account, {'expert1':'商家1'})], [], []))
        key = (self.account,'expert1')
        with patch('publisher_app.monitor_dashboard.save_session'):
            self.view._set_enabled([key],False)
        self.view._accept_cycle(([(self.account, {'expert1':'商家新名','expert2':'商家2'})], [], []))
        self.assertFalse(self.view.tasks[key]['enabled'])
        self.assertTrue(self.view.tasks[(self.account,'expert2')]['enabled'])
        self.view._accept_cycle(([(self.account, {'expert2':'商家2'})], [], []))
        self.assertNotIn(key,self.view.tasks)

    def test_initial_baseline_dedup_search_and_global_order(self):
        self.view._accept_cycle(([(self.account, {'expert1':'商家1'})], [], []))
        key = (self.account,'expert1')
        snapshot = dict(self.view.tasks[key])
        row = {'planId':1,'planTitle':'篮球🔥','planPublicTime':'2026-11-04 10:00:00'}
        self.view._accept_cycle(([],[(key,snapshot,[row])],[]))
        self.view._accept_cycle(([],[(key,snapshot,[row])],[]))
        self.assertEqual(len(self.view.feed),1)
        self.view.feed[('红料','expert2','2')] = ('红料','商家2','2026-11-04 11:00:00','足球',20,20,'')
        self.view._render_articles()
        first = self.view.articles.get_children()[0]
        self.assertEqual(self.view.articles.item(first,'values')[0],'红料')
        self.view.order.set('上架时间↑')
        first = self.view.articles.get_children()[0]
        self.assertEqual(self.view.articles.item(first,'values')[0],'壹料')
        self.view.keyword.set('篮球')
        self.assertEqual(len(self.view.articles.get_children()),1)
        self.assertIn('检查完成',self.view.logs.get('1.0','end'))
        self.view.keyword.set('')
        shop_label = next(label for label in self.view.shop_keys if label.startswith('[红料]'))
        self.view.shop.set(shop_label)
        self.assertEqual(len(self.view.articles.get_children()),1)
        first = self.view.articles.get_children()[0]
        self.assertEqual(self.view.articles.item(first,'values')[0],'红料')
        self.cache_writer.assert_called()

    def test_account_and_task_checkboxes(self):
        from types import SimpleNamespace
        self.view.account_data[self.account].update(user_id='user1')
        self.view.clients[self.account] = object()
        self.view._refresh_accounts()
        self.root.update_idletasks()
        item = self.view.accounts.get_children()[0]
        self.view.accounts.focus(item)
        self.view._select_accounts(SimpleNamespace(keysym='space'))
        self.assertNotIn(self.account,self.view.selected_accounts)
        self.view._select_accounts(SimpleNamespace(keysym='space'))
        self.assertIn(self.account,self.view.selected_accounts)
        self.view._accept_cycle(([(self.account, {'expert1':'商家1'})], [], []))
        self.view.checked_tasks.add((self.account,'expert1'))
        self.assertEqual(self.view._checked_keys(),[(self.account,'expert1')])

    def test_same_name_merchants_stay_separate_and_bulk_checks(self):
        other = '红料:user2'
        self.view.account_data[self.account].update(user_id='user1')
        self.view.account_data[other] = {'platform':'红料','name':'测试用户','user_id':'user2'}
        self.view.clients = {self.account:object(), other:object()}
        self.view._check_all_accounts(True)
        self.assertEqual(self.view.selected_accounts,{self.account,other})
        self.view._accept_cycle(([(self.account,{'same-id':'同名商家'}), (other,{'same-id':'同名商家'})], [], []))
        self.assertEqual(len(self.view.tasks),2)
        platforms = {self.view.merchants.set(item,'平台') for item in self.view.merchants.get_children()}
        self.assertEqual(platforms,{'壹料','红料'})
        self.view._check_all_tasks(True)
        self.assertEqual(len(self.view._checked_keys()),2)
        with patch('publisher_app.monitor_dashboard.save_session'):
            self.view._set_enabled([(self.account,'same-id')],False)
        self.assertTrue(self.view.tasks[(other,'same-id')]['enabled'])
        self.view._check_all_tasks(False)
        self.assertEqual(self.view._checked_keys(),[])
        self.view._check_all_accounts(False)
        self.assertEqual(self.view.selected_accounts,set())


if __name__ == '__main__':
    unittest.main()
