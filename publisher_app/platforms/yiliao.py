from requests import Session, RequestException
import json
from pathlib import Path
from datetime import datetime, timedelta
from html import escape
from enum import IntEnum
from ..config import YILIAO_SESSION_FILE, YILIAO_URLS
from .base import PlatformAdapter


class YiliaoDiscountValue(IntEnum):
    # Mapped from the observed platform behavior: checked "允许折扣" must
    # publish as the value that renders as discount-enabled in 壹料.
    DISCOUNT_ALLOWED = 0
    DISCOUNT_FORBIDDEN = 1


class YiliaoPlatform(PlatformAdapter):
    name = "壹料"
    capabilities = frozenset({"child_sync", "image_upload", "pinning", "article_history"})

    def __init__(self):
        self.session = Session()
        self.user = {}
        try:
            saved = json.loads(YILIAO_SESSION_FILE.read_text(encoding="utf-8"))
            self.user = saved.get("user_data", {})
            self.session.cookies.update(saved.get("cookies", {}))
        except (OSError, ValueError):
            pass

    @property
    def logged_in(self):
        return bool(self.user.get("token"))

    def login(self, account, password):
        result = self._post("login", {"account": account, "pwd": password, "proxyTag": ""})
        self.user = result or {}
        YILIAO_SESSION_FILE.write_text(json.dumps({"user_data": self.user, "cookies": self.session.cookies.get_dict()}, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.user

    def _post(self, key, data):
        headers = {"Content-Type": "application/json", "User-Agent": "YiliaoPublisher/1.0"}
        if self.user.get("token"):
            headers["Authorization"] = self.user["token"]
        response = self.session.post(YILIAO_URLS[key], json={"d": data}, headers=headers, timeout=20)
        response.raise_for_status()
        result = response.json()
        if result.get("c") != 200:
            raise RuntimeError("壹料接口失败：{}".format(result.get("m")))
        return result.get("d")

    def child_accounts(self):
        try:
            response = self.session.post(YILIAO_URLS["user_info"], headers={"Authorization": self.user.get("token", "")}, timeout=20)
            response.raise_for_status(); result = response.json()
            if result.get("c") != 200: raise RuntimeError(result.get("m"))
            self.user_info = result.get("d", {})
            return self.user_info.get("groupList", [])
        except RequestException as exc:
            raise RuntimeError("获取壹料子账号失败：{}".format(exc))

    def publish(self, article, images=(), child_ids=(), **_options):
        content = article["content"]
        for path in images:
            url = self.upload_image(path)
            content += '<p><img src="{}" alt="" data-href="" style=""/></p>'.format(url)
        now = datetime.now(); expiry = now + timedelta(hours=24)
        tags = [x.strip() for x in article.get("tags", "").replace("，", ",").split(",") if x.strip()]
        no_discount = (YiliaoDiscountValue.DISCOUNT_ALLOWED if article.get("discount_enabled", False)
                       else YiliaoDiscountValue.DISCOUNT_FORBIDDEN)
        result = self._post("publish", {"id":"", "appPush":1, "planPackAuto":1, "planPacks":"", "noDiscount":int(no_discount), "notifyAuto":0, "items":"", "title":article["title"], "title2":article.get("subtitle", ""), "summary":self._html(article.get("summary", "")), "freeContent":self._html(article.get("free_content", "")), "content":self._html(content), "free":0, "needPay":1, "price":str(article["price"]), "priceReal":str(article["price"]), "publicTime":now.strftime("%Y-%m-%d %H:%M:%S"), "endTime":expiry.strftime("%Y-%m-%d %H:%M:%S"), "activityId":None, "sportsId":4, "expertId":self.user.get("expertId"), "tag1":"", "tag2":"", "tags":",".join(tags), "labelIds":"", "playType":"9001", "tagsArray":tags, "presell":int(bool(article.get("presale",1))), "updateTimeShow":0, "beginTime":expiry.strftime("%Y-%m-%d %H:%M:%S")})
        article_id = (result or {}).get("id")
        if child_ids:
            self._post("sync", {"planId": article_id, "expertIdList": list(child_ids)})
        return {"response": result, "id": article_id}

    def update(self, article_id, article, images=(), **_options):
        if not str(article_id or "").strip():
            raise ValueError("壹料文章 ID 不能为空")
        content = article["content"]
        for path in images:
            url = self.upload_image(path)
            content += '<p><img src="{}" alt="" data-href="" style=""/></p>'.format(url)
        if not str(content or "").strip():
            raise ValueError("更新正文不能为空，已阻止提交空内容")
        # Keep the article active after editing. The API expects a future window;
        # sending the current instant as endTime can make the article disappear.
        expiry = datetime.now() + timedelta(hours=24)
        no_discount = (YiliaoDiscountValue.DISCOUNT_ALLOWED if article.get("discount_enabled", False)
                       else YiliaoDiscountValue.DISCOUNT_FORBIDDEN)
        fields = {"id":str(article_id), "expertId":self.user.get("expertId"), "compType":"1", "publicTime":datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "lotteryType":6, "issueNo":None, "title":article.get("title", ""), "title2":article.get("subtitle", ""), "summary":self._html(article.get("summary", "")), "freeContent":self._html(article.get("free_content", "")), "beginTime":expiry.strftime("%Y-%m-%d %H:%M:%S"), "endTime":expiry.strftime("%Y-%m-%d %H:%M:%S"), "content":self._html(content), "playType":"9001", "planType":None, "hidden":0, "free":0, "matchs":None, "status":0, "verifyStatus":2, "verifyMsg":None, "activityId":0, "sportsId":4, "notifyAuto":0, "noDiscount":int(no_discount), "tags":"", "planPackAuto":0, "planPacks":"", "presell":int(bool(article.get("presale", 1))), "updateTimeShow":0, "qrcodeList":[]}
        price = article.get("price")
        if price is not None and str(price).strip():
            fields.update(price=str(price).strip(), priceReal=str(price).strip())
        result = self._post("modify", fields)
        self._post("sync_update", {"planId":str(article_id)})
        return result

    def set_weight(self, article_id, weight):
        result = self._post("modify", {"id":int(article_id), "weight":int(weight)})
        if result is not True:
            raise RuntimeError("壹料置顶状态更新失败：{}".format(result))
        return result

    @staticmethod
    def _html(text):
        text = str(text or "").strip()
        return text if text.startswith("<") else "<p>{}</p>".format(escape(text).replace("\n", "<br>"))

    def upload_image(self, path):
        path = Path(path); headers = {"Authorization": self.user.get("token", "")}
        with path.open("rb") as image:
            response = self.session.post(YILIAO_URLS["upload"], data={"path":"resource"}, files={"files":(path.name,image)}, headers=headers, timeout=30)
        response.raise_for_status(); result = response.json()
        if result.get("c") != 200: raise RuntimeError(result.get("m"))
        return self._find_url(result.get("d"))

    @staticmethod
    def _find_url(value):
        if isinstance(value, str) and value.startswith(("https://", "http://")): return value
        if isinstance(value, dict):
            for item in value.values():
                found = YiliaoPlatform._find_url(item)
                if found: return found
        if isinstance(value, list):
            for item in value:
                found = YiliaoPlatform._find_url(item)
                if found: return found
        return None
