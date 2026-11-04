import base64
import json
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

BASE = "https://yapi.njyuelu.cn"
PUBLIC_KEY = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCziwFlX06REs4ZRbpuzqwpKRsil4yzYc9itZwz/8S80Wof3SV/FN0Uq/hKDdDRXhoFzvF8sfvZNyUuUNeWlARyePvthXybn+JTTmIbUrcZV29ss4B5Y9TUTMeZB2TsWoOFVsv+knBMp5aT5Z2aGrL5XmkCxnV6np7GamlfoBOHhwIDAQAB"


def common(session, uri, data, base=BASE):
    body = {"d": data}
    params = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    plaintext = json.dumps({"uri": uri, "d": body}, ensure_ascii=False, separators=(",", ":")).encode()
    key = serialization.load_der_public_key(base64.b64decode(PUBLIC_KEY))
    size = key.key_size // 8 - 11
    encrypted = b"".join(key.encrypt(plaintext[i:i + size], padding.PKCS1v15())
                         for i in range(0, len(plaintext), size))
    response = session.post(base + "/h5/h5-do/common", timeout=20,
                            headers={"h5url": uri, "paramUrlData": quote(params, safe="")},
                            json={"m": base64.b64encode(encrypted).decode()})
    response.raise_for_status()
    result = response.json()
    if result.get("c") != 200:
        raise ValueError(f"{uri} 失败，业务码 {result.get('c')}：{result.get('m')}")
    return result.get("d")

DOMAINS = {"壹料": BASE, "红料": "https://api.hongliao168.cn"}


class MonitorClient:
    initial_limit = 100
    def __init__(self, platform, saved=None):
        self.base = DOMAINS[platform]
        saved = saved or {}
        self.uuid = saved.get("uuid") or str(uuid.uuid4())
        self.session = requests.Session()
        self.session.headers.update({
            "Origin": "https://m.njyuelu.cn", "Referer": "https://m.njyuelu.cn/",
            "appId": "yl-m", "version": "1.0.0", "uuid": self.uuid,
        })
        self.user_id = saved.get("user_id")
        if saved.get("token"):
            self.session.headers["Authorization"] = saved["token"]
        self.index = 0

    def call(self, path, data):
        return common(self.session, path, data, self.base)

    def captcha(self, phone):
        self.index += 1
        self.phone = phone
        self.key = f"{phone}?{self.index}"
        result = self.session.get(self.base + f"/resource/app-do/kaptcha?key={self.key}", timeout=15)
        result.raise_for_status()
        with Image.open(BytesIO(result.content)) as image:
            return image.copy()

    def sms(self, code):
        if self.call("/resource/app-do/kaptchaValidate", {"code": code, "key": self.key}) is not True:
            raise ValueError("图形验证码校验未通过")
        self.call("/resource/rse-sms-do/sendCode", {"phone": int(self.phone), "code": 1})

    def login(self, code):
        result = self.call("/user/usr-do/login", {"phone": int(self.phone), "smsCode": code})
        self.session.headers["Authorization"] = result["token"]
        profile = self.call("/user/usr-do/userInfo", {})
        if profile["id"] != result["userId"]:
            raise ValueError("登录账号与本人资料不匹配")
        self.user_id = profile["id"]
        return {"user_id": self.user_id, "uuid": self.uuid, "token": result["token"],
                "name": profile.get("name") or self.phone}

    def following(self):
        merchants = {}
        for page in range(1, 101):
            result = self.call("/user/app-user-focus/my", {
                "data": {"id": self.user_id}, "page": str(page), "pageSize": "200",
            })
            rows = result["rows"]
            for row in rows:
                expert = row.get("expertId")
                if expert:
                    merchants[expert] = row.get("expertName") or row.get("userName") or row.get("name") or expert
            total = result.get("total")
            if not rows or (total is not None and page * 200 >= int(total)) or (total is None and len(rows) < 200):
                return merchants
        raise ValueError("关注列表超过分页上限")

    def latest(self, expert):
        result = self.call("/plan/app-plan-do/expertLastPlan", {
            "expertId": expert, "userId": self.user_id, "sportsId": 4,
            "groupType": "", "labelId": "", "title": "",
        })
        rows = result.get("rows") if isinstance(result, dict) else result
        if not isinstance(rows, list):
            raise ValueError("无法读取最新文章列表")
        rows = [dict(row,planSubtitle=row.get('planSubtitle') or row.get('planTitle2') or row.get('title2') or row.get('subtitle') or '') for row in rows]
        return sorted(rows, key=lambda row: str(row.get('planPublicTime') or ''), reverse=True)[:self.initial_limit]
