"""壹料文章发布工具（PC 端轻量版）。运行：python main.py"""
import json
import re
import mimetypes
import queue
import tempfile
import threading
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from PIL import ImageGrab

import requests

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "session.json"
ARTICLE_HISTORY_FILE = BASE_DIR / "article_history.json"
EXPERT_USER_FILE = BASE_DIR / "expert_user_map.json"
MERCHANTS_FILE = BASE_DIR / "merchant_groups.json"
LOGIN_URL = "https://yapi.njyuelu.cn/mgr/mgr/login"
PUBLISH_URL = "https://yapi.njyuelu.cn/plan/mgr-do/add"
SYNC_URL = "https://yapi.njyuelu.cn/plan/mgr-do/planSynAdd"
MODIFY_URL = "https://yapi.njyuelu.cn/plan/mgr-do/modifyContent"
SYNC_UPDATE_URL = "https://yapi.njyuelu.cn/plan/mgr-do/planSynUpdate"
IMAGE_UPLOAD_URL = "https://yapi.njyuelu.cn/resource/rse-img-do/uploads"
EXPERT_INFO_URL = "https://yapi.njyuelu.cn/plan/mgr-expert-do/expertInfo"
USER_GROUP_URL = "https://yapi.njyuelu.cn/mgr/sys-group/userGroupList"
USER_INFO_URL = "https://yapi.njyuelu.cn/mgr/sys-user-do/userInfo"
HEADERS = {"Content-Type": "application/json", "User-Agent": "YiliaoPublisher/1.0"}


class ApiError(RuntimeError):
    pass


