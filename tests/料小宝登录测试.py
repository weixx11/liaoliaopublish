"""料小宝登录联调。先用 --bootstrap-only 验证初始化。"""
import argparse
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


def clipboard_images():
    from io import BytesIO
    from PIL import Image, ImageGrab

    images = []
    while True:
        if input("在微信复制一张图片后按回车读取，输入 done 完成：").strip().lower() == "done":
            return images
        copied = ImageGrab.grabclipboard()
        if isinstance(copied, Image.Image):
            with BytesIO() as buffer:
                copied.save(buffer, format="PNG")
                images.append((f"wechat-{len(images) + 1}.png", buffer.getvalue(), "image/png"))
        elif isinstance(copied, list):
            from mimetypes import guess_type
            for filename in copied:
                path = Path(filename)
                mime = guess_type(path.name)[0] or ""
                if mime.startswith("image/") and path.is_file():
                    images.append((path.name, path.read_bytes(), mime))
        print(f"当前已收集 {len(images)} 张图片")


def create_article(session, paths, secret, iv, use_clipboard=False, *,
                   presale=True, discount=False, pinned=False, price=0):
    from mimetypes import guess_type

    title = input("测试文章标题：").strip()
    if not title:
        raise ValueError("标题不能为空")
    summary = input("文章简介（可留空）：").strip()
    tag_text = input("标签（用逗号分隔，可留空）：")
    tags = [tag.strip() for tag in tag_text.replace("，", ",").split(",") if tag.strip()]
    content = input("免费正文：")
    paid_content = input("付费正文（留空则不提交）：")
    for path in paths:
        if not path.is_file():
            raise ValueError(f"图片不存在：{path}")
    attachments = [(path.name, path.read_bytes(), guess_type(path.name)[0] or "application/octet-stream")
                   for path in paths]
    if use_clipboard:
        copied = clipboard_images()
        if not copied:
            raise ValueError("未从剪贴板读取到图片")
        attachments.extend(copied)
    if input(f"将上传 {len(attachments)} 张图片并发布《{title}》，请输入 PUBLISH：") != "PUBLISH":
        print("已取消发布")
        return
    images = upload_images(session, attachments, "ARTICLE_FREE", secret, iv)
    payload = {
        "title": title, "summary": summary, "price": price, "originalPrice": price,
        "isPreSale": presale, "tags": tags, "freeContent": content, "freeImages": images,
        "isDiscountAllowed": discount, "isMembershipAllowed": True,
        "isListed": True, "isPinned": pinned, "status": 1,
    }
    if paid_content.strip():
        payload["paidContent"] = paid_content
        payload["paidImages"] = []
    result = send_encrypted(session, "/article/create", payload, secret, iv)
    if result.get("code") != 200:
        raise ValueError(f"创建失败，业务状态码 {result.get('code')}")
    print("创建成功，文章编号：", result.get("data"))


def upload_images(session, attachments, category, secret, iv):
    images = []
    for name, data, mime in attachments:
        response = session.post(
                BASE + "/file/upload/" + category,
                files={"file": (name, data, mime)},
                timeout=60,
            )
        response.raise_for_status()
        result = unpack(response.json(), secret, iv)
        if result.get("code") != 200 or not result.get("data", {}).get("filePath"):
            raise ValueError(f"图片上传失败：{name}，业务状态码 {result.get('code')}")
        images.append(result["data"]["filePath"])
        print(f"图片已上传：{name}")
    return images


def append_article(session, article_no, secret, iv, use_clipboard):
    content = input("追加正文：")
    attachments = clipboard_images() if use_clipboard else []
    if not content.strip() and not attachments:
        raise ValueError("请填写追加正文或添加图片")
    if input(f"将向文章 {article_no} 追加内容和 {len(attachments)} 张图片，输入 APPEND 确认：") != "APPEND":
        print("已取消追加")
        return
    images = upload_images(session, attachments, "ARTICLE_APPEND", secret, iv)
    result = send_encrypted(session, "/article/append", {
        "articleNo": article_no, "content": content, "images": images,
    }, secret, iv)
    if result.get("code") != 200:
        raise ValueError(f"追加失败，业务状态码 {result.get('code')}，{result.get('message', '')}")
    print("追加成功，文章编号：", article_no)


