"""Read-only probes for verified frontend routes; no writes to the platform."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from publisher_app.platforms.liaoxiaobao_monitor import LiaoxiaobaoMonitorClient
from publisher_app.config import APP_DIR
from publisher_app.storage import write_json


def without_credentials(value):
    if isinstance(value,dict):
        return {key:without_credentials(item) for key,item in value.items()
                if not any(word in key.lower() for word in ('token','secret','password','authorization','cookie')) and key.lower() not in ('iv','sid','pwd')}
    if isinstance(value,list): return [without_credentials(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description='料小宝用户监控只读测试')
    parser.add_argument('--author-id',help='关注列表返回的商家authorId，用于查询文章')
    args = parser.parse_args()
    platform = LiaoxiaobaoMonitorClient()
    if not platform.logged_in:
        parser.error('请先在统一工具的料小宝用户监控登录页登录；多账号时请使用统一界面选择账号')
    output = {}
    steps = [('profile','/user/profile',{}),('counts','/follow/counts',{}),
             ('following','/follow/list/1/100',{'blocked':False})]
    if args.author_id:
        steps.append(('articles','/article/list/1/100',{'followedOnly':True,'authorId':args.author_id}))
    path = APP_DIR / '料小宝监控测试.local.json'
    failed = False
    for name,route,payload in steps:
        try:
            value = platform._send(route,payload)
            output[name] = without_credentials(value)
            keys = ', '.join(value.keys()) if isinstance(value,dict) else type(value).__name__
            print(f'{name} 成功，返回字段：{keys}',flush=True)
            if isinstance(value,dict) and isinstance(value.get('records'),list):
                rows = value['records']
                print(f'本页 {len(rows)} 条；首条字段：'+(', '.join(rows[0].keys()) if rows else '无'),flush=True)
        except Exception as exc:
            print(f'{name} 失败：{type(exc).__name__}。若会话失效，请先重新登录。',flush=True)
            output[name] = {'error_type':type(exc).__name__}
            failed = True
            break
    write_json(path,output)
    print(f'结果已保存：{path.name}',flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    raise SystemExit(main())
