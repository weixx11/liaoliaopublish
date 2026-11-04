"""料商宝文章追加/修改接口测试。

运行：python 料商宝修改测试.py
提交前必须输入 UPDATE 确认。
"""
import getpass
import json

import requests

from 料商宝发布测试 import login


BASE_URL = "https://qwer.lszs.red/lsb"
UPDATE_URL = BASE_URL + "/updatePro"
TOP_URL = BASE_URL + "/toSeldTop"
TIMEOUT = 20


def update_article(session, uid, sid, pid, title, short_msg, content, price="",
                   show_label="biaobiao", presale=1, can_discount=1):
    """调用 updatePro 追加文章内容；pid 是 addPro 返回的文章 ID。"""
    if not pid.strip():
        raise ValueError("pid 不能为空")
    fields = [
        ("uid", uid), ("sid", sid), ("pid", pid.strip()),
        ("title", title), ("shortMsg", short_msg), ("content", content),
        ("price", str(price)), ("customPrice", ""), ("showLabel", show_label),
        ("canBuyCount", "0"), ("customCount", ""), ("playTime", ""),
        ("freeTime", ""), ("validTime", ""), ("onSeld", "1"),
        ("fsLv", "0"), ("allZK", "10"), ("canZK", "1" if can_discount else "0"),
        ("canVip", "1"), ("canAgain", "0"), ("gid", "0"),
        ("bgimgid", "img/a001.png"), ("showLabel", show_label),
        ("shortmsg", short_msg), ("content", content),
        ("preSale", "1" if presale else "0"),
    ]
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Origin": "https://qwer.lszs.red",
        "Referer": "https://qwer.lszs.red/lsb/updateIndex?uid={}&sid={}&pid={}".format(uid, sid, pid),
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Mobile Safari/537.36",
    }
    # Empty file part ensures multipart/form-data even when no image is attached.
    response = session.post(
        UPDATE_URL,
        data=fields,
        files={"tmpFile0": ("", b"", "application/octet-stream")},
        headers=headers,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"http_status": response.status_code, "raw": response.text[:2000]}


def toggle_top(session, uid, sid, pid, action="top"):
    """调用同一个 toSeldTop 接口；该接口根据当前状态执行置顶或取消置顶。"""
    if not pid.strip():
        raise ValueError("pid 不能为空")
    if action not in ("top", "untop"):
        raise ValueError("action 只能是 top 或 untop")
    headers = {
        "Accept": "*/*",
        "Origin": "https://qwer.lszs.red",
        "Referer": "https://qwer.lszs.red/lsb/myPro?uid={}&sid={}".format(uid, sid),
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Mobile Safari/537.36",
    }
    response = session.post(
        TOP_URL,
        data={"uid": uid, "sid": sid, "pid": pid.strip()},
        headers=headers,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"http_status": response.status_code, "raw": response.text[:2000]}


if __name__ == "__main__":
    http = requests.Session()
    mobile = __import__("os").environ.get("LSB_TEST_ACCOUNT") or input("ACCOUNT: ").strip()
    password = __import__("os").environ.get("LSB_TEST_PASSWORD") or input("PASSWORD: ").strip()
    try:
        uid, sid = login(http, mobile, password)
        print("登录成功，sid 已隐藏。")
        operation = input("选择操作：1=追加内容，2=置顶，3=取消置顶：").strip()
        pid = input("文章 pid（addPro 返回的文章 ID）：").strip()
        if operation in ("2", "3"):
            action = "top" if operation == "2" else "untop"
            label = "置顶" if action == "top" else "取消置顶"
            print("\n将对文章 pid={} 执行{}。".format(pid, label))
            if input("确认请输入 TOP：").strip() != "TOP":
                print("已取消，未执行操作。")
            else:
                result = toggle_top(http, uid, sid, pid, action)
                print("操作接口响应：{}".format(json.dumps(result, ensure_ascii=False)))
        else:
            title = input("更新后的标题：").strip()
            short_msg = input("短摘要：").strip()
            content = input("本次追加内容：").strip()
            price = input("价格：").strip()
            presale = input("预售：1=是，0=否（默认 1）：").strip() or "1"
            can_discount = input("允许折扣：1=是，0=无折扣（默认 1）：").strip() or "1"
            if presale not in ("0", "1") or can_discount not in ("0", "1"):
                raise ValueError("预售和折扣参数只能输入 0 或 1")
            print("\n将追加更新文章 pid={}，标题：{}".format(pid, title))
            if input("确认提交请输入 UPDATE：").strip() != "UPDATE":
                print("已取消，未提交修改。")
            else:
                result = update_article(
                    http, uid, sid, pid, title, short_msg, content, price,
                    presale=int(presale), can_discount=int(can_discount),
                )
                print("修改接口响应：{}".format(json.dumps(result, ensure_ascii=False)))
                if isinstance(result, dict) and result.get("status") == 200:
                    print("接口状态码为 200。")
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print("测试失败：{}".format(exc))