def change_pin(session, article_no, secret, iv, pin):
    action = "置顶" if pin else "取消置顶"
    if input(f"将{action}文章 {article_no}，输入 YES 确认：").strip() != "YES":
        print("已取消操作")
        return
    endpoint = "/article/pin" if pin else "/article/unpin"
    result = send_encrypted(session, endpoint, {"articleNos": [article_no]}, secret, iv)
    if result.get("code") != 200:
        raise ValueError(f"{action}失败，业务状态码 {result.get('code')}，{result.get('message', '')}")
    print(f"{action}成功，文章编号：{article_no}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap-only", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--presale", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--discount", action="store_true")
    parser.add_argument("--pinned", action="store_true")
    parser.add_argument("--price", type=int, default=0)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--publish", nargs="*", type=Path, metavar="图片路径")
    operation.add_argument("--append", metavar="文章编号")
    operation.add_argument("--paid-upload", action="store_true", help="测试上传微信剪贴板图片到付费区")
    operation.add_argument("--pin", metavar="文章编号")
    operation.add_argument("--unpin", metavar="文章编号")
    parser.add_argument("--clipboard", action="store_true", help="从微信复制图片后按回车读取，配合 --publish")
    args = parser.parse_args()
    if args.clipboard and args.publish is None and args.append is None:
        parser.error("--clipboard 需要与 --publish 或 --append 一起使用")
    try:
        with requests.Session() as session:
            secret, iv = bootstrap(session)
            print("初始化成功")
            if not args.bootstrap_only:
                config_path = Path(__file__).with_name("料小宝账号.local.json")
                config = json.loads(config_path.read_text(encoding="utf-8-sig"))
                phone = config.get("phone")
                password = config.get("password")
                if not isinstance(phone, str) or not phone.strip() or not isinstance(password, str) or not password:
                    raise ValueError("请在料小宝账号.local.json 中填写 phone 和 password")
                result = login(session, phone.strip(), password, secret, iv)
                print("登录业务状态码：", result.get("code"))
                if args.profile or args.paid_upload or any(value is not None for value in (args.publish, args.append, args.pin, args.unpin)):
                    data = result.get("data")
                    token = result.get("token") or (data.get("token") if isinstance(data, dict) else None)
                    if not isinstance(token, str) or not token:
                        raise ValueError("登录响应没有找到 token")
                    session.headers["Authorization"] = f"Bearer {token}"
                if args.paid_upload:
                    attachments = clipboard_images()
                    if not attachments:
                        raise ValueError("未从剪贴板读取到图片")
                    if input(f"将上传 {len(attachments)} 张付费区图片，输入 UPLOAD 确认：").strip() == "UPLOAD":
                        paths = upload_images(session, attachments, "ARTICLE_PAID", secret, iv)
                        for path in paths:
                            print("付费区图片路径：", path)
                    else:
                        print("已取消上传")
                if args.profile:
                    profile = unpack(post(session, "/user/profile", None), secret, iv)
                    print(profile)
                    print("个人资料业务状态码：", profile.get("code"))
                if args.append is not None:
                    append_article(session, args.append, secret, iv, args.clipboard)
                if args.pin is not None or args.unpin is not None:
                    change_pin(session, args.pin or args.unpin, secret, iv, pin=args.pin is not None)
                if args.publish is not None:
                    create_article(session, args.publish, secret, iv, args.clipboard,
                                   presale=args.presale, discount=args.discount,
                                   pinned=args.pinned, price=args.price)
    except (requests.RequestException, ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"联调失败：{exc}\n")