class ArticleHistory:
    """保存本工具成功发布过的文章标题与方案 ID，不保存正文。"""
    def __init__(self):
        self.items = []
        try:
            self.items = json.loads(ARTICLE_HISTORY_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    def save(self, title, plan_id):
        record = {"title": title.strip(), "plan_id": str(plan_id), "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self.items = [x for x in self.items if x.get("plan_id") != record["plan_id"]]
        self.items.insert(0, record)
        ARTICLE_HISTORY_FILE.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")

    def search(self, keyword=""):
        keyword = keyword.strip().lower()
        return [x for x in self.items if not keyword or keyword in x.get("title", "").lower() or keyword in x.get("plan_id", "").lower()]


class ExpertUserMap:
    """本地保存 expertId 到平台 userId 的映射，供后续用户查询使用。"""
    def __init__(self):
        try:
            self.items = json.loads(EXPERT_USER_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.items = {}

    def save(self, expert_info):
        expert_id = expert_info.get("id")
        user_id = expert_info.get("userId")
        if not expert_id or not user_id:
            raise ApiError("专家信息返回中缺少 id 或 userId，未保存映射。")
        self.items[str(expert_id)] = {
            "expertId": str(expert_id), "userId": str(user_id),
            "name": expert_info.get("name", ""),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        EXPERT_USER_FILE.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.items[str(expert_id)]

    def get(self, expert_id):
        return self.items.get(str(expert_id), {})


class MerchantStore:
    """以平台返回的 groupRelateId 为键保存子商户列表。"""
    def __init__(self):
        try:
            self.items = json.loads(MERCHANTS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.items = {}

    def save(self, expert_id, groups):
        active = {}
        for group in groups or []:
            relate_id = group.get("groupRelateId")
            if relate_id and int(group.get("status", 1)) == 1:
                active[str(relate_id)] = {
                    "name": group.get("groupRelateName") or group.get("groupName") or str(relate_id),
                    "groupRelateId": str(relate_id),
                }
        self.items[str(expert_id)] = list(active.values())
        MERCHANTS_FILE.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.items[str(expert_id)]

    def get(self, expert_id):
        return self.items.get(str(expert_id), [])


class YiliaoApi:
    def __init__(self):
        self.http = requests.Session()
        self.user = {}
        self.load_cache()

    @property
    def logged_in(self):
        return bool(self.user.get("token"))

    def load_cache(self):
        try:
            saved = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            self.user = saved.get("user_data", {})
            self.http.cookies.update(saved.get("cookies", {}))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.user = {}

    def _headers(self):
        headers = HEADERS.copy()
        if self.logged_in:
            headers["Authorization"] = self.user["token"]
        return headers

    def _post(self, url, data, wrap_data=True):
        try:
            payload = {"d": data} if wrap_data else {"d": data}
            # Most APIs accept d as an object; expertInfo specifically expects
            # the scalar expert ID at the root's d field.
            response = self.http.post(url, json=payload, headers=self._headers(), timeout=15)
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ApiError("网络请求失败：{}".format(exc)) from exc
        if not isinstance(result, dict):
            raise ApiError("接口返回格式异常：{}".format(url))
        if result.get("c") != 200:
            message = result.get("m") or "服务器未返回失败原因"
            if result.get("c") in (401, 403) or "未登录" in str(message):
                self.clear_cache()
            raise ApiError("操作失败：{}".format(message))
        return result.get("d")

    def login(self, account, password):
        if not account.strip() or not password:
            raise ApiError("请输入账号和密码。")
        data = self._post(LOGIN_URL, {"account": account.strip(), "pwd": password, "proxyTag": ""})
        self.user = data or {}
        try:
            CACHE_FILE.write_text(json.dumps({"user_data": self.user, "cookies": self.http.cookies.get_dict()}, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            raise ApiError("登录成功，但无法保存登录状态：{}".format(exc))
        return self.user

    def clear_cache(self):
        self.user = {}
        self.http.cookies.clear()
        try:
            CACHE_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _html(value):
        value = value.strip()
        # Text widgets may contain plain text mixed with the platform's image
        # fragments. Preserve those tags and wrap only the surrounding text.
        if "<img" in value.lower():
            parts = re.split(r'(<p>\s*<img\b[^>]*?/?>\s*</p>)', value, flags=re.IGNORECASE)
            rendered = []
            for part in parts:
                if not part:
                    continue
                if re.fullmatch(r'<p>\s*<img\b[^>]*?/?>\s*</p>', part, flags=re.IGNORECASE):
                    rendered.append(part)
                elif part.startswith("<"):
                    rendered.append(part)
                else:
                    text = escape(part).replace("\n", "<br>")
                    if text.strip():
                        rendered.append("<p>{}</p>".format(text))
            return "".join(rendered)
        if value.startswith("<"):
            return value
        return "<p>{}</p>".format(escape(value).replace("\n", "<br>"))

    def publish(self, title, summary, content, price, tags, no_discount=1, presell=1):
        if not self.logged_in:
            raise ApiError("请先登录。")
        if not title.strip() or not content.strip():
            raise ApiError("标题和正文不能为空。")
        try:
            price = str(float(price))
        except ValueError as exc:
            raise ApiError("价格必须是数字。") from exc
        now, expiry = datetime.now(), datetime.now() + timedelta(hours=24)
        tag_list = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        data = {
            "id": "", "appPush": 1, "planPackAuto": 1, "planPacks": "", "noDiscount": int(bool(no_discount)), "notifyAuto": 0, "items": "",
            "title": title.strip(), "title2": "", "summary": self._html(summary), "content": self._html(content), "free": 0, "needPay": 1,
            "price": price, "priceReal": price, "publicTime": now.strftime("%Y-%m-%d %H:%M:%S"), "endTime": expiry.strftime("%Y-%m-%d %H:%M:%S"),
            "activityId": None, "sportsId": 4, "expertId": self.user.get("expertId"), "tag1": "", "tag2": "", "tags": ",".join(tag_list),
            "labelIds": "", "playType": "9001", "tagsArray": tag_list, "presell": int(bool(presell)), "updateTimeShow": 0,
            "beginTime": expiry.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return self._post(PUBLISH_URL, data)

    def sync(self, plan_id, expert_ids):
        if isinstance(expert_ids, str):
            ids = [x.strip() for x in expert_ids.replace("，", ",").replace("\n", ",").split(",") if x.strip()]
        else:
            ids = [str(x).strip() for x in (expert_ids or []) if str(x).strip()]
        return self._post(SYNC_URL, {"planId": plan_id, "expertIdList": ids}) if ids else None

    def modify_content(self, plan_id, content, price):
        if not plan_id.strip() or not content.strip():
            raise ApiError("请填写方案 ID 和更新正文。")
        expiry = datetime.now() + timedelta(hours=24)
        data = {
            "id": plan_id.strip(), "expertId": self.user.get("expertId"), "compType": "1", "publicTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "lotteryType": 6, "issueNo": None, "price": price.strip(), "priceReal": price.strip(),
            "beginTime": expiry.strftime("%Y-%m-%d %H:%M:%S"), "endTime": expiry.strftime("%Y-%m-%d %H:%M:%S"), "content": self._html(content),
            "playType": "9001", "planType": None, "hidden": 0, "free": 0, "matchs": None, "status": 0, "verifyStatus": 2,
            "verifyMsg": None, "activityId": 0, "sportsId": 4, "notifyAuto": 0, "noDiscount": 1, "tags": "", "planPackAuto": 0,
            "planPacks": "", "presell": 1, "updateTimeShow": 0, "qrcodeList": [],
        }
        return self._post(MODIFY_URL, data)

    def sync_update(self, plan_id):
        return self._post(SYNC_UPDATE_URL, {"planId": plan_id.strip()})

    def set_plan_weight(self, plan_id, weight):
        if not str(plan_id).strip():
            raise ApiError("请先选择或填写方案 ID。")
        try:
            numeric_id = int(plan_id)
        except (TypeError, ValueError) as exc:
            raise ApiError("方案 ID 必须是数字。") from exc
        result = self._post(MODIFY_URL, {"id": numeric_id, "weight": int(weight)})
        if result is not True:
            raise ApiError("修改置顶状态失败，接口返回：{}".format(result))
        return result

    def expert_info(self):
        expert_id = self.user.get("expertId")
        if not expert_id:
            raise ApiError("当前登录信息中没有 expertId。")
        info = self._post(EXPERT_INFO_URL, expert_id)
        if not isinstance(info, dict):
            raise ApiError("expertInfo 返回内容不是专家信息对象，请检查接口响应。")
        return info

    def user_groups(self, user_id):
        # This endpoint's DTO declares userId as an integer. The opaque U...
        # identifier returned by expertInfo cannot be used for this parameter.
        try:
            numeric_user_id = int(user_id)
        except (TypeError, ValueError) as exc:
            raise ApiError("子商户接口要求数字 userId；当前账号信息中的 userId 是 {}。请提供接口请求里数字 userId（例如 435）的来源。".format(user_id)) from exc
        groups = self._post(USER_GROUP_URL, {"tag1": 2, "groupType": 1, "userId": numeric_user_id})
        if not isinstance(groups, list):
            raise ApiError("userGroupList 返回内容不是列表，请检查接口响应。")
        return groups

    def user_info(self):
        """该接口不需要业务请求参数，返回当前登录用户及 groupList。"""
        try:
            response = self.http.post(USER_INFO_URL, headers=self._headers(), timeout=15)
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ApiError("获取当前用户信息失败：{}".format(exc)) from exc
        if not isinstance(result, dict) or result.get("c") != 200:
            raise ApiError("获取当前用户信息失败：{}".format(result.get("m") if isinstance(result, dict) else "返回格式异常"))
        info = result.get("d")
        if not isinstance(info, dict):
            raise ApiError("userInfo 返回内容不是用户信息对象。")
        return info

    def upload_image(self, image_path):
        """上传本地图片并返回平台返回的公开图片 URL。"""
        if not self.logged_in:
            raise ApiError("请先登录后再上传图片。")
        image_path = Path(image_path)
        if not image_path.is_file():
            raise ApiError("图片文件不存在：{}".format(image_path))
        content_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
        headers = self._headers()
        headers.pop("Content-Type", None)  # requests 会自动生成 multipart boundary
        try:
            with image_path.open("rb") as image_file:
                response = self.http.post(
                    IMAGE_UPLOAD_URL,
                    data={"path": "resource"},
                    files={"files": (image_path.name, image_file, content_type)},
                    headers=headers,
                    timeout=30,
                )
            response.raise_for_status()
            result = response.json()
        except (OSError, requests.RequestException, ValueError) as exc:
            raise ApiError("图片上传失败：{}".format(exc)) from exc
        if result.get("c") != 200:
            raise ApiError("图片上传失败：{}".format(result.get("m") or "服务器未返回失败原因"))
        url = self._find_image_url(result.get("d"))
        if not url:
            raise ApiError("图片已上传，但无法从返回数据中识别图片 URL：{}".format(result.get("d")))
        return url

    @staticmethod
    def _find_image_url(value):
        """兼容上传接口可能返回字符串、对象或对象列表的情况。"""
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
        if isinstance(value, dict):
            for key in ("url", "src", "path", "fileUrl", "filePath", "resourceUrl"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                    return candidate
            for candidate in value.values():
                url = YiliaoApi._find_image_url(candidate)
                if url:
                    return url
        if isinstance(value, list):
            for candidate in value:
                url = YiliaoApi._find_image_url(candidate)
                if url:
                    return url
        return None


class PublisherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.api, self.events, self.history, self.expert_users, self.merchants = YiliaoApi(), queue.Queue(), ArticleHistory(), ExpertUserMap(), MerchantStore()
        self.title("壹料文章发布工具")
        self.geometry("960x720")
        self.minsize(800, 600)
        self._build()
        self._refresh_user()
        self.after(100, self._drain_events)
        # Cached sessions skip the login button, so load account and merchant
        # mappings on startup as well.
        if self.api.logged_in:
            self.after(300, self.fetch_groups)

    def _build(self):
        ttk.Style(self).configure("Title.TLabel", font=("Microsoft YaHei UI", 15, "bold"))
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        head = ttk.Frame(container); head.pack(fill="x")
        ttk.Label(head, text="壹料文章发布工具", style="Title.TLabel").pack(side="left")
        self.user_label = ttk.Label(head, text="未登录"); self.user_label.pack(side="right")
        self.account_info_label = ttk.Label(container, text="专家 userId：未查询")
        self.account_info_label.pack(anchor="e")
        auth = ttk.LabelFrame(container, text="账号登录", padding=10); auth.pack(fill="x", pady=(12, 8))
        ttk.Label(auth, text="账号").grid(row=0, column=0); self.account = ttk.Entry(auth, width=22); self.account.grid(row=0, column=1, padx=(6, 16))
        ttk.Label(auth, text="密码").grid(row=0, column=2); self.password = ttk.Entry(auth, width=22, show="●"); self.password.grid(row=0, column=3, padx=6)
        ttk.Button(auth, text="登录", command=self.login).grid(row=0, column=4, padx=(10, 4)); ttk.Button(auth, text="退出登录", command=self.logout).grid(row=0, column=5)
        tabs = ttk.Notebook(container); tabs.pack(fill="both", expand=True)
        self.publish_tab, self.edit_tab = ttk.Frame(tabs, padding=12), ttk.Frame(tabs, padding=12)
        tabs.add(self.publish_tab, text="发布文章"); tabs.add(self.edit_tab, text="编辑已发布文章")
        self._build_publish(); self._build_edit()
        self.log = scrolledtext.ScrolledText(container, height=7, state="disabled", font=("Consolas", 9)); self.log.pack(fill="x", pady=(10, 0))

    def _build_publish(self):
        tab = self.publish_tab; tab.columnconfigure(1, weight=1); tab.rowconfigure(2, weight=1)
        ttk.Label(tab, text="标题 *").grid(row=0, column=0, sticky="nw", pady=5); self.title_entry = ttk.Entry(tab); self.title_entry.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(tab, text="摘要").grid(row=1, column=0, sticky="nw", pady=5); self.summary = tk.Text(tab, height=3, wrap="word"); self.summary.grid(row=1, column=1, sticky="nsew", pady=5)
        body_label = ttk.Frame(tab); body_label.grid(row=2, column=0, sticky="nw", pady=5)
        ttk.Label(body_label, text="正文 *\n复制图片后 Ctrl+V 上传").pack(anchor="w")
        ttk.Button(body_label, text="上传本地图片", command=lambda: self.upload_local_image(self.content)).pack(anchor="w", pady=(8, 0))
        ttk.Button(body_label, text="插入图片链接", command=lambda: self.insert_image(self.content)).pack(anchor="w", pady=(8, 0))
        self.content = tk.Text(tab, height=12, wrap="word"); self.content.grid(row=2, column=1, sticky="nsew", pady=5)
        self.content.bind("<Control-v>", lambda event: self.paste_image_from_clipboard(event, self.content), add="+")
        options = ttk.Frame(tab); options.grid(row=3, column=1, sticky="ew", pady=8)
        ttk.Label(options, text="价格").pack(side="left"); self.price = ttk.Entry(options, width=10); self.price.insert(0, "12"); self.price.pack(side="left", padx=(5, 16))
        ttk.Label(options, text="标签（逗号分隔）").pack(side="left"); self.tags = ttk.Entry(options); self.tags.pack(side="left", fill="x", expand=True, padx=5)
        self.no_discount_var = tk.IntVar(value=1)
        self.presell_var = tk.IntVar(value=1)
        ttk.Checkbutton(options, text="无折扣", variable=self.no_discount_var).pack(side="left", padx=(8, 2))
        ttk.Checkbutton(options, text="预售", variable=self.presell_var).pack(side="left", padx=2)
        ttk.Label(tab, text="同步专家 ID\n（可选，逗号或换行分隔）").grid(row=4, column=0, sticky="nw", pady=5); self.sync_ids = tk.Text(tab, height=3, wrap="word"); self.sync_ids.grid(row=4, column=1, sticky="ew", pady=5)
        group_box = ttk.LabelFrame(tab, text="选择同步子商户（可选）", padding=6); group_box.grid(row=5, column=1, sticky="ew", pady=5)
        self.group_list = tk.Listbox(group_box, selectmode="multiple", height=4, exportselection=False)
        self.group_list.pack(side="left", fill="both", expand=True)
        ttk.Button(group_box, text="刷新商户列表", command=self.fetch_groups).pack(side="left", padx=8)
        ttk.Button(tab, text="发布文章", command=self.publish).grid(row=6, column=1, sticky="e", pady=(8, 0))

    def _build_edit(self):
        tab = self.edit_tab; tab.columnconfigure(1, weight=1); tab.rowconfigure(3, weight=1)
        history = ttk.LabelFrame(tab, text="已发布文章（本工具自动记录）", padding=6); history.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        history.columnconfigure(1, weight=1)
        ttk.Label(history, text="搜索标题 / ID").grid(row=0, column=0, sticky="w")
        self.search_history = ttk.Entry(history); self.search_history.grid(row=0, column=1, sticky="ew", padx=6); self.search_history.bind("<KeyRelease>", lambda _event: self.refresh_history())
        ttk.Button(history, text="刷新", command=self.refresh_history).grid(row=0, column=2)
        self.article_list = ttk.Treeview(history, columns=("title", "id", "time"), show="headings", height=4)
        self.article_list.heading("title", text="文章标题"); self.article_list.heading("id", text="方案 ID"); self.article_list.heading("time", text="发布时间")
        self.article_list.column("title", width=280); self.article_list.column("id", width=250); self.article_list.column("time", width=145)
        self.article_list.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0)); self.article_list.bind("<<TreeviewSelect>>", self.select_article)
        ttk.Label(tab, text="方案 ID *").grid(row=1, column=0, sticky="nw", pady=5); self.plan_id = ttk.Entry(tab); self.plan_id.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(tab, text="新价格\n（留空则按接口默认）").grid(row=2, column=0, sticky="nw", pady=5); self.new_price = ttk.Entry(tab); self.new_price.grid(row=2, column=1, sticky="ew", pady=5)
        body_label = ttk.Frame(tab); body_label.grid(row=3, column=0, sticky="nw", pady=5)
        ttk.Label(body_label, text="更新正文 *\n复制图片后 Ctrl+V 上传").pack(anchor="w")
        ttk.Button(body_label, text="上传本地图片", command=lambda: self.upload_local_image(self.new_content)).pack(anchor="w", pady=(8, 0))
        ttk.Button(body_label, text="插入图片链接", command=lambda: self.insert_image(self.new_content)).pack(anchor="w", pady=(8, 0))
        self.new_content = tk.Text(tab, height=14, wrap="word"); self.new_content.grid(row=3, column=1, sticky="nsew", pady=5)
        self.new_content.bind("<Control-v>", lambda event: self.paste_image_from_clipboard(event, self.new_content), add="+")
        controls = ttk.Frame(tab); controls.grid(row=4, column=1, sticky="e", pady=(8, 0))
        ttk.Button(controls, text="仅更新内容", command=lambda: self.update(False)).pack(side="left", padx=6); ttk.Button(controls, text="更新并同步", command=lambda: self.update(True)).pack(side="left", padx=6)
        ttk.Button(controls, text="置顶文章", command=lambda: self.set_pin_weight(5000, "置顶文章")).pack(side="left", padx=6)
        ttk.Button(controls, text="取消置顶", command=lambda: self.set_pin_weight(0, "取消置顶")).pack(side="left")
        self.refresh_history()

    def _run(self, label, action, on_ok=None):
        def worker():
            try: self.events.put(("ok", label, action(), on_ok))
            except Exception as exc: self.events.put(("error", label, str(exc), None))
        self._write(label + "处理中…"); threading.Thread(target=worker, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                kind, label, value, callback = self.events.get_nowait()
                if kind == "ok":
                    self._write(label + "成功。")
                    if callback: callback(value)
                else:
                    self._write("{}失败：{}".format(label, value)); messagebox.showerror("操作失败", value)
        except queue.Empty: pass
        self.after(100, self._drain_events)

    def _write(self, text):
        self.log.configure(state="normal"); self.log.insert("end", "[{}] {}\n".format(datetime.now().strftime("%H:%M:%S"), text)); self.log.see("end"); self.log.configure(state="disabled")

    def _refresh_user(self):
        text = "已登录：{}（{}）".format(self.api.user.get("name") or self.api.user.get("account"), self.api.user.get("expertId", "")) if self.api.logged_in else "未登录"
        self.user_label.configure(text=text)
        expert_id = self.api.user.get("expertId", "")
        cached = self.expert_users.get(expert_id) if expert_id else {}
        self.account_info_label.configure(text="专家 userId：{}{}".format(cached.get("userId", "未查询"), "（{}）".format(cached.get("name")) if cached.get("name") else ""))

    def insert_image(self, text_widget):
        """把公网图片地址作为 HTML 图片标签插入当前位置。"""
        url = simpledialog.askstring("插入图片", "请输入可公开访问的图片 URL：", parent=self)
        if not url:
            return
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("图片地址无效", "图片地址必须以 http:// 或 https:// 开头。")
            return
        self._insert_image_html(text_widget, url)
        self._write("已按平台富文本格式插入图片。")

    def _insert_image_html(self, text_widget, url):
        image_html = '<p><img src="{}" alt="" data-href="" style=""/></p>'.format(escape(url, quote=True))
        text_widget.insert("insert", image_html)

    def upload_local_image(self, text_widget):
        image_path = filedialog.askopenfilename(
            title="选择要上传的图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"), ("所有文件", "*.*")],
            parent=self,
        )
        if not image_path:
            return

        def done(url):
            self._insert_image_html(text_widget, url)
            self._write("图片上传成功，已插入正文：{}".format(url))

        self._run("上传图片", lambda: self.api.upload_image(image_path), done)

    def paste_image_from_clipboard(self, event, text_widget):
        """上传剪贴板位图或微信复制的图片文件路径；普通文本走默认粘贴。"""
        try:
            clipboard_data = ImageGrab.grabclipboard()
        except Exception as exc:
            self._write("读取剪贴板图片失败：{}".format(exc))
            return None
        image_path = None
        cleanup_path = False
        if isinstance(clipboard_data, (list, tuple)):
            # Windows clipboard may expose copied files as a list of paths.
            image_path = next((Path(p) for p in clipboard_data if Path(str(p)).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp") and Path(str(p)).is_file()), None)
        elif clipboard_data is not None and hasattr(clipboard_data, "save"):
            with tempfile.NamedTemporaryFile(prefix="yiliao_clip_", suffix=".png", delete=False) as temp_file:
                image_path = Path(temp_file.name)
            cleanup_path = True
            try:
                clipboard_data.save(str(image_path), format="PNG")
            except Exception as exc:
                try:
                    image_path.unlink()
                except OSError:
                    pass
                self._write("无法读取剪贴板图片：{}".format(exc))
                return "break"
        if image_path is None:
            return None  # Not an image; let Tk paste ordinary clipboard text.

        def done(url):
            self._insert_image_html(text_widget, url)
            self._write("剪贴板图片已上传并插入正文。")

        def upload_and_clean():
            try:
                return self.api.upload_image(image_path)
            finally:
                if cleanup_path:
                    try:
                        image_path.unlink()
                    except OSError:
                        pass

        self._run("上传剪贴板图片", upload_and_clean, done)
        return "break"

    def refresh_history(self):
        if not hasattr(self, "article_list"):
            return
        for item in self.article_list.get_children():
            self.article_list.delete(item)
        keyword = self.search_history.get() if hasattr(self, "search_history") else ""
        for record in self.history.search(keyword):
            self.article_list.insert("", "end", values=(record.get("title", ""), record.get("plan_id", ""), record.get("published_at", "")))

    def select_article(self, _event=None):
        selected = self.article_list.selection()
        if not selected:
            return
        values = self.article_list.item(selected[0], "values")
        if values:
            self.plan_id.delete(0, "end")
            self.plan_id.insert(0, values[1])
            self._write("已选择《{}》（方案 ID：{}）。".format(values[0], values[1]))

    def login(self):
        def done(user):
            self._refresh_user(); self.password.delete(0, "end"); self._write("当前账号：{}".format(user.get("account", "")))
            self.fetch_groups()
        self._run("登录", lambda: self.api.login(self.account.get(), self.password.get()), done)

    def fetch_expert_info(self):
        def done(info):
            record = self.expert_users.save(info)
            self._refresh_user()
            self._write("已保存专家 {} 对应的 userId：{}".format(record.get("name") or record["expertId"], record["userId"]))
        self._run("获取账号信息", self.api.expert_info, done)

    def fetch_groups(self):
        def load_groups(user):
            expert_id = user.get("expertId") or self.api.user.get("expertId", "")
            user_id = user.get("id")
            if not user_id:
                raise ApiError("userInfo 返回中没有数字 id，无法加载子商户。")
            groups = user.get("groupList")
            if groups is None:
                groups = self.api.user_groups(user_id)
            return expert_id, user_id, groups

        def done(data):
            expert_id, user_id, groups = data
            saved = self.merchants.save(expert_id, groups)
            self.expert_users.items[str(expert_id)] = {
                "expertId": str(expert_id), "userId": user_id,
                "name": self.api.user.get("name", ""),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            EXPERT_USER_FILE.write_text(json.dumps(self.expert_users.items, ensure_ascii=False, indent=2), encoding="utf-8")
            self.group_list.delete(0, "end")
            for merchant in saved:
                self.group_list.insert("end", "{}  |  {}".format(merchant["name"], merchant["groupRelateId"]))
            self._write("已获取数字 userId={}，并加载 {} 个子商户。".format(user_id, len(saved)))
            self._refresh_user()
        def action():
            user = self.api.user_info()
            return load_groups(user)
        self._run("加载用户及子商户", action, done)

    def logout(self):
        self.api.clear_cache(); self._refresh_user(); self._write("已退出登录并清除本地登录状态。")

    def publish(self):
        def action():
            result = self.api.publish(
                self.title_entry.get(), self.summary.get("1.0", "end-1c"),
                self.content.get("1.0", "end-1c"), self.price.get(), self.tags.get(),
                no_discount=self.no_discount_var.get(), presell=self.presell_var.get(),
            )
            plan_id = str((result or {}).get("id", ""))
            if not plan_id: raise ApiError("发布成功但未获取到方案 ID。")
            expert_ids = [item["groupRelateId"] for index, item in enumerate(self.merchants.get(self.api.user.get("expertId", ""))) if index in self.group_list.curselection()]
            expert_ids.extend(x.strip() for x in self.sync_ids.get("1.0", "end-1c").replace("，", ",").replace("\n", ",").split(",") if x.strip())
            if expert_ids: self.api.sync(plan_id, list(dict.fromkeys(expert_ids)))
            return plan_id
        def done(plan_id):
            self.history.save(self.title_entry.get(), plan_id)
            self.refresh_history()
            self.plan_id.delete(0, "end"); self.plan_id.insert(0, plan_id); self._write("方案 ID：{}（已保存标题映射）".format(plan_id)); messagebox.showinfo("发布成功", "文章已发布。方案 ID：{}".format(plan_id))
        self._run("发布", action, done)

    def update(self, also_sync):
        plan_id = self.plan_id.get()
        def action():
            self.api.modify_content(plan_id, self.new_content.get("1.0", "end-1c"), self.new_price.get())
            if also_sync: self.api.sync_update(plan_id)
            return plan_id
        self._run("更新{}".format("并同步" if also_sync else "内容"), action)

    def set_pin_weight(self, weight, label):
        plan_id = self.plan_id.get().strip()
        self._run(label, lambda: self.api.set_plan_weight(plan_id, weight))


if __name__ == "__main__":
    PublisherApp().mainloop()
