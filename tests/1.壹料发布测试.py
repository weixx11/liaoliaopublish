import json
import os
import requests
from datetime import datetime, timedelta

# 1. 基础配置
LOGIN_URL = 'https://yapi.njyuelu.cn/mgr/mgr/login'
PUBLISH_URL = 'https://yapi.njyuelu.cn/plan/mgr-do/add'
SYN_URL = 'https://yapi.njyuelu.cn/plan/mgr-do/planSynAdd'  # 同步接口
MODIFY_URL = 'https://yapi.njyuelu.cn/plan/mgr-do/modifyContent'

SYN_UPDATE_URL = (
    'https://yapi.njyuelu.cn/plan/mgr-do/planSynUpdate'  # 👈 新增：更新后同步接口
)
USER_GROUP_URL = 'https://yapi.njyuelu.cn/mgr/sys-group/userGroupList'
# userGroupList 接口要求数字 userId；当前测试样例为 435。
TEST_USER_ID = "U20260602182706755MPOY"
CACHE_FILE = 'session.json'

ACCOUNT = __import__("os").environ.get("YILIAO_TEST_ACCOUNT") or input("ACCOUNT: ").strip()
PWD = __import__("os").environ.get("YILIAO_TEST_PASSWORD") or input("PASSWORD: ").strip()

# 创建全局 Session 对象（核心：自动保存和传递 Cookie）
session_client = requests.Session()

# 统一请求头
COMMON_HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,'
        ' like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
}


def login():
  """登录并持久化保存凭证与 Cookie"""
  payload = {'d': {'account': ACCOUNT, 'pwd': PWD, 'proxyTag': ''}}

  try:
    print('🔑 正在请求服务器进行登录...')
    # 使用 session_client 登录，自动捕获 Cookie
    response = session_client.post(
        LOGIN_URL, json=payload, headers=COMMON_HEADERS, timeout=10
    )
    res_data = response.json()

    if res_data.get('c') == 200:
      user_data = res_data.get('d', {})
      session_info = {
          'user_data': user_data,
          'cookies': session_client.cookies.get_dict(),
      }

      with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(session_info, f, ensure_ascii=False, indent=4)
      print('✅ 登录成功，Token 及 Cookie 已成功缓存！')
      return session_info
    else:
      print(f"❌ 登录失败: {res_data.get('m')}")
      return None
  except Exception as e:
    print(f'❌ 登录网络异常: {e}')
    return None


def get_session():
  """获取凭证（优先读取本地缓存并恢复 Cookie）"""
  if os.path.exists(CACHE_FILE):
    try:
      with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        session_info = json.load(f)
        user_data = session_info.get('user_data', {})
        cookies = session_info.get('cookies', {})

        if user_data.get('token'):
          print('⚡ 已加载本地缓存的 Token 与 Cookie，跳过登录步骤。')
          # 恢复 Cookie 到当前的 session_client 中
          session_client.cookies.update(cookies)
          return session_info
    except Exception:
      print('⚠️ 读取本地缓存失败，准备重新登录...')

  return login()


def publish_plan(
    session_info,
    title,
    summary,
    content,
    price='12',
    tags='biao',
):
  """测试发布方案/文章接口"""
  if not session_info:
    print('❌ 无有效凭证，无法发布。')
    return None

  user_data = session_info.get('user_data', {})
  token = user_data.get('token')
  expert_id = user_data.get('expertId')

  # 1. 组装请求头：使用你确认的 Authorization 字段
  headers = COMMON_HEADERS.copy()
  headers['Authorization'] = token  # 如果服务器要求 Bearer 格式，可以改成 f"Bearer {token}"
  # 📌 动态计算时间
  now = datetime.now()
  public_time_str = now.strftime("%Y-%m-%d %H:%M:%S")  # 实时发布时间
  end_time_str = (now + timedelta(hours=24)).strftime(
      "%Y-%m-%d %H:%M:%S"
  )  # 24小时后的截止时间
  # 2. 组装接口真实的 Payload 数据结构
  payload = {
      'd': {
          'id': '',
          'appPush': 1,
          'planPackAuto': 1,
          'planPacks': '',
          'noDiscount': 1,
          'notifyAuto': 0,
          'items': '',
          'title': title,
          'title2': '',
          'summary': f'<p>{summary}</p>'
          if not summary.startswith('<p>')
          else summary,
          'content': f'<p>{content}</p>'
          if not content.startswith('<p>')
          else content,
          'free': 0,
          'needPay': 1,
          'price': str(price),
          'priceReal': str(price),
          'publicTime': public_time_str,
          'endTime': end_time_str,
          'activityId': None,
          'sportsId': 4,
          'expertId': expert_id,
          'tag1': '',
          'tag2': '',
          'tags': tags,
          'labelIds': '',
          'playType': '9001',
          'tagsArray': [tags] if isinstance(tags, str) else tags,
          'presell': 1,
          'updateTimeShow': 0,
          'beginTime': end_time_str,
      }
  }

  print(f'\n🚀 正在提交发布方案：《{title}》...')
  try:
    # 使用带有 Cookie 的 session_client 发送请求
    response = session_client.post(
        PUBLISH_URL, json=payload, headers=headers, timeout=10
    )
    res_data = response.json()

    if res_data.get('c') == 200:
      plan_id = res_data.get('d', {}).get('id')
      print('🎉 发布成功！')
      print(f'   生成方案 ID (id): {plan_id}')
      print(f"   标题: {res_data.get('d', {}).get('title')}")
      print(
          f"   审核状态 (verifyStatus): {res_data.get('d', {}).get('verifyStatus')}"
      )
      return res_data
    else:
      print(f"❌ 发布失败，接口返回: {res_data.get('m')}")

      if res_data.get('c') in [401, 403] or '未登录' in str(res_data.get('m')):
        print('⚠️ 凭证已过期，自动清除本地缓存文件...')
        if os.path.exists(CACHE_FILE):
          os.remove(CACHE_FILE)
      return res_data

  except Exception as e:
    print(f'❌ 请求发生异常: {e}')
    return None


