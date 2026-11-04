"""料商宝登录接口测试脚本。

运行：python 料商宝登录测试.py
依赖：requests（pip install requests）

密码通过隐藏输入读取，不会写入文件或打印到终端。
"""
import getpass
import json
import requests


LOGIN_URL = "https://qwer.lszs.red/lsb/toMobileLogin"
TIMEOUT = 15


def test_login(mobile, password):
    """以 application/x-www-form-urlencoded 表单方式调用登录接口。"""
    session = requests.Session()
    try:
        response = session.post(
            LOGIN_URL,
            data={"mobile": mobile, "pwd": password},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://qwer.lszs.red/lsb/loginIndex"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print("请求失败：{}".format(exc))
        return False

    try:
        result = response.json()
    except ValueError:
        print("接口未返回 JSON，HTTP 状态：{}".format(response.status_code))
        print(response.text[:1000])
        return False

    # 不输出 data 中的 sid，避免把会话凭证暴露在终端记录里。
    safe_result = dict(result)
    data = safe_result.get("data")
    if isinstance(data, str) and "sid=" in data:
        safe_result["data"] = "uid=...&sid=***"
    print("接口响应：{}".format(json.dumps(safe_result, ensure_ascii=False)))

    if result.get("status") == 200:
        print("登录成功。")
        return True

    print("登录失败，接口状态码：{}，信息：{}".format(result.get("status"), result.get("msg")))
    return False


if __name__ == "__main__":
    account = input("料商宝账号（手机号）：").strip()
    secret = getpass.getpass("密码：")
    test_login(account, secret)
