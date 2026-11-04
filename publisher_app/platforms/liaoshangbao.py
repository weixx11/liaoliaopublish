"""料商宝 HTTP API 适配器。正式程序不依赖任何测试脚本。"""
from io import BytesIO
from pathlib import Path
from enum import IntEnum
from mimetypes import guess_type
from PIL import Image, ImageOps
import requests
from ..config import LSB_BASE_URL
from .base import PlatformAdapter

TIMEOUT = 60
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/156.0.0.0 Mobile Safari/537.36")


class LiaoshangbaoDiscountValue(IntEnum):
    DISCOUNT_FORBIDDEN = 0  # canZK=0 表示不允许折扣
    DISCOUNT_ALLOWED = 1  # canZK=1 表示允许折扣


class LiaoshangbaoPlatform(PlatformAdapter):
    name = "料商宝"
    capabilities = frozenset({"image_upload", "pre_sale", "discount", "platform_managed_sync"})

    def __init__(self, session=None, uid=None, sid=None):
        self.session = session or requests.Session()
        self.uid, self.sid = uid, sid

    @property
    def logged_in(self):
        return bool(self.uid and self.sid)

    def _headers(self, referer_path=""):
        headers = {"Accept": "*/*", "Origin": "https://qwer.lszs.red",
                   "X-Requested-With": "XMLHttpRequest", "User-Agent": MOBILE_UA}
        if self.uid and self.sid:
            headers["Referer"] = "https://qwer.lszs.red/lsb/{}?uid={}&sid={}".format(referer_path, self.uid, self.sid)
        return headers

    def login(self, mobile, password):
        response = self.session.post(LSB_BASE_URL + "/toMobileLogin",
                                     data={"mobile": mobile, "pwd": password},
                                     headers={"User-Agent": MOBILE_UA,
                                              "Referer": "https://qwer.lszs.red/lsb/loginIndex"},
                                     timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != 200:
            raise RuntimeError("料商宝登录失败：{}".format(data.get("msg")))
        session_fields = dict(part.split("=", 1) for part in str(data.get("data", "")).split("&") if "=" in part)
        self.uid, self.sid = session_fields.get("uid"), session_fields.get("sid")
        if not self.logged_in:
            raise RuntimeError("登录响应没有 uid/sid")
        return {"uid": self.uid, "sid": self.sid}

    @staticmethod
    def _multipart_image(image_path):
        if not image_path:
            return {"tmpFile0": ("", b"", "application/octet-stream")}, None
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError("图片不存在：{}".format(path))
        if path.stat().st_size > 1024 * 1024:
            try:
                with Image.open(path) as source:
                    if not getattr(source, "is_animated", False):
                        picture = ImageOps.exif_transpose(source)
                        picture.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
                        with BytesIO() as buffer:
                            transparent = "A" in picture.getbands() or "transparency" in picture.info
                            if transparent:
                                picture.convert("RGBA").save(buffer, format="PNG", optimize=True)
                                suffix, mime = ".png", "image/png"
                            else:
                                picture.convert("RGB").save(buffer, format="JPEG", quality=87, optimize=True)
                                suffix, mime = ".jpg", "image/jpeg"
                            if buffer.tell() < path.stat().st_size:
                                return {"tmpFile0": ("tmpFile0" + suffix, buffer.getvalue(), mime)}, None
            except (OSError, Image.DecompressionBombError):
                pass
        handle = path.open("rb")
        mime = guess_type(path.name)[0] or "application/octet-stream"
        return {"tmpFile0": ("tmpFile0" + path.suffix.lower(), handle, mime)}, handle

    def _post_multipart(self, endpoint, fields, images, referer):
        if len(images) > 9:
            raise ValueError("料商宝每篇最多上传 9 张图片")
        files = {}
        handles = []
        try:
            for index, path in enumerate(images or (None,)):
                parts, handle = self._multipart_image(path)
                if handle:
                    handles.append(handle)
                name, data, mime = parts["tmpFile0"]
                field = f"tmpFile{index}"
                files[field] = (name.replace("tmpFile0", field, 1), data, mime)
            response = self.session.post(LSB_BASE_URL + endpoint, data=fields, files=files,
                                         headers=self._headers(referer), timeout=(10, 180 if images else TIMEOUT))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ReadTimeout as exc:
            raise RuntimeError("料商宝响应超时，提交结果未确认。请先到平台核对内容，再决定是否重试。") from exc
        finally:
            for handle in handles:
                handle.close()

    def publish(self, article, images=(), *, free_images=()):
        if not self.logged_in:
            raise RuntimeError("请先登录料商宝")
        fields = [
            ("uid", self.uid), ("sid", self.sid), ("title", article["title"]),
            ("title2", article.get("subtitle", "")),
            ("shortMsg", article.get("subtitle",article.get("summary", ""))), ("free_content", article.get("free_content", "")),
            ("content", article["content"]), ("price", str(article.get("price", "10"))),
            ("showLabel", article.get("label", "")), ("onSeld", "1"), ("canVip", "1"),
            ("bgimgid", "img/a001.png"), ("canBuyCount", "0"), ("playTime", ""),
            ("autoSeldTime", ""), ("autoNoticeTime", ""), ("freeTime", ""), ("validTime", ""),
            ("fsLv", "0"), ("allZK", "10"),
            ("canZK", str(LiaoshangbaoDiscountValue.DISCOUNT_ALLOWED if article.get("discount_enabled", False) else LiaoshangbaoDiscountValue.DISCOUNT_FORBIDDEN)), ("canAgain", "0"), ("gid", "0"),
            ("showLabel", article.get("label", "")), ("shortmsg", article.get("subtitle",article.get("summary", ""))),
            ("freeContent", article.get("free_content", "")), ("content", article["content"]),
            ("preSale", str(article.get("presale", 1))),
        ]
        # The current protocol has a single tmpFileN image sequence. Until a
        # separate free-image field is verified, use it for both editor areas.
        attachments = tuple(free_images) + tuple(images)
        result = self._post_multipart("/addPro", fields, attachments,
                                      "addIndex?uid={}&sid={}".format(self.uid, self.sid))
        if result.get("status") != 200:
            raise RuntimeError("料商宝发布失败：{}".format(result))
        return result

    def update(self, article_id, article, images=()):
        if not self.logged_in:
            raise RuntimeError("请先登录料商宝")
        if not str(article_id or "").strip():
            raise ValueError("料商宝文章 ID 不能为空")
        if not str(article.get("content", "")).strip() and not images:
            raise ValueError("料商宝追加内容需要文字或图片")
        # Keep this field sequence consistent with the captured, working
        # updatePro request. In particular, updatePro has no title2 field.
        fields = [
            ("uid", self.uid), ("sid", self.sid), ("pid", str(article_id)),
            ("title", article["title"]), ("shortMsg", article.get("subtitle", "")),
            ("content", article["content"]), ("price", str(article.get("price", "10"))),
            ("customPrice", ""), ("showLabel", article.get("label", "")),
            ("canBuyCount", "0"), ("customCount", ""), ("playTime", ""),
            ("freeTime", ""), ("validTime", ""), ("onSeld", "1"), ("fsLv", "0"),
            ("allZK", "10"), ("canZK", str(LiaoshangbaoDiscountValue.DISCOUNT_ALLOWED if article.get("discount_enabled", False) else LiaoshangbaoDiscountValue.DISCOUNT_FORBIDDEN)),
            ("canVip", "1"), ("canAgain", "0"), ("gid", "0"), ("bgimgid", "img/a001.png"),
            ("showLabel", article.get("label", "")), ("shortmsg", article.get("subtitle", "")),
            ("content", article["content"]), ("preSale", str(article.get("presale", 1))),
        ]
        price = article.get("price")
        if 'subtitle' not in article:
            fields = [(name,value) for name,value in fields if name not in ('shortMsg','shortmsg')]
        if 'label' not in article:
            fields = [(name,value) for name,value in fields if name != 'showLabel']
        if price is None or not str(price).strip():
            raise ValueError("料商宝更新需要价格，请填写文章原价或新价格")
        result = self._post_multipart("/updatePro", fields, images,
                                      "updateIndex?uid={}&sid={}&pid={}".format(self.uid, self.sid, article_id))
        if result.get("status") != 200:
            raise RuntimeError("料商宝更新失败：{}".format(result))
        return result

    def set_top(self, article_id):
        response = self.session.post(LSB_BASE_URL + "/toSeldTop",
                                     data={"uid": self.uid, "sid": self.sid, "pid": str(article_id)},
                                     headers=self._headers("myPro"), timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
