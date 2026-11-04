import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from pathlib import Path

import requests
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BASE = "https://home.liaoxiaobao.cn/api"
PUBLIC_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAys1M5OzPbNsteMDVSLzSOecuyBwbK7KudC+OSZjRGF/D6td4mLpQI4dzCyTmrDkaX7c8eUK7QdOMrDEDqDgmuxUFzwNvC4p3JWzh4LyuDWtwMc29Bj20ALFtEdWAlkkV6XIkXBrjG84njWM+6v70paWmnldR7CoeT+O+Dj5TxXHIMh/kdj6omkHOcA4vYQlhsATwkN1cO6Xyj5tOVNtOIZRSSRO5XYjwJQALvXI29aLcnpopvzUuMULkqtSJiaJkLyslZ4h/9W29vWyYYdRo6BhF08NRPIR86yWYMQsegteacEp4gCONuTJ7nuJYZ7yLZZUwQBnymhBbwHS4qbQxZQIDAQAB"
)


def post(session, path, body):
    response = session.post(BASE + path, json=body, timeout=20, headers={
        "X-Request-Id": str(uuid.uuid4()),
        "X-Timestamp": str(time.time_ns() // 1_000_000),
        "X-Platform": "web",
    })
    response.raise_for_status()
    return response.json()


def decrypt(data, key, iv):
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    raw = decryptor.update(base64.b64decode(data, validate=True)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return json.loads(unpadder.update(raw) + unpadder.finalize())


def bootstrap(session):
    seed = secrets.token_bytes(32)
    public_key = serialization.load_der_public_key(base64.b64decode(PUBLIC_KEY))
    encrypted = public_key.encrypt(seed, rsa_padding.OAEP(
        mgf=rsa_padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None,
    ))
    result = post(session, "/public/bootstrap", {"ek": base64.b64encode(encrypted).decode()})
    if result.get("code") != 200:
        raise ValueError(f"初始化失败，业务状态码 {result.get('code')}")
    data = decrypt(result["data"]["data"], seed[:16], seed[16:])
    return data["secretKey"], data["iv"]


def login(session, phone, password, secret, iv):
    return send_encrypted(session, "/auth/login", {"phone": phone, "password": password}, secret, iv)


def send_encrypted(session, path, payload, secret, iv):
    key, vector = secret[:16].encode(), iv[:16].encode()
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    padder = padding.PKCS7(128).padder()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(vector)).encryptor()
    data = base64.b64encode(encryptor.update(padder.update(raw) + padder.finalize()) + encryptor.finalize()).decode()

    def sign(value):
        return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    result = post(session, path, {"data": data, "sign": sign(data)})
    return unpack(result, secret, iv)


def unpack(result, secret, iv):
    if "code" not in result:
        expected = hmac.new(secret.encode(), result["data"].encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, result["sign"]):
            raise ValueError("接口响应验签失败")
        return decrypt(result["data"], secret[:16].encode(), iv[:16].encode())
    return result

from .base import PlatformAdapter
from ..storage import load_session, save_session


class LiaoxiaobaoPlatform(PlatformAdapter):
    name = "料小宝"
    capabilities = frozenset({"image_upload", "pinning", "platform_managed_sync"})

    def __init__(self, credentials=None):
        self.session = requests.Session()
        self.credentials = load_session(self.name) if credentials is None else dict(credentials)
        self.session.cookies.update(self.credentials.get('cookies',{}))
        self._authorize()

    def _authorize(self):
        if self.logged_in:
            self.session.headers["Authorization"] = "Bearer " + self.credentials["token"]

    @property
    def logged_in(self):
        return all(self.credentials.get(key) for key in ("token", "secret", "iv"))

    def login(self, phone, password):
        credentials = self._login_credentials(phone,password)
        save_session(self.name, credentials)
        self.credentials = credentials
        self._authorize()
        return "料小宝登录成功"

    def _login_credentials(self, phone, password):
        secret, iv = bootstrap(self.session)
        result = login(self.session, phone, password, secret, iv)
        self._check(result)
        data = result.get("data")
        token = result.get("token") or (data.get("token") if isinstance(data, dict) else None)
        if not isinstance(token, str) or not token:
            raise ValueError("料小宝登录响应缺少令牌")
        credentials = {"token": token, "secret": secret, "iv": iv,
                       "cookies": self.session.cookies.get_dict()}
        return credentials

    @staticmethod
    def _check(result):
        if result.get("code") != 200:
            raise RuntimeError(f"料小宝请求失败（{result.get('code')}）：{result.get('message', '')}")
        return result.get("data")

    def _send(self, path, payload):
        return self._check(send_encrypted(self.session, path, payload,
                                          self.credentials["secret"], self.credentials["iv"]))

    def _upload(self, paths, category):
        from mimetypes import guess_type
        images = []
        for filename in paths:
            path = Path(filename)
            with path.open("rb") as stream:
                response = self.session.post(BASE + "/file/upload/" + category,
                    files={"file": (path.name, stream, guess_type(path.name)[0] or "application/octet-stream")},
                    timeout=(10, 180))
            response.raise_for_status()
            result = unpack(response.json(), self.credentials["secret"], self.credentials["iv"])
            images.append(self._check(result)["filePath"])
        return images

    def publish(self, article, images=(), **options):
        price = float(article["price"])
        paid = not article["presale"] and price > 0
        category = "ARTICLE_PAID" if paid else "ARTICLE_FREE"
        uploaded = [] if article["presale"] else self._upload(images, category)
        free_uploaded = self._upload(options.get('free_images', ()), 'ARTICLE_FREE')
        payload = {
            "title": article["title"], "summary": article["summary"],
            "price": price, "originalPrice": price,
            "isPreSale": bool(article["presale"]), "tags": article["tags"],
            "freeContent": "\n".join(filter(None, (article["free_content"], article["content"])))
                           if not article["presale"] and not price else article["free_content"],
            "freeImages": free_uploaded + ([] if paid else uploaded),
            "isDiscountAllowed": article["discount_enabled"],
            "isMembershipAllowed": True, "isListed": True, "isPinned": False, "status": 1,
        }
        if paid and (article["content"] or uploaded):
            payload.update(paidContent=article["content"], paidImages=uploaded)
        return self._send("/article/create", payload)

    def update(self, article_id, article, images=(), **options):
        payload = {"articleNo": str(article_id), "content": article["content"],
                   "images": self._upload(images, "ARTICLE_APPEND")}
        for field in ('title','summary'):
            if str(article.get(field,'')).strip():
                payload[field] = article[field]
        if article.get("price"):
            payload["originalPrice"] = float(article["price"])
        if "discount_enabled" in article:
            payload["isDiscountAllowed"] = bool(article["discount_enabled"])
        if 'tags' in article:
            tags = article['tags']
            payload['tags'] = tags if isinstance(tags,list) else [tag.strip() for tag in str(tags).replace('，',',').split(',') if tag.strip()]
        if article.get("presale") in (False, 0):
            payload["finishPreSale"] = True
        return self._send("/article/append", payload)

    def set_top(self, article_id, pin):
        return self._send("/article/pin" if pin else "/article/unpin",
                          {"articleNos": [str(article_id)]})
