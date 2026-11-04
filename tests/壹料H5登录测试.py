"""手动输入图形码和短信码，验证壹料 H5 用户会话。"""
import base64
import argparse
import time
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


def common(session, uri, data):
    body = {"d": data}
    params = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    plaintext = json.dumps({"uri": uri, "d": body}, ensure_ascii=False, separators=(",", ":")).encode()
    key = serialization.load_der_public_key(base64.b64decode(PUBLIC_KEY))
    size = key.key_size // 8 - 11
    encrypted = b"".join(key.encrypt(plaintext[i:i + size], padding.PKCS1v15())
                         for i in range(0, len(plaintext), size))
    response = session.post(BASE + "/h5/h5-do/common", timeout=20,
                            headers={"h5url": uri, "paramUrlData": quote(params, safe="")},
                            json={"m": base64.b64encode(encrypted).decode()})
    response.raise_for_status()
    result = response.json()
    if result.get("c") != 200:
        raise ValueError(f"{uri} 失败，业务码 {result.get('c')}：{result.get('m')}")
    return result.get("d")


def main():
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("yiliao", "hongliao"), default="yiliao")
    parser.add_argument("--expert-id", help="登录后查询指定商家的第一页文章")
    parser.add_argument("--watch", action="store_true", help="持续查询并输出新增文章")
    parser.add_argument("--following", action="store_true", help="查询当前账号关注的商家")
    parser.add_argument("--interval", type=int, default=60, help="轮询间隔秒数，默认 60")
    args = parser.parse_args()
    if args.platform == "hongliao":
        BASE = "https://api.hongliao168.cn"
    if args.watch and not args.expert_id:
        parser.error("--watch 需要指定 --expert-id")
    if args.interval < 10:
        parser.error("--interval 至少为 10 秒")
    phone = input("手机号：").strip()
    if len(phone) != 11 or not phone.isascii() or not phone.isdecimal():
        raise ValueError("请输入 11 位手机号")
    with requests.Session() as session:
        session.headers.update({"Origin": "https://m.njyuelu.cn", "Referer": "https://m.njyuelu.cn/",
                                "appId": "yl-m", "version": "1.0.0", "uuid": str(uuid.uuid4())})
        index = 0
        while True:
            index += 1
            captcha_key = f"{phone}?{index}"
            response = session.get(BASE + f"/resource/app-do/kaptcha?key={captcha_key}", timeout=15)
            response.raise_for_status()
            with Image.open(BytesIO(response.content)) as image:
                captcha_path = Path(__file__).resolve().with_name("壹料H5验证码.local.png")
                image.save(captcha_path, format="PNG")
            print(f"验证码图片已保存：{captcha_path}", flush=True)
            code = input("图形验证码（直接回车换一张）：").strip()
            if code:
                if common(session, "/resource/app-do/kaptchaValidate", {"code": code, "key": captcha_key}) is not True:
                    raise ValueError("图形验证码校验未通过")
                break
        common(session, "/resource/rse-sms-do/sendCode", {"phone": int(phone), "code": 1})
        sms = input("收到的六位短信验证码：").strip()
        if len(sms) != 6 or not sms.isascii() or not sms.isdecimal():
            raise ValueError("请输入六位短信验证码")
        login = common(session, "/user/usr-do/login", {"phone": int(phone), "smsCode": sms})
        if not isinstance(login, dict) or not login.get("token"):
            raise ValueError("登录响应缺少 token")
        session.headers["Authorization"] = login["token"]
        profile = common(session, "/user/usr-do/userInfo", {})
        if not isinstance(profile, dict) or not profile.get("id") or profile["id"] != login.get("userId"):
            raise ValueError("本人资料与登录账号不匹配")
        print("登录成功，本人资料验证通过")
        if args.following:
            followed = common(session, "/user/app-user-focus/my", {
                "data": {"id": profile["id"]}, "page": "1", "pageSize": "200",
            })
            rows = followed.get("rows") if isinstance(followed, dict) else None
            if not isinstance(rows, list):
                raise ValueError("关注列表响应缺少 rows")
            merchants = {row["expertId"]: row for row in rows
                         if isinstance(row, dict) and row.get("expertId")}
            print(f"接口总数：{followed.get('total', '未返回')}，本页商家数：{len(merchants)}")
            for expert_id, row in merchants.items():
                name = row.get("expertName") or row.get("userName") or row.get("name") or "未返回名称"
                print(f"{expert_id} | {name}")
        if args.expert_id:
            monitor_plans(session, args.expert_id, profile["id"], args.watch, args.interval)


def monitor_plans(session, expert_id, user_id, watch, interval):
    seen = set()
    first = True
    while True:
            plans = common(session, "/plan/app-plan-do/expertLastPlan", {
                "expertId": expert_id, "userId": user_id, "sportsId": 4,
                "groupType": "", "labelId": "", "title": "",
            })
            rows = plans.get("rows") if isinstance(plans, dict) else plans
            if not isinstance(rows, list):
                raise ValueError("最新文章接口返回的列表结构无法识别")
            if first:
                print(f"已记录当前最新列表 {len(rows)} 条，作为监控基线")
            for row in rows:
                plan_id = row.get("planId")
                if plan_id is None or plan_id in seen:
                    continue
                seen.add(plan_id)
                if first and watch:
                    continue
                if not first:
                    print("发现新增文章")
                print(f"{row.get('planId')} | {row.get('planPublicTime')} | "
                      f"{row.get('planTitle')} | 原价 {row.get('price')} | "
                      f"实际价 {row.get('priceReal')} | 置顶 {row.get('top')}")
            if not watch:
                return
            if first:
                print(f"开始监控，每 {interval} 秒检查一次，按 Ctrl+C 停止")
            first = False
            time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止监控")
    except (requests.RequestException, ValueError, OSError) as exc:
        raise SystemExit(f"联调失败：{exc}") from None
