"""壹料与料商宝统一发布/编辑器。平台登录和图片处理彼此独立。"""
import json
import queue
import re
import sys
import threading
import tempfile
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from urllib.parse import unquote
from PIL import ImageGrab

from publisher_app.platforms.yiliao import YiliaoPlatform
from publisher_app.platforms.liaoshangbao import LiaoshangbaoPlatform

ROOT = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
       else Path(__file__).resolve().parent)
LSB_SESSION_FILE = ROOT / "料商宝会话.json"
ARTICLE_MAP_FILE = ROOT / "多平台文章映射.json"


class UnifiedPublisher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("多平台文章发布与编辑")
        self.geometry("1000x780")
        self.minsize(820, 650)
        self.yiliao = YiliaoPlatform()
        self.lsb = self._load_lsb_session()
        self.lsb_platform = LiaoshangbaoPlatform(uid=self.lsb.get("uid"), sid=self.lsb.get("sid"))
        self.lsb_platform.session.cookies.update(self.lsb.get("cookies", {}))
        # Keep file attachments scoped to each editor; a prior publish must not
        # leak its first image into the next article.
        self.publish_images = []
        self.edit_images = []
        self.events = queue.Queue()
        self.mapping = self._load_mapping()
        self._build()
        self._refresh_status()
        self.after(120, self._poll)

    def _load_lsb_session(self):
        try:
            data = json.loads(LSB_SESSION_FILE.read_text(encoding="utf-8"))
            return data
        except (OSError, ValueError):
            return {"uid": None, "sid": None}

    def _load_mapping(self):
        try:
            raw = json.loads(ARTICLE_MAP_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        # Upgrade the former one-platform-per-row format into title records.
        grouped = {}
        for row in raw:
            title = row.get("title", "")
            entry = grouped.setdefault(title, {"title": title, "ids": {}})
            if row.get("price") is not None:
                entry["price"] = row["price"]
            platform = row.get("platform")
            if platform:
                entry["ids"][platform] = str(row.get("id", ""))
            else:
                entry["ids"].update(row.get("ids", {}))
        return list(grouped.values())

    def _save_mapping(self, platform, title, article_id, price):
        entry = next((row for row in self.mapping if row.get("title") == title), None)
        if entry is None:
            entry = {"title": title, "ids": {}}
            self.mapping.insert(0, entry)
        entry.setdefault("ids", {})[platform] = str(article_id)
        entry["price"] = price
        ARTICLE_MAP_FILE.write_text(json.dumps(self.mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        self.refresh_map()

    def _build(self):
        root = ttk.Frame(self, padding=12); root.pack(fill="both", expand=True)
        ttk.Label(root, text="统一文章工作台", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        tabs = ttk.Notebook(root); tabs.pack(fill="both", expand=True, pady=8)
        self.login_tab = ttk.Frame(tabs, padding=10)
        self.pub = ttk.Frame(tabs, padding=10); self.edit = ttk.Frame(tabs, padding=10)
        tabs.add(self.login_tab, text="平台登录"); tabs.add(self.pub, text="统一发布"); tabs.add(self.edit, text="统一编辑")
        self._build_login(); self._build_publish(); self._build_edit()
        self.log = scrolledtext.ScrolledText(root, height=7, state="disabled"); self.log.pack(fill="x")

    def _build_login(self):
        pages = ttk.Notebook(self.login_tab); pages.pack(fill="both", expand=True)
        self.y_login_page = ttk.Frame(pages, padding=18); self.l_login_page = ttk.Frame(pages, padding=18)
        pages.add(self.y_login_page, text="壹料"); pages.add(self.l_login_page, text="料商宝")
        ybox = ttk.LabelFrame(self.y_login_page, text="壹料账号登录", padding=14); ybox.pack(anchor="nw", fill="x")
        ttk.Label(ybox, text="账号").grid(row=0, column=0, sticky="w", pady=6)
        self.y_account = ttk.Entry(ybox, width=30); self.y_account.grid(row=0, column=1, padx=8, pady=6)
        ttk.Label(ybox, text="密码").grid(row=1, column=0, sticky="w", pady=6)
        self.y_password = ttk.Entry(ybox, width=30, show="●"); self.y_password.grid(row=1, column=1, padx=8, pady=6)
        ttk.Button(ybox, text="登录壹料", command=self.login_yiliao).grid(row=2, column=1, sticky="e", padx=8, pady=8)
        self.y_status = ttk.Label(ybox, text=""); self.y_status.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=5)
        lbox = ttk.LabelFrame(self.l_login_page, text="料商宝账号登录", padding=14); lbox.pack(anchor="nw", fill="x")
        ttk.Label(lbox, text="手机号 / 账号").grid(row=0, column=0, sticky="w", pady=6)
        self.mobile = ttk.Entry(lbox, width=30); self.mobile.grid(row=0, column=1, padx=8, pady=6)
        ttk.Label(lbox, text="密码").grid(row=1, column=0, sticky="w", pady=6)
        self.password = ttk.Entry(lbox, width=30, show="●"); self.password.grid(row=1, column=1, padx=8, pady=6)
        ttk.Button(lbox, text="登录料商宝", command=self.login_lsb).grid(row=2, column=1, sticky="e", padx=8, pady=8)
        self.l_status = ttk.Label(lbox, text=""); self.l_status.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=5)

    def _build_publish(self):
        self.pub.columnconfigure(1, weight=1); self.pub.rowconfigure(5, weight=1)
        ttk.Label(self.pub, text="标题").grid(row=1, column=0, sticky="w", pady=3); self.title = ttk.Entry(self.pub, font=("Segoe UI Emoji", 11)); self.title.grid(row=1, column=1, sticky="ew")
        ttk.Label(self.pub, text="副标题").grid(row=2, column=0, sticky="w", pady=3); self.subtitle = ttk.Entry(self.pub, font=("Segoe UI Emoji", 11)); self.subtitle.grid(row=2, column=1, sticky="ew")
        ttk.Label(self.pub, text="免费内容").grid(row=3, column=0, sticky="w", pady=3); self.free = ttk.Entry(self.pub); self.free.grid(row=3, column=1, sticky="ew")
        ttk.Label(self.pub, text="正文").grid(row=4, column=0, sticky="nw"); self.body = tk.Text(self.pub, height=10, wrap="word"); self.body.grid(row=4, column=1, sticky="nsew")
        self.body.bind("<Control-v>", lambda event: self.paste_image(event, self.body), add="+")
        ttk.Button(self.pub, text="添加图片（平台发布时分别处理）", command=lambda: self.add_images(self.body)).grid(row=5, column=1, sticky="w", pady=4)
        options = ttk.Frame(self.pub); options.grid(row=6, column=1, sticky="ew", pady=4)
        ttk.Label(options, text="价格").pack(side="left"); self.price = ttk.Entry(options, width=8); self.price.insert(0, "10"); self.price.pack(side="left", padx=4)
        ttk.Label(options, text="标签").pack(side="left", padx=(8, 0)); self.label = ttk.Entry(options, width=18); self.label.insert(0, "biaobiao"); self.label.pack(side="left", padx=4)
        self.presale = tk.IntVar(value=1); ttk.Checkbutton(options, text="预售", variable=self.presale).pack(side="left", padx=4)
        self.discount = tk.IntVar(value=1); ttk.Checkbutton(options, text="允许折扣", variable=self.discount).pack(side="left", padx=4)
        ttk.Label(self.pub, text="发布平台").grid(row=7, column=0, sticky="w")
        targets = ttk.Frame(self.pub); targets.grid(row=7, column=1, sticky="w")
        self.pub_y = tk.IntVar(value=1); self.pub_l = tk.IntVar(value=1)
        ttk.Checkbutton(targets, text="壹料", variable=self.pub_y).pack(side="left", padx=5)
        ttk.Checkbutton(targets, text="料商宝（平台同步默认开启）", variable=self.pub_l).pack(side="left", padx=5)
        ttk.Label(self.pub, text="壹料同步子账号").grid(row=8, column=0, sticky="nw")
        self.child_list = tk.Listbox(self.pub, selectmode="multiple", height=4, exportselection=False); self.child_list.grid(row=8, column=1, sticky="ew")
        ttk.Button(self.pub, text="刷新壹料子账号", command=self.load_children).grid(row=9, column=1, sticky="w", pady=3)
        ttk.Button(self.pub, text="发布到所选平台", command=self.publish).grid(row=10, column=1, sticky="e", pady=6)

    def _add_emoji_picker(self, frame, widgets):
        menu = tk.Menu(frame, tearoff=False)
        target = widgets[0]

        def remember(event):
            nonlocal target
            target = event.widget

        for widget in widgets:
            widget.bind("<FocusIn>", remember, add="+")
        for emoji in ("🔥", "🏀", "⚽️", "🏆", "🎉", "👍", "⭐", "❤️", "✅", "😂"):
            menu.add_command(label=emoji, command=lambda value=emoji: target.insert("insert", value))
        button = ttk.Menubutton(frame, text="插入表情", menu=menu)
        button.grid(row=0, column=0, sticky="w", padx=4)

    def _build_edit(self):
        ttk.Label(self.edit, text="搜索标题 / ID").grid(row=0, column=0, sticky="w", pady=4)
        self.map_search = ttk.Entry(self.edit); self.map_search.grid(row=0, column=1, sticky="ew")
        self.map_search.bind("<KeyRelease>", lambda _e: self.refresh_map())
        ttk.Label(self.edit, text="标题 | 两平台文章 ID").grid(row=1, column=0, sticky="nw")
        self.maplist = tk.Listbox(self.edit, height=6, exportselection=False); self.maplist.grid(row=1, column=1, sticky="ew")
        self.maplist.bind("<<ListboxSelect>>", self.select_mapping)
        self.edit.columnconfigure(1, weight=1); self.edit.rowconfigure(6, weight=1)
        ttk.Label(self.edit, text="文章 ID").grid(row=2, column=0, sticky="w", pady=4); self.edit_id = ttk.Entry(self.edit); self.edit_id.grid(row=2, column=1, sticky="ew")
        ttk.Label(self.edit, text="更新标题").grid(row=3, column=0, sticky="w", pady=4); self.edit_title = ttk.Entry(self.edit, font=("Segoe UI Emoji", 11)); self.edit_title.grid(row=3, column=1, sticky="ew")
        ttk.Label(self.edit, text="副标题").grid(row=4, column=0, sticky="w", pady=4); self.edit_subtitle = ttk.Entry(self.edit, font=("Segoe UI Emoji", 11)); self.edit_subtitle.grid(row=4, column=1, sticky="ew")
        ttk.Label(self.edit, text="摘要 / 短消息").grid(row=5, column=0, sticky="w", pady=4); self.edit_summary = ttk.Entry(self.edit); self.edit_summary.grid(row=5, column=1, sticky="ew")
        ttk.Label(self.edit, text="追加正文").grid(row=6, column=0, sticky="nw"); self.edit_body = tk.Text(self.edit, height=10); self.edit_body.grid(row=6, column=1, sticky="nsew")
        self.edit_body.bind("<Control-v>", lambda event: self.paste_image(event, self.edit_body), add="+")
        ttk.Button(self.edit, text="添加图片（由目标平台处理）", command=lambda: self.add_images(self.edit_body)).grid(row=7, column=1, sticky="w", pady=4)
        row = ttk.Frame(self.edit); row.grid(row=8, column=1, sticky="ew")
        ttk.Label(row, text="价格").pack(side="left"); self.edit_price = ttk.Entry(row, width=8); self.edit_price.pack(side="left", padx=4)
        self.edit_presale = tk.IntVar(value=1)
        ttk.Checkbutton(row, text="预售", variable=self.edit_presale).pack(side="left", padx=4)
        self.edit_discount = tk.IntVar(value=1)
        ttk.Checkbutton(row, text="允许折扣", variable=self.edit_discount).pack(side="left", padx=4)
        actions = ttk.Frame(self.edit); actions.grid(row=9, column=1, sticky="e", pady=5)
        ttk.Button(actions, text="更新并同步", command=self.update).pack(side="left", padx=3)
        ttk.Button(actions, text="统一置顶", command=lambda: self.change_top(True)).pack(side="left", padx=3)
        ttk.Button(actions, text="统一取消置顶", command=lambda: self.change_top(False)).pack(side="left", padx=3)
        self.refresh_map()
        self._add_emoji_picker(self.pub, (self.title, self.subtitle, self.body))
        emoji_row = ttk.Frame(self.edit)
        emoji_row.grid(row=7, column=0, sticky="w")
        self._add_emoji_picker(emoji_row, (self.edit_title, self.edit_subtitle, self.edit_body))

    def _refresh_status(self):
        self.y_status.configure(text="在线：{}".format(self.yiliao.user.get("name") or self.yiliao.user.get("account")) if self.yiliao.logged_in else "未登录")
        self.l_status.configure(text="在线 uid：{}".format(self.lsb.get("uid")) if self.lsb.get("sid") else "未登录")

    def _log(self, text):
        self.log.configure(state="normal"); self.log.insert("end", text + "\n"); self.log.see("end"); self.log.configure(state="disabled")

    def _run(self, title, fn, done=None):
        def work():
            try: self.events.put((title, True, fn(), done))
            except Exception as exc: self.events.put((title, False, str(exc), None))
        self._log(title + "处理中…"); threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                title, ok, result, done = self.events.get_nowait()
                self._log(title + ("完成：" if ok else "失败：") + str(result))
                if ok and done: done(result)
                if not ok: messagebox.showerror(title, str(result))
                self._refresh_status()
        except queue.Empty: pass
        self.after(120, self._poll)

    def login_lsb(self):
        mobile, password = self.mobile.get().strip(), self.password.get()
        def done(credentials):
            self.lsb = credentials
            self.lsb_platform.uid, self.lsb_platform.sid = credentials["uid"], credentials["sid"]
            LSB_SESSION_FILE.write_text(json.dumps({**credentials, "cookies": self.lsb_platform.session.cookies.get_dict()}, ensure_ascii=False, indent=2), encoding="utf-8")
            self.password.delete(0, "end")
        def action():
            return self.lsb_platform.login(mobile, password)
        self._run("料商宝登录", action, done)

    def login_yiliao(self):
        account, password = self.y_account.get().strip(), self.y_password.get()
        def done(_result):
            self.y_password.delete(0, "end")
            self.load_children()
        self._run("壹料登录", lambda: self.yiliao.login(account, password), done)

    def load_children(self):
        if not self.yiliao.logged_in: return
        def done(groups):
            self.child_accounts = groups; self.child_list.delete(0, "end")
            for group in groups: self.child_list.insert("end", "{} | {}".format(group["groupRelateName"], group["groupRelateId"]))
        def action():
            return self.yiliao.child_accounts()
        self._run("加载壹料子账号", action, done)

    def add_images(self, widget):
        paths = filedialog.askopenfilenames(title="选择图片", filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")])
        if paths:
            attachments = self._attachments_for(widget)
            for path in paths:
                token = uuid.uuid4().hex
                attachments.append((token, str(path)))
                widget.insert("insert", "\n[图片:{}|{}]\n".format(token, Path(path).name))
            self._log("已加入 {} 张图片附件；发布时由目标平台分别上传。".format(len(paths)))

    def _attachments_for(self, widget):
        return self.publish_images if widget is self.body else self.edit_images

    @staticmethod
    def _clipboard_path(value):
        raw = unquote(str(value).strip())
        if raw.lower().startswith("file:"):
            raw = raw[5:].lstrip("/\\")
            if re.match(r"^[A-Za-z]:[/\\]", raw):
                pass
            elif re.match(r"^[A-Za-z]:[/\\]", raw[1:]):
                raw = raw[1:]
        return Path(raw)

    def paste_image(self, event, widget):
        """微信复制的图片文件或位图变成附件标记，不把路径粘到文章正文。"""
        try:
            data = ImageGrab.grabclipboard()
        except Exception as exc:
            self._log("读取剪贴板失败：{}".format(exc))
            return None
        path = None
        if isinstance(data, (list, tuple)):
            path = next((self._clipboard_path(p) for p in data
                         if self._clipboard_path(p).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
                         and self._clipboard_path(p).is_file()), None)
        elif data is not None and hasattr(data, "save"):
            handle = tempfile.NamedTemporaryFile(prefix="publisher_clip_", suffix=".png", delete=False)
            path = Path(handle.name); handle.close()
            try:
                data.save(str(path), format="PNG")
            except Exception as exc:
                path.unlink(missing_ok=True)
                self._log("剪贴板图片处理失败：{}".format(exc))
                return "break"
        if path is None:
            return None  # Clipboard contains text; retain the normal paste behavior.
        token = uuid.uuid4().hex
        self._attachments_for(widget).append((token, str(path)))
        widget.insert("insert", "\n[图片:{}|{}]\n".format(token, path.name))
        self._log("已添加剪贴板图片附件：{}".format(path.name))
        return "break"

    @staticmethod
    def _strip_image_markers(raw):
        return re.sub(r"\n?\[图片:(?:[0-9a-f]{32}\|)?[^\]]+\]\n?", "\n", raw).strip()

    def _platform_content(self, platform, raw, attachments):
        # Marker tokens never expose local paths to the article content.
        attachment_by_token = {token: path for token, path in attachments}
        tokens = re.findall(r"\[图片:([0-9a-f]{32})\|[^\]]+\]", raw)
        text = self._strip_image_markers(raw)
        if platform == "壹料":
            if text and any(token in attachment_by_token for token in tokens):
                text = self.yiliao._html(text)
            for token in tokens:
                path = attachment_by_token.get(token)
                if path:
                    url = self.yiliao.upload_image(path)
                    text += '<p><img src="{}" alt="" data-href="" style=""/></p>'.format(url)
        return text

    def _clear_used_images(self, widget, attribute, used):
        used_tokens = {token for token, _path in used}
        remaining = [(token, path) for token, path in getattr(self, attribute) if token not in used_tokens]
        setattr(self, attribute, remaining)
        if used_tokens:
            content = widget.get("1.0", "end-1c")
            for token in used_tokens:
                content = re.sub(r"\n?\[图片:{}\|[^\]]+\]\n?".format(re.escape(token)), "\n", content)
            widget.delete("1.0", "end")
            widget.insert("1.0", content)

    def publish(self):
        title, free_content = self.title.get().strip(), self.free.get().strip()
        if not title: messagebox.showwarning("缺少标题", "请填写文章标题。"); return
        if self.pub_y.get() and not self.yiliao.logged_in: messagebox.showwarning("壹料未登录", "请先单独登录壹料。"); return
        if self.pub_l.get() and not self.lsb.get("sid"): messagebox.showwarning("料商宝未登录", "请先单独登录料商宝。"); return
        raw = self.body.get("1.0", "end-1c"); price = self.price.get().strip()
        images = tuple(self.publish_images)
        do_y, do_l = bool(self.pub_y.get()), bool(self.pub_l.get())
        selected = [self.child_accounts[i]["groupRelateId"] for i in self.child_list.curselection()] if hasattr(self, "child_accounts") else []
        def action():
            results = []
            if do_y:
                content = self._platform_content("壹料", raw, images)
                data = self.yiliao.publish({"title":title,"subtitle":self.subtitle.get().strip(),"summary":free_content,"free_content":free_content,"content":content,"price":price,"tags":self.label.get().strip(),"discount_enabled":bool(self.discount.get()),"presale":self.presale.get()}, child_ids=selected)
                pid = data.get("id")
                if not pid: raise ApiError("壹料发布未返回文章 ID：{}".format(data))
                self._save_mapping("壹料", title, pid, price); results.append("壹料 ID={}".format(pid))
            if do_l:
                clean_content = self._strip_image_markers(raw)
                article = {"title": title, "subtitle": self.subtitle.get().strip(), "shortMsg": free_content, "free_content": free_content, "content": clean_content,
                           "summary":free_content,"price": price, "label": self.label.get(), "presale": self.presale.get(), "discount_enabled":bool(self.discount.get())}
                result = self.lsb_platform.publish(article, [path for _token, path in images])
                if not isinstance(result, dict) or result.get("status") != 200: raise ApiError("料商宝发布失败：{}".format(result))
                self._save_mapping("料商宝", title, result.get("data") or result.get("msg") or "", price)
                results.append("料商宝: {}".format(result.get("msg")))
            return "; ".join(results)
        if not messagebox.askyesno("确认发布", "确认发布到所选平台？料商宝同步按平台当前设置执行，壹料同步到已勾选子账号。"):
            return
        self._run("统一发布", action, lambda _result: self._clear_used_images(self.body, "publish_images", images))

    def refresh_map(self):
        if not hasattr(self, "maplist"): return
        self.maplist.delete(0, "end")
        query = self.map_search.get().strip().lower() if hasattr(self, "map_search") else ""
        for record in self.mapping:
            ids = record.get("ids", {})
            display = "{} | 壹料:{} | 料商宝:{}".format(record.get("title", ""), ids.get("壹料", "-"), ids.get("料商宝", "-"))
            if not query or query in display.lower():
                self.maplist.insert("end", display)

    def select_mapping(self, _event=None):
        selection = self.maplist.curselection()
        if selection:
            query = self.map_search.get().strip().lower()
            visible = [row for row in self.mapping if not query or query in (row.get("title", "") + " " + " ".join(row.get("ids", {}).values())).lower()]
            record = visible[selection[0]]
            self.selected_article = record
            ids = record.get("ids", {})
            self.edit_id.delete(0, "end"); self.edit_id.insert(0, "壹料: {}    料商宝: {}".format(ids.get("壹料", "-"), ids.get("料商宝", "-")))
            self.edit_title.delete(0, "end"); self.edit_title.insert(0, record["title"])
            self.edit_price.delete(0, "end")
            self.edit_price.insert(0, str(record.get("price", "")))
            self.edit_subtitle.delete(0, "end")

    def update(self):
        record = getattr(self, "selected_article", None)
        if not record:
            messagebox.showwarning("请选择文章", "请先搜索并选择要修改的文章标题。")
            return
        ids = record.get("ids", {})
        targets = {name: article_id for name, article_id in ids.items() if article_id and article_id != "-"}
        title, free_content = self.edit_title.get(), self.edit_summary.get()
        raw, price = self.edit_body.get("1.0", "end-1c"), self.edit_price.get().strip()
        price = price or str(record.get("price", "")).strip()
        if "料商宝" in targets and not price:
            messagebox.showwarning("缺少原价", "这篇历史文章没有保存价格，请填写料商宝上的原价后再更新。")
            return
        images = tuple(self.edit_images)
        article = {"title": title, "summary": free_content, "free_content": free_content,
                   "content": raw, "price": price,
                   "subtitle": self.edit_subtitle.get().strip(),
                   "presale": int(bool(self.edit_presale.get())),
                   "discount_enabled": bool(self.edit_discount.get())}
        def action():
            outcomes = []
            if "壹料" in targets:
                content = self._platform_content("壹料", raw, images)
                self.yiliao.update(targets["壹料"], {**article, "content": content})
                outcomes.append("壹料 {} 已修改并触发更新同步".format(targets["壹料"]))
            if "料商宝" in targets:
                clean_content = self._strip_image_markers(raw)
                response = self.lsb_platform.update(targets["料商宝"], {**article, "content": clean_content,
                    "label": self.label.get().strip()}, [path for _token, path in images])
                outcomes.append("料商宝 {} 已更新：{}（子账号同步由平台处理）".format(
                    targets["料商宝"], response.get("msg", "接口已接受")))
            return "；".join(outcomes)
        if not targets:
            messagebox.showwarning("缺少平台文章 ID", "所选标题没有关联到可修改的平台文章 ID。")
            return
        if "壹料" in targets and not self.yiliao.logged_in:
            messagebox.showwarning("壹料未登录", "该标题关联壹料文章，请先登录壹料。")
            return
        if "料商宝" in targets and not self.lsb_platform.logged_in:
            messagebox.showwarning("料商宝未登录", "该标题关联料商宝文章，请先登录料商宝。")
            return
        sync_note = "壹料修改成功后会自动同步给子账号；料商宝按平台自身同步设置处理。" if "壹料" in targets else "料商宝按平台自身同步设置处理。"
        if not messagebox.askyesno("确认更新并同步", "将更新《{}》对应的已发布平台文章：{}。\n{}\n继续吗？".format(title, "、".join(targets), sync_note)):
            return
        def finish(_result):
            self._clear_used_images(self.edit_body, "edit_images", images)
            record["title"] = title
            if price:
                record["price"] = price
            ARTICLE_MAP_FILE.write_text(json.dumps(self.mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            self.refresh_map()
        self._run("统一更新并同步", action, finish)

    def change_top(self, pin):
        record = getattr(self, "selected_article", None)
        if not record:
            messagebox.showwarning("请选择文章", "请先搜索并选择要操作的文章标题。")
            return
        targets = {name: article_id for name, article_id in record.get("ids", {}).items()
                   if article_id and article_id != "-"}
        if not targets:
            messagebox.showwarning("缺少平台文章 ID", "所选标题没有关联的平台文章 ID。")
            return
        if "壹料" in targets and not self.yiliao.logged_in:
            messagebox.showwarning("壹料未登录", "该标题关联壹料文章，请先登录壹料。")
            return
        if "料商宝" in targets and not self.lsb_platform.logged_in:
            messagebox.showwarning("料商宝未登录", "该标题关联料商宝文章，请先登录料商宝。")
            return
        operation = "置顶" if pin else "取消置顶"
        if not messagebox.askyesno("确认{}".format(operation), "对《{}》所有已关联平台执行{}？".format(record.get("title", ""), operation)):
            return
        def action():
            outcomes = []
            if "壹料" in targets:
                self.yiliao.set_weight(targets["壹料"], 5000 if pin else 0)
                outcomes.append("壹料 {} 成功".format(operation))
            if "料商宝" in targets:
                response = self.lsb_platform.set_top(targets["料商宝"])
                outcomes.append("料商宝：{}".format(response.get("msg", "已请求")))
            return "；".join(outcomes)
        self._run("统一{}".format(operation), action)


if __name__ == "__main__":
    UnifiedPublisher().mainloop()
