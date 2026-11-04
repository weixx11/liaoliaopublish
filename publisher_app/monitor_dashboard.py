"""Account-scoped monitoring tasks and a shared searchable article feed."""
import time
from queue import Queue, Empty
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from .monitor_view import MonitorLoginSupport
from .platforms.h5_monitor import DOMAINS, MonitorClient
from .platforms.liaoshangbao_monitor_adapter import LiaoshangbaoMonitorAdapter
from .platforms.liaoxiaobao_monitor_adapter import LiaoxiaobaoMonitorAdapter
from .storage import load_session, save_session
from .monitor_cache import load_articles, save_articles


class MonitorView(MonitorLoginSupport):
    def __init__(self, parent):
        self.account_data = load_session("H5监控账号")
        for platform in DOMAINS:
            saved = load_session(f"{platform}H5")
            if saved.get("user_id") and saved.get("token"):
                self.account_data.setdefault(f"{platform}:{saved['user_id']}", dict(saved, platform=platform))
        self.preferences = load_session("H5监控设置")
        self.feed = load_articles()
        self.checked_tasks = set()
        self.selected_accounts = set()
        self.follow_due = 0
        self.progress_events = Queue()
        super().__init__(parent)
        self.clients = {}
        for key,data in self.account_data.items():
            if data.get('platform') == '料商宝' and data.get('uid') and data.get('sid'):
                self.clients[key] = LiaoshangbaoMonitorAdapter(data)
            elif data.get('platform') == '料小宝' and data.get('purpose')=='user_monitor' and all(data.get(field) for field in ('token','secret','iv','user_id')):
                self.clients[key] = LiaoxiaobaoMonitorAdapter(data)
            elif data.get('token') and data.get('platform') in DOMAINS:
                self.clients[key] = MonitorClient(data['platform'],data)
        self._refresh_accounts()
        self.after(1000, self._tick)
        self.after(100,self._poll_progress)

    def _login_lxb_monitor(self):
        phone,password = self.lxb_monitor_phone.get().strip(),self.lxb_monitor_password.get()
        if not phone or not password:
            self.status.set('请填写料小宝用户监控账号和密码'); return
        client = LiaoxiaobaoMonitorAdapter()
        def done(saved):
            key = f"料小宝:{saved['user_id']}"
            client.user_id = saved['user_id']
            self.account_data[key] = saved
            save_session('H5监控账号',self.account_data)
            self.clients[key] = client
            self._refresh_accounts()
            self.lxb_monitor_password.delete(0,'end')
            self._log('料小宝用户监控登录成功，会话已独立保存，请到商家监控勾选账号')
        self._submit('料小宝用户监控登录',lambda:client.login(phone,password),done)

    def _poll_progress(self):
        try:
            for _ in range(30): self._log(self.progress_events.get_nowait())
        except Empty:
            pass
        self.after(100,self._poll_progress)

    def _build(self):
        self.keyword = tk.StringVar()
        self.order = tk.StringVar(value="上架时间↓")
        self.shop = tk.StringVar(value='全部店铺')
        self.merchant_query = tk.StringVar()
        body = ttk.Panedwindow(self, orient="horizontal")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        body.grid(row=0, column=0, sticky='nsew')
        left = ttk.Frame(body, padding=(0, 0, 8, 0))
        right = ttk.Frame(body)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        body.add(left, weight=2); body.add(right, weight=3)
        ttk.Label(left, text="已登录监控账号（可多选）").pack(anchor="w")
        self.accounts = ttk.Treeview(left, columns=('勾选','账号'), show='headings', height=5, selectmode='none')
        self.accounts.heading('勾选', text='选择'); self.accounts.column('勾选', width=45, stretch=False)
        self.accounts.heading('账号', text='平台 / 用户账号'); self.accounts.column('账号', width=280)
        self.accounts.pack(fill="x")
        self.accounts.bind('<ButtonRelease-1>', self._select_accounts)
        self.accounts.bind('<space>', self._select_accounts)
        account_actions = ttk.Frame(left); account_actions.pack(fill='x')
        ttk.Button(account_actions, text='全选账号', command=lambda: self._check_all_accounts(True)).pack(side='left')
        ttk.Button(account_actions, text='取消全选', command=lambda: self._check_all_accounts(False)).pack(side='left')
        ttk.Button(left, text="同步所选账号的关注商家", command=self._following).pack(fill="x", pady=5)
        bar = ttk.Frame(left); bar.pack(fill="x")
        ttk.Label(bar, text="间隔（秒，至少10）").pack(side="left")
        ttk.Entry(bar, textvariable=self.interval, width=6).pack(side="left")
        ttk.Checkbutton(left, text="新帖弹窗提醒", variable=self.alert).pack(anchor="w")
        actions = ttk.Frame(left); actions.pack(fill="x", pady=5)
        for label, action in (("开始所选", self._start), ("暂停所选", self._pause), ("立即检查", self._check)):
            ttk.Button(actions, text=label, command=action).pack(side="left")
        ttk.Label(left, text="勾选商家后批量操作；点击操作列独立开始 / 暂停").pack(anchor="w")
        merchant_search = ttk.Frame(left); merchant_search.pack(fill='x',pady=4)
        ttk.Label(merchant_search,text='搜索商家').pack(side='left')
        ttk.Entry(merchant_search,textvariable=self.merchant_query).pack(side='left',fill='x',expand=True,padx=4)
        ttk.Button(merchant_search,text='清空',command=lambda:self.merchant_query.set('')).pack(side='left')
        merchant_actions = ttk.Frame(left); merchant_actions.pack(fill='x')
        ttk.Button(merchant_actions, text='全选商家', command=lambda: self._check_all_tasks(True)).pack(side='left')
        ttk.Button(merchant_actions, text='取消全选', command=lambda: self._check_all_tasks(False)).pack(side='left')
        taskbox = ttk.Frame(left); taskbox.pack(fill='both', expand=True)
        self.merchants = ttk.Treeview(taskbox, columns=('勾选','平台','商家', '账号', '状态', '操作'), show='headings', height=14)
        for name, width in (('勾选',42), ('平台',48), ('商家',120), ('账号',120), ('状态',60), ('操作',50)):
            self.merchants.heading(name, text=name); self.merchants.column(name, width=width, stretch=False)
        task_scroll = ttk.Scrollbar(taskbox, command=self.merchants.yview)
        task_x = ttk.Scrollbar(taskbox, orient='horizontal', command=self.merchants.xview)
        self.merchants.configure(yscrollcommand=task_scroll.set, xscrollcommand=task_x.set)
        task_scroll.pack(side='right', fill='y'); task_x.pack(side='bottom', fill='x')
        self.merchants.pack(fill='both', expand=True)
        self.merchants.bind('<ButtonRelease-1>', self._task_click)
        self.merchants.bind('<<TreeviewSelect>>', self._show_task_details)
        filters = ttk.Frame(right); filters.grid(row=0, column=0, sticky='ew', pady=(0,6))
        ttk.Label(filters, text="标题关键词").pack(side='left')
        ttk.Entry(filters, textvariable=self.keyword).pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(filters, text="清空", command=lambda: self.keyword.set('')).pack(side='left')
        ttk.Combobox(filters, textvariable=self.order, values=('上架时间↓','上架时间↑'), state='readonly', width=12).pack(side='left')
        self.keyword.trace_add('write', lambda *_: self._render_articles())
        self.order.trace_add('write', lambda *_: self._render_articles())
        shopbar = ttk.Frame(right); shopbar.grid(row=1, column=0, sticky='ew', pady=(0,5))
        searchbar = ttk.Frame(shopbar); searchbar.pack(fill='x',pady=(0,4))
        ttk.Label(searchbar,text='搜索商家').pack(side='left')
        ttk.Entry(searchbar,textvariable=self.merchant_query).pack(side='left',fill='x',expand=True,padx=5)
        ttk.Button(searchbar,text='清空',command=lambda:self.merchant_query.set('')).pack(side='left')
        ttk.Label(shopbar, text='店铺').pack(side='left')
        self.shop_picker = ttk.Combobox(shopbar, textvariable=self.shop, state='readonly', values=['全部店铺'])
        self.shop_picker.pack(side='left', fill='x', expand=True, padx=5)
        self.shop.trace_add('write', lambda *_: self._render_articles())
        self.article_count = ttk.Label(shopbar); self.article_count.pack(side='right')
        table = ttk.Frame(right); table.grid(row=2, column=0, sticky='nsew')
        columns = ('平台','商家','上架时间','标题','原价','实际价','置顶')
        self.articles = ttk.Treeview(table, columns=columns, show='headings')
        self.article_menu = tk.Menu(self.articles, tearoff=False)
        self.article_menu.add_command(label='复制完整标题', command=self._copy_titles)
        self.articles.bind('<Button-3>', self._article_context_menu)
        self.articles.bind('<Control-c>', self._copy_titles)
        self.articles.bind('<Control-C>', self._copy_titles)
        for name, width in zip(columns, (50,95,140,350,60,60,45)):
            self.articles.heading(name, text=name)
            self.articles.column(name, width=width, stretch=name=='标题')
        ybar = ttk.Scrollbar(table, command=self.articles.yview)
        xbar = ttk.Scrollbar(table, orient='horizontal', command=self.articles.xview)
        self.articles.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        ybar.pack(side='right', fill='y'); xbar.pack(side='bottom', fill='x')
        self.articles.pack(fill='both', expand=True)
        self.articles.bind('<<TreeviewSelect>>', self._show_article_details)
        logbar = ttk.Frame(right); logbar.grid(row=3, column=0, sticky='ew')
        ttk.Label(logbar, text='监控运行日志（关注同步 / 商家检查 / 新文章）').pack(side='left')
        ttk.Button(logbar, text='清空日志', command=self._clear_log).pack(side='right')
        self.logs = scrolledtext.ScrolledText(right, height=5, state='disabled')
        self.logs.grid(row=4, column=0, sticky='ew')
        ttk.Label(self, textvariable=self.status).grid(row=1, column=0, sticky='w')
        ttk.Label(self, text='所选商家 / 文章详情').grid(row=2, column=0, sticky='w', pady=(4,0))
        self.details = scrolledtext.ScrolledText(self, height=3, wrap='word', state='disabled')
        self.details.grid(row=3, column=0, sticky='ew', pady=(4,0))
        self._set_details('选择商家查看完整账号、商家ID和监控状态；选择文章查看完整标题。查询结果会自动保存，重启后可继续搜索。')
        self._render_articles()
        self.merchant_query.trace_add('write',self._filter_merchants)

    def _matches_merchant(self, platform, name, merchant_id):
        query = self.merchant_query.get().strip().casefold()
        return query in f'{platform} {name} {merchant_id}'.casefold()

    def _filter_merchants(self, *_args):
        self._render_tasks()
        self._render_articles()

    def build_login_page(self, notebook):
        page = ttk.Frame(notebook, padding=16)
        notebook.add(page, text='壹料 / 红料用户登录')
        ttk.Label(page, text='监控用 H5 用户账号，可分别登录多个账号；会话自动保存。').pack(anchor='w')
        login = ttk.Frame(page); login.pack(fill='x', pady=12)
        ttk.Combobox(login, textvariable=self.platform, values=list(DOMAINS), state='readonly', width=7).pack(side='left')
        for label, variable, width, button, command in (
            ('手机号', self.phone, 13, '获取图片', self._captcha),
            ('图形码', self.captcha_code, 6, '发送短信', self._send_sms),
            ('短信码', self.sms_code, 7, '登录', self._login)):
            ttk.Label(login, text=label).pack(side='left', padx=3)
            ttk.Entry(login, textvariable=variable, width=width).pack(side='left')
            ttk.Button(login, text=button, command=command).pack(side='left')
        self.captcha_label = ttk.Label(page); self.captcha_label.pack(anchor='w')
        ttk.Label(page, textvariable=self.status).pack(anchor='w', pady=8)
        self.login_accounts = tk.Listbox(page, height=8)
        self.login_accounts.pack(fill='x')
        lsb_page = ttk.Frame(notebook,padding=16)
        notebook.add(lsb_page,text='料商宝用户监控登录')
        ttk.Label(lsb_page,text='监控用户账号独立保存，可登录多个；不影响料商宝发布账号。').grid(row=0,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Label(lsb_page,text='手机号').grid(row=1,column=0,sticky='w')
        self.lsb_monitor_phone = ttk.Entry(lsb_page,width=30)
        self.lsb_monitor_phone.grid(row=1,column=1,padx=8,pady=6)
        ttk.Label(lsb_page,text='密码').grid(row=2,column=0,sticky='w')
        self.lsb_monitor_password = ttk.Entry(lsb_page,width=30,show='●')
        self.lsb_monitor_password.grid(row=2,column=1,padx=8,pady=6)
        ttk.Button(lsb_page,text='登录并保存监控账号',command=self._login_lsb_monitor).grid(row=3,column=1,pady=8,sticky='e')
        ttk.Label(lsb_page,textvariable=self.status,wraplength=650).grid(row=4,column=0,columnspan=2,sticky='w')
        self.lsb_login_accounts = tk.Listbox(lsb_page,height=6)
        self.lsb_login_accounts.grid(row=5,column=0,columnspan=2,sticky='ew',pady=8)
        lxb_page = ttk.Frame(notebook,padding=16)
        notebook.add(lxb_page,text='料小宝用户监控登录')
        ttk.Label(lxb_page,text='使用用户账号登录监控，独立保存会话。').grid(row=0,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Label(lxb_page,text='手机号').grid(row=1,column=0,sticky='w')
        self.lxb_monitor_phone = ttk.Entry(lxb_page,width=30); self.lxb_monitor_phone.grid(row=1,column=1,padx=8,pady=6)
        ttk.Label(lxb_page,text='密码').grid(row=2,column=0,sticky='w')
        self.lxb_monitor_password = ttk.Entry(lxb_page,width=30,show='●'); self.lxb_monitor_password.grid(row=2,column=1,padx=8,pady=6)
        ttk.Button(lxb_page,text='登录并保存用户监控账号',command=self._login_lxb_monitor).grid(row=3,column=1,sticky='e',pady=8)
        ttk.Label(lxb_page,textvariable=self.status,wraplength=650).grid(row=4,column=0,columnspan=2,sticky='w')
        self.lxb_login_accounts = tk.Listbox(lxb_page,height=6); self.lxb_login_accounts.grid(row=5,column=0,columnspan=2,sticky='ew',pady=8)
        self._refresh_accounts()

    def _login_lsb_monitor(self):
        phone = self.lsb_monitor_phone.get().strip()
        password = self.lsb_monitor_password.get()
        if not phone or not password:
            self.status.set('请填写料商宝监控账号手机号和密码'); return
        client = LiaoshangbaoMonitorAdapter()
        def done(saved):
            key = f"料商宝:{saved['user_id']}"
            self.account_data[key] = saved
            save_session('H5监控账号',self.account_data)
            self.clients[key] = client
            self.lsb_monitor_password.delete(0,'end')
            self._refresh_accounts()
            self._log(f'料商宝监控账号 {phone} 登录成功，已保存会话，请到商家监控勾选账号')
        self._submit('料商宝用户登录',lambda:client.login(phone,password),done)

    def _refresh_accounts(self):
        self.account_keys = list(self.clients)
        self.accounts.delete(*self.accounts.get_children())
        self.account_ids = {}
        if hasattr(self, 'login_accounts'): self.login_accounts.delete(0, 'end')
        if hasattr(self,'lsb_login_accounts'): self.lsb_login_accounts.delete(0,'end')
        if hasattr(self,'lxb_login_accounts'): self.lxb_login_accounts.delete(0,'end')
        for index, key in enumerate(self.account_keys):
            data = self.account_data[key]
            label = f"[{data['platform']}] {data.get('name', '')} ({data.get('phone', data['user_id'])})"
            iid = self.accounts.insert('', 'end', values=('☑' if key in self.selected_accounts else '☐',label))
            self.account_ids[iid] = key
            if hasattr(self, 'login_accounts'): self.login_accounts.insert('end', label + ' · 已保存会话')
            if data['platform']=='料商宝' and hasattr(self,'lsb_login_accounts'):
                self.lsb_login_accounts.insert('end',label+' · 已保存会话')
            if data['platform']=='料小宝' and hasattr(self,'lxb_login_accounts'):
                self.lxb_login_accounts.insert('end',label+' · 已保存用户监控会话')

    def _login(self):
        client = self._challenge()
        code = self.sms_code.get().strip()
        if not client: return
        if len(code) != 6 or not code.isascii() or not code.isdecimal():
            self.status.set('请输入六位短信验证码'); return
        platform, phone = self.platform.get(), self.phone.get().strip()
        def done(saved):
            key = f"{platform}:{saved['user_id']}"
            self.account_data[key] = dict(saved, platform=platform, phone=phone)
            save_session('H5监控账号', self.account_data)
            self.clients[key] = client
            self.challenges.pop(platform, None)
            self.sms_code.set(''); self.captcha_code.set(''); self.captcha_label.configure(image='')
            self._refresh_accounts()
            self._log(f"{platform} {saved['name']} 登录成功，已保存会话")
        self._submit('用户登录', lambda: client.login(code), done)

    def _log(self, message):
        for client in self.clients.values():
            sid = getattr(client,'sid',None)
            if sid: message = message.replace(str(sid),'[会话已隐藏]')
        self.status.set(message)
        self.logs.configure(state='normal')
        self.logs.insert('end', f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
        if int(self.logs.index('end-1c').split('.')[0]) > 1000: self.logs.delete('1.0','101.0')
        self.logs.see('end'); self.logs.configure(state='disabled')

    def _clear_log(self):
        self.logs.configure(state='normal'); self.logs.delete('1.0','end'); self.logs.configure(state='disabled')

    def _select_accounts(self, event=None):
        item = self.accounts.focus() if event and event.keysym == 'space' else self.accounts.identify_row(event.y) if event else ''
        key = self.account_ids.get(item)
        if not key: return
        if key in self.selected_accounts: self.selected_accounts.remove(key)
        else: self.selected_accounts.add(key)
        self.accounts.set(item,'勾选','☑' if key in self.selected_accounts else '☐')
        self.follow_due = 0
        self._render_tasks()

    def _following(self):
        self.follow_due = 0
        self._cycle()

    def _check_all_accounts(self, checked):
        self.selected_accounts = set(self.clients) if checked else set()
        self.follow_due = 0
        self._refresh_accounts()
        self._render_tasks()

    def _check_all_tasks(self, checked):
        visible = set(self.task_ids.values())
        if checked:
            self.checked_tasks.update(visible)
        else:
            self.checked_tasks.difference_update(visible)
        self._render_tasks()

    def _render_tasks(self):
        selected = {self.task_ids[i] for i in self.merchants.selection() if i in getattr(self,'task_ids',{})}
        self.merchants.delete(*self.merchants.get_children())
        self.task_ids = {}
        for key, task in self.tasks.items():
            if key[0] not in self.selected_accounts: continue
            if not self._matches_merchant(self.account_data[key[0]]['platform'],task['name'],key[1]): continue
            iid = self.merchants.insert('', 'end', values=('☑' if key in self.checked_tasks else '☐',self.account_data[key[0]]['platform'],task['name'],self.account_data[key[0]].get('name',''),
                                                         '运行中' if task['enabled'] else '已暂停',
                                                         '暂停' if task['enabled'] else '开始'))
            self.task_ids[iid] = key
            if key in selected: self.merchants.selection_add(iid)

    def _task_click(self, event):
        item = self.merchants.identify_row(event.y)
        key = self.task_ids.get(item)
        if not key: return
        column = self.merchants.identify_column(event.x)
        if column == '#1':
            if key in self.checked_tasks: self.checked_tasks.remove(key)
            else: self.checked_tasks.add(key)
            self.merchants.set(item,'勾选','☑' if key in self.checked_tasks else '☐')
        elif column == '#6': self._set_enabled([key], not self.tasks[key]['enabled'])
        self._show_task_details()

    def _set_enabled(self, keys, enabled):
        if not keys:
            self._log('请先勾选要操作的商家'); return
        try:
            seconds = int(self.interval.get())
            if seconds < 10: raise ValueError
        except ValueError:
            self._log('监控间隔至少为10秒'); return
        for key in keys:
            task = self.tasks[key]
            task.update(enabled=enabled, seconds=seconds, due=0, generation=task['generation']+1)
            self.preferences['|'.join(key)] = {'enabled':enabled, 'seconds':seconds}
            platform = self.account_data[key[0]]['platform']
            self._log(f"[{platform} / {task['name']} / {key[1]}] {'开始' if enabled else '暂停'}监控")
        save_session('H5监控设置', self.preferences)
        self._render_tasks()

    def _start(self):
        self._set_enabled(self._checked_keys(), True)

    def _pause(self):
        self._set_enabled(self._checked_keys(), False)

    def _checked_keys(self):
        return [key for key in self.task_ids.values() if key in self.checked_tasks]

    def _check(self):
        keys = self._checked_keys()
        if not keys: self._log('请先选择商家'); return
        self._cycle(keys)

    def _tick(self):
        self._cycle()
        self.after(1000, self._tick)

    def _cycle(self, manual=None):
        if self.busy or not self.selected_accounts: return
        now = time.monotonic()
        accounts = [(key,self.clients[key]) for key in self.selected_accounts]
        refresh = now >= self.follow_due
        jobs = [(key,dict(task),self.clients[key[0]]) for key,task in self.tasks.items()
                if key[0] in self.selected_accounts and
                (key in manual if manual is not None else task['enabled'] and task['due'] <= now)]
        if not refresh and not jobs: return
        self.follow_due = now + 60 if refresh else self.follow_due
        for key, task, _ in jobs: self.tasks[key]['due'] = now + task['seconds']
        def work():
            followed, results, errors = [], [], []
            if refresh:
                for account,client in accounts:
                    try: followed.append((account,client.following()))
                    except Exception as exc: errors.append(f"账号 {self.account_data[account].get('name','')} 关注列表失败：{exc}")
            for key,task,client in jobs:
                try:
                    if isinstance(client,LiaoxiaobaoMonitorAdapter):
                        def progress(page,pages,count,name=task['name']):
                            if page==1 or page%10==0 or page==pages:
                                self.progress_events.put(f'[料小宝 / {name}] 正在核对分页 {page}/{pages}，已读取在售文章 {count} 篇')
                        rows = client.latest(key[1],progress=progress)
                    else:
                        rows = client.latest(key[1])
                    results.append((key,task,rows))
                except Exception as exc: errors.append(f"[{self.account_data[key[0]]['platform']} / {task['name']} / {key[1]}] 检查失败：{exc}")
            return followed,results,errors
        self._submit('检查关注商家与最新文章', work, self._accept_cycle)

    def _accept_cycle(self, output):
        followed, results, errors = output
        for account,merchants in followed:
            if account not in self.selected_accounts: continue
            for key in list(self.tasks):
                if key[0] == account and key[1] not in merchants:
                    del self.tasks[key]
                    self.checked_tasks.discard(key)
            for expert,name in merchants.items():
                key = (account,expert)
                if key in self.tasks: self.tasks[key]['name'] = name; continue
                preference = self.preferences.get('|'.join(key), {})
                self.tasks[key] = dict(name=name, enabled=preference.get('enabled',True),
                                       seconds=max(10,int(preference.get('seconds',60))),due=0,generation=0)
            self._log(f"{self.account_data[account].get('name','')}：关注商家 {len(merchants)} 个，已同步任务")
        notices = []
        for key,snapshot,rows in results:
            task = self.tasks.get(key)
            if not task or key[0] not in self.selected_accounts or task['generation'] != snapshot['generation']: continue
            baseline = key not in self.seen
            seen = self.seen.setdefault(key,set())
            fresh = [row for row in rows if row.get('planId') is not None and str(row['planId']) not in seen]
            seen.update(str(row['planId']) for row in rows if row.get('planId') is not None)
            fresh.sort(key=lambda row: str(row.get('planPublicTime') or ''), reverse=True)
            platform = self.account_data[key[0]]['platform']
            initial_limit = getattr(self.clients.get(key[0]),'initial_limit',100)
            incoming = fresh[:initial_limit] if baseline else fresh
            new_ids = {str(row['planId']) for row in incoming}
            # Refresh cached titles too, without treating subtitle changes as new posts.
            for row in rows:
                if row.get('planId') is None: continue
                article_key = (platform,key[1],str(row['planId']))
                if str(row['planId']) not in new_ids and article_key not in self.feed: continue
                title = str(row.get('planTitle') or '').strip()
                subtitle = str(row.get('planSubtitle') or '').strip()
                display_title = f'{title} | {subtitle}' if title and subtitle and subtitle != title else title or subtitle
                self.feed[(platform,key[1],str(row['planId']))] = (platform,task['name'],row.get('planPublicTime') or '',
                    display_title,row.get('price'),row.get('priceReal'),'是' if row.get('top') else '')
            count = 0 if baseline else len(fresh)
            self._log(f"[{platform} / {task['name']}] 检查完成，共 {len(rows)} 篇，" + (f'首次载入最近{initial_limit}篇' if baseline else f'新增 {count} 篇'))
            if count: notices.append(f"[{platform}] {task['name']}：新增 {count} 篇")
        for error in errors: self._log(error)
        if len(self.feed) > 5000:
            keep = sorted(self.feed, key=lambda key:self.feed[key][2], reverse=True)[:5000]
            self.feed = {key:self.feed[key] for key in keep}
        self._render_tasks(); self._render_articles()
        if results:
            try: save_articles(self.feed)
            except OSError as exc: self._log(f'文章缓存保存失败：{exc}')
        if notices and self.alert.get(): messagebox.showinfo('商家新帖', '\n'.join(notices[:10]), parent=self)

    def _article_context_menu(self, event):
        item = self.articles.identify_row(event.y)
        if not item:
            return
        if item not in self.articles.selection():
            self.articles.selection_set(item)
        self.articles.focus_set()
        try:
            self.article_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.article_menu.grab_release()

    def _copy_titles(self, _event=None):
        selected = set(self.articles.selection())
        titles = [self.articles.set(item, '标题')
                  for item in self.articles.get_children() if item in selected]
        if titles:
            self.clipboard_clear()
            self.clipboard_append('\n'.join(titles))
            self.status.set(f'已复制 {len(titles)} 篇文章的完整标题')
        return 'break'

    def _render_articles(self):
        if not hasattr(self,'articles'): return
        self.shop_keys = {'全部店铺': None}
        for (platform, expert, article_id), values in self.feed.items():
            if not self._matches_merchant(platform,values[1],expert): continue
            self.shop_keys[f'[{platform}] {values[1]} · {expert}'] = (platform, expert)
        self.shop_picker.configure(values=list(self.shop_keys))
        if self.shop.get() not in self.shop_keys: self.shop.set('全部店铺')
        query = self.keyword.get().strip().casefold()
        shop = self.shop_keys.get(self.shop.get())
        rows = [row for key,row in self.feed.items() if query in row[3].casefold()
                and self._matches_merchant(key[0],row[1],key[1]) and (shop is None or key[:2] == shop)]
        rows.sort(key=lambda row:row[2], reverse=self.order.get().endswith('↓'))
        self.articles.delete(*self.articles.get_children())
        for row in rows[:500]: self.articles.insert('','end',values=tuple('' if value is None else value for value in row))
        self.article_count.configure(text=f'匹配 {len(rows)} / 共 {len(self.feed)} 篇')

    def _set_details(self, text):
        self.details.configure(state='normal'); self.details.delete('1.0','end')
        self.details.insert('1.0',text); self.details.configure(state='disabled')

    def _show_task_details(self, _event=None):
        items = self.merchants.selection()
        if not items: return
        key = self.task_ids.get(items[0])
        if key not in self.tasks: return
        task, account = self.tasks[key], self.account_data[key[0]]
        self._set_details(f"商家：{task['name']}　平台：{account['platform']}　商家ID：{key[1]}\n账号：{account.get('name','')}　用户ID：{account.get('user_id',key[0])}\n监控：{'运行中' if task['enabled'] else '已暂停'}　间隔：{task['seconds']} 秒")

    def _show_article_details(self, _event=None):
        selected = self.articles.selection()
        if selected:
            row = self.articles.item(selected[0], 'values')
            self._set_details(f'平台：{row[0]}　商家：{row[1]}　上架时间：{row[2]}\n完整标题：{row[3]}')

    def _schedule(self):
        pass  # Scheduling is task-specific and handled by _tick.
