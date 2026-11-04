"""料商宝文章发布接口测试。

运行：python 料商宝发布测试.py
脚本会先登录，然后展示待发布内容并要求输入 PUBLISH 才会实际提交。
"""
import getpass
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import unquote

import requests
from PIL import ImageGrab


BASE_URL = "https://qwer.lszs.red/lsb"
LOGIN_URL = BASE_URL + "/toMobileLogin"
PUBLISH_URL = BASE_URL + "/addPro"
TIMEOUT = 20


def normalize_clipboard_path(value):
    """Convert clipboard file URI variants (including file:\\D:\\...) to paths."""
    raw = unquote(str(value).strip())
    if raw.lower().startswith("file:"):
        raw = raw[5:]
        # file:///D:/..., file:/D:/..., and file:\\D:\\... variants.
        raw = raw.lstrip("/\\")
        if re.match(r"^[A-Za-z]:[/\\]", raw):
            pass
        elif re.match(r"^[A-Za-z]:[/\\]", raw[1:]):
            raw = raw[1:]
    return Path(raw)


def login(session, mobile, password):
    response = session.post(
        LOGIN_URL,
        data={"mobile": mobile, "pwd": password},
        headers={"User-Agent": "Mozilla/5.0", "Referer": BASE_URL + "/loginIndex"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("status") != 200:
        raise RuntimeError("登录失败：{}".format(result.get("msg")))
    # 登录接口 data 格式为 uid=...&sid=...
    pairs = dict(item.split("=", 1) for item in str(result.get("data", "")).split("&") if "=" in item)
    if not pairs.get("uid") or not pairs.get("sid"):
        raise RuntimeError("登录返回中缺少 uid/sid：{}".format(result))
    return pairs["uid"], pairs["sid"]


def publish_article(session, uid, sid, article, image_path=None):
    """提交 multipart/form-data；支持本地文件或剪贴板图片。"""
    # Use a list of pairs because the browser submits several duplicate keys.
    fields = [
        ("uid", uid), ("sid", sid), ("title", article["title"]),
        ("shortMsg", article.get("shortMsg", "")),
        ("free_content", article.get("free_content", "")),
        ("content", article["content"]), ("price", str(article.get("price", "10"))),
        ("showLabel", article.get("showLabel", "biaobiao")),
        ("onSeld", str(article.get("onSeld", 1))), ("canVip", str(article.get("canVip", 1))),
        ("bgimgid", article.get("bgimgid", "img/a001.png")),
        ("canBuyCount", str(article.get("canBuyCount", 0))),
        ("playTime", article.get("playTime", "")), ("autoSeldTime", article.get("autoSeldTime", "")),
        ("autoNoticeTime", article.get("autoNoticeTime", "")), ("freeTime", article.get("freeTime", "")),
        ("validTime", article.get("validTime", "")), ("fsLv", str(article.get("fsLv", 0))),
        ("allZK", str(article.get("allZK", 10))),
        # Browser capture with no discount uses canZK=0; canZK=1 enables discount.
        ("canZK", str(article.get("canZK", 1))),
        ("canAgain", str(article.get("canAgain", 0))), ("gid", str(article.get("gid", 0))),
        ("showLabel", article.get("showLabel", "biaobiao")),
        ("shortmsg", article.get("shortMsg", "")),
        ("freeContent", article.get("free_content", "")),
        ("content", article["content"]), ("preSale", str(article.get("preSale", 0))),
    ]
    # Providing an empty file part keeps the request multipart when the user
    # omits an image; when selected, the actual tmpFile0 replaces this part.
    files = {"tmpFile0": ("", b"", "application/octet-stream")}
    image_handle = None
    clipboard_buffer = None
    if image_path:
        path = normalize_clipboard_path(image_path)
        if not path.is_file():
            raise FileNotFoundError("图片文件不存在：{}".format(path))
        image_handle = path.open("rb")
        files = {"tmpFile0": ("tmpFile0" + path.suffix.lower(), image_handle)}
    else:
        clipboard_image = ImageGrab.grabclipboard()
        if isinstance(clipboard_image, (list, tuple)):
            copied_file = next((normalize_clipboard_path(p) for p in clipboard_image if normalize_clipboard_path(p).is_file()), None)
            if copied_file:
                image_handle = copied_file.open("rb")
                files = {"tmpFile0": (copied_file.name, image_handle)}
        elif clipboard_image is not None and hasattr(clipboard_image, "save"):
            clipboard_buffer = BytesIO()
            clipboard_image.save(clipboard_buffer, format="PNG")
            clipboard_buffer.seek(0)
            files = {"tmpFile0": ("clipboard.png", clipboard_buffer, "image/png")}
    try:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Origin": "https://qwer.lszs.red",
            "Referer": "https://qwer.lszs.red/lsb/addIndex?uid={}&sid={}".format(uid, sid),
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Mobile Safari/537.36",
        }
        # Do not set Content-Type manually: requests must add the multipart boundary.
        response = session.post(PUBLISH_URL, data=fields, files=files, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            return {"http_status": response.status_code, "raw": response.text[:2000]}
    finally:
        if image_handle:
            image_handle.close()
        if clipboard_buffer:
            clipboard_buffer.close()


if __name__ == "__main__":
    http = requests.Session()
    # mobile = input("料商宝账号（手机号）：").strip()
    mobile = __import__("os").environ.get("LSB_TEST_ACCOUNT") or input("ACCOUNT: ").strip()
    password = __import__("os").environ.get("LSB_TEST_PASSWORD") or input("PASSWORD: ").strip()
    try:
        uid, sid = login(http, mobile, password)
        print("登录成功，已取得 uid；sid 已隐藏。")
        article = {
            "title": input("文章标题：").strip(),
            "shortMsg": input("短摘要：").strip(),
            "free_content": input("免费内容：").strip(),
            "content": input("付费正文：").strip(),
            "price": input("价格（默认 10）：").strip() or "10",
        }
        presale_answer = input("是否预售？输入 1=是，0=否（默认 0）：").strip() or "0"
        discount_answer = input("是否允许折扣？输入 1=是，0=无折扣（默认 1）：").strip() or "1"
        if presale_answer not in ("0", "1") or discount_answer not in ("0", "1"):
            raise ValueError("预售和折扣选项只能输入 0 或 1")
        article["preSale"] = int(presale_answer)
        article["canZK"] = int(discount_answer)
        image_path = input("图片文件路径或 file URI（直接复制图片后留空，将从剪贴板读取）：").strip() or None
        print("\n将向料商宝提交文章：{}（价格 {}）".format(article["title"], article["price"]))
        if input("确认发布请输入 PUBLISH：").strip() != "PUBLISH":
            print("已取消，未提交文章。")
        else:
            result = publish_article(http, uid, sid, article, image_path)
            print("发布接口响应：{}".format(json.dumps(result, ensure_ascii=False)))
    except (requests.RequestException, ValueError, RuntimeError, OSError) as exc:
        print("测试失败：{}".format(exc))