def sync_plan(session_info, plan_id, expert_id_list):
  """测试方案同步接口"""
  if not session_info or not plan_id:
    return None

  user_data = session_info.get('user_data', {})
  token = user_data.get('token')

  headers = COMMON_HEADERS.copy()
  headers['Authorization'] = token

  payload = {'d': {'planId': plan_id, 'expertIdList': expert_id_list}}

  print(f'\n🔄 正在将方案 ID: {plan_id} 同步给其他专家...')
  try:
    response = session_client.post(
        SYN_URL, json=payload, headers=headers, timeout=10
    )
    res_data = response.json()

    if res_data.get('c') == 200:
      print('🎉 方案同步成功！')
      return res_data
    else:
      print(f"❌ 同步失败，接口返回: {res_data.get('m')}")
      return res_data
  except Exception as e:
    print(f'❌ 同步请求异常: {e}')
    return None


def sync_plan(session_info, plan_id, expert_id_list):
  """第二步：测试方案同步接口"""
  if not session_info or not plan_id:
    return None

  user_data = session_info.get('user_data', {})
  token = user_data.get('token')

  headers = COMMON_HEADERS.copy()
  headers['Authorization'] = token

  payload = {'d': {'planId': plan_id, 'expertIdList': expert_id_list}}

  print(f'\n🔄 正在将方案 ID: {plan_id} 同步给其他专家...')
  try:
    response = session_client.post(
        SYN_URL, json=payload, headers=headers, timeout=10
    )
    res_data = response.json()

    if res_data.get('c') == 200:
      print('🎉 方案同步成功！')
      return res_data
    else:
      print(f"❌ 同步失败，接口返回: {res_data.get('m')}")
      return res_data
  except Exception as e:
    print(f'❌ 同步请求异常: {e}')
    return None


def modify_plan(
    session_info, plan_id, new_content, new_price=''
):
  """第三步：测试方案内容修改/再编辑接口"""
  if not session_info or not plan_id:
    print('❌ 缺少凭证或方案 ID，无法修改。')
    return None

  user_data = session_info.get('user_data', {})
  token = user_data.get('token')
  expert_id = user_data.get('expertId')

  headers = COMMON_HEADERS.copy()
  headers['Authorization'] = token

  # 按照你提供的 modifyContent 接口完整结构组装（支持修改标题、摘要、价格等）
  payload = {
      'd': {
          'id': plan_id,  # 👈 必须传入要修改的方案 ID
          'expertId': expert_id,
          'compType': '1',
          'publicTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          'lotteryType': 6,
          'issueNo': None,
          'price': str(new_price),
          'priceReal': str(new_price),
          'beginTime': (datetime.now() + timedelta(hours=24)).strftime(
              '%Y-%m-%d %H:%M:%S'
          ),
          'endTime': (datetime.now() + timedelta(hours=24)).strftime(
              '%Y-%m-%d %H:%M:%S'
          ),
          # 'title': '',
          # 'title2': '',
          # 'summary': f'<p>{new_summary}</p>',
          'content': f'<p>{new_content}</p>'
          if not new_content.startswith('<p>')
          else new_content,
          'playType': '9001',
          'planType': None,
          'hidden': 0,
          'free': 0,
          'matchs': None,
          'status': 0,
          'verifyStatus': 2,
          'verifyMsg': None,
          'activityId': 0,
          'activityName': None,
          'pv': 0,
          'compId': 7,
          'compName': None,
          'sportsId': 4,
          'notifyTime': None,
          'channel': None,
          'labelIds': None,
          'buy': None,
          'roomWeight': 0,
          'refund': 0,
          'totalGold': 0,
          'expertGold': 0,
          'visit': 0,
          'weight': 0,
          'stopBuy': 0,
          'notifyAuto': 0,
          'noDiscount': 1,
          'tags': '',
          'payStatus': 0,
          'planPackAuto': 0,
          'planPacks': '',
          'presell': 1,
          'moreList': None,
          'promotionGold': 0,
          'actualPromotionGold': 0,
          'updateTimeShow': 0,
          'qrcodeList': [],  # 编辑时可以简化或传空列表
      }
  }

  print(f'\n✏️ 正在修改方案 ID: {plan_id} 的内容...')
  try:
    response = session_client.post(
        MODIFY_URL, json=payload, headers=headers, timeout=10
    )
    res_data = response.json()

    if res_data.get('c') == 200 and res_data.get('d') is True:
      print('🎉 方案内容修改成功！')
      return res_data
    else:
      print(f"❌ 修改失败，接口返回: {res_data.get('m')}")
      return res_data
  except Exception as e:
    print(f'❌ 修改请求异常: {e}')
    return None
def sync_update_plan(session_info, plan_id):
  """第四步：内容更新后的同步接口 (planSynUpdate)"""
  if not session_info or not plan_id:
    return None

  user_data = session_info.get('user_data', {})
  token = user_data.get('token')

  headers = COMMON_HEADERS.copy()
  headers['Authorization'] = token

  # 按照你提供的 planSynUpdate 接口结构组装
  payload = {'d': {'planId': plan_id}}

  print(f'\n🔄 正在触发方案更新后的同步接口 (ID: {plan_id})...')
  try:
    response = session_client.post(
        SYN_UPDATE_URL, json=payload, headers=headers, timeout=10
    )
    res_data = response.json()

    if res_data.get('c') == 200:
      print('🎉 更新同步成功！')
      return res_data
    else:
      print(f"❌ 更新同步失败，接口返回: {res_data.get('m')}")
      return res_data
  except Exception as e:
    print(f'❌ 更新同步请求异常: {e}')
    return None


def get_user_groups(session_info, user_id=TEST_USER_ID):
  """查询当前用户下的子商户，列出商户名与同步所需 groupRelateId。"""
  if not session_info:
    print('❌ 无有效凭证，无法查询子商户。')
    return None

  user_data = session_info.get('user_data', {})
  token = user_data.get('token')
  if not token:
    print('❌ 登录信息中没有 Token，无法查询子商户。')
    return None
  numeric_user_id = user_id
  # try:
  #   numeric_user_id = str(user_id)
  # except (TypeError, ValueError):
  #   print(f'❌ userId 必须是数字，当前值: {user_id!r}')
  #   return None

  headers = COMMON_HEADERS.copy()
  headers['Authorization'] = token
  payload = {'d': {'tag1': 2, 'groupType': 1, 'userId': numeric_user_id}}

  print(f'\n🔎 正在查询 userId={numeric_user_id} 的子商户...')
  try:
    response = session_client.post(
        USER_GROUP_URL, json=payload, headers=headers, timeout=15
    )
    response.raise_for_status()
    res_data = response.json()
    if res_data.get('c') != 200:
      print(f"❌ 查询失败: {res_data.get('m')}")
      return res_data

    groups = res_data.get('d') or []
    if not isinstance(groups, list):
      print(f'❌ 接口返回的 d 不是列表: {groups!r}')
      return res_data

    print(f'✅ 查询成功，共 {len(groups)} 个子商户：')
    for group in groups:
      merchant_name = group.get('groupRelateName') or group.get('groupName') or ''
      relate_id = group.get('groupRelateId') or ''
      print(f'   商户名: {merchant_name} | 同步专家 ID: {relate_id}')
    return res_data
  except Exception as e:
    print(f'❌ 查询子商户请求异常: {e}')
    return None

if __name__ == '__main__':
  # 1. 读取/获取凭证信息
  session_info = get_session()

  if session_info:
    u_data = session_info.get('user_data', {})
    print(
        f"当前操作账号: {u_data.get('account')} | 专家 ID:"
        f" {u_data.get('expertId')}"
    )
    # 测试子商户查询；按实际接口参数修改 TEST_USER_ID（示例：435）。
    get_user_groups(session_info, TEST_USER_ID)

    """
    # # 2. 执行一次方案发布测试
    publish_result = publish_plan(
        session_info=session_info,
        title='测试10',
        summary='这是测试摘要内容',
        content='199asd',
        price='13',
        tags='aa',
    )

    # # 3. 如果发布成功，自动触发同步
    if publish_result and publish_result.get('c') == 200:
      plan_id = publish_result.get('d', {}).get('id')
      if plan_id:
        target_expert_ids = [
            'DL20260427184658234VQCG',
            "DL20260506153525345KKML"
            # 'DL20260506153708181HMCX',
        ]
        sync_plan(session_info, plan_id, target_expert_ids)

    modify_result = modify_plan(
        session_info=session_info,
        plan_id=plan_id,
        new_content='新修改1235336',
        new_price='',
    )
    if modify_result and modify_result.get('c') == 200:
        sync_update_plan(session_info, plan_id)
"""