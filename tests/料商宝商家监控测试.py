"""Read-only following test. No publish/update calls."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from publisher_app.platforms.liaoshangbao_monitor import LiaoshangbaoMonitorClient
from publisher_app.config import APP_DIR
from publisher_app.storage import load_session, read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('liaoshangbao_monitor.local.json'))
    parser.add_argument('--use-saved', action='store_true', help='明确使用统一工具已保存的料商宝发布账号会话')
    parser.add_argument('--soid',help='指定商家的 s_user_id，测试文章列表')
    parser.add_argument('--pages',type=int,default=None,help='可选：限制测试页数；默认获取最近100篇，跳过旧置顶占位')
    parser.add_argument('--watch',action='store_true',help='首次载入100篇后持续检测新增文章')
    parser.add_argument('--interval',type=int,default=60,help='监控间隔秒数，至少10，默认60')
    args = parser.parse_args()
    if args.pages is not None and not 1 <= args.pages <= 20: parser.error('--pages 范围为1到20')
    if args.watch and (not args.soid or args.pages is not None): parser.error('--watch 需要 --soid，且不能限制 --pages')
    if args.interval < 10: parser.error('--interval 至少10秒')
    config = load_session('料商宝') if args.use_saved else read_json(args.config,{})
    client = LiaoshangbaoMonitorClient(uid=config.get('uid'),sid=config.get('sid'))
    client.session.cookies.update(config.get('cookies',{}))
    if not client.logged_in:
        if not config.get('mobile') or not config.get('pwd'):
            parser.error('请将 example.json 复制为 liaoshangbao_monitor.local.json，填写 mobile/pwd 或 uid/sid')
        client.login(config['mobile'],config['pwd'])
        print('登录成功（status=200；不使用 success 判断）')
    try:
        records = client.latest(args.soid,args.pages) if args.soid else client.following_records()
    except Exception as exc:
        # requests exceptions can include a URL containing sid.
        message = str(exc).replace(str(client.sid),'[隐藏]') if client.sid else str(exc)
        raise RuntimeError(message) from None
    output = APP_DIR / ('料商宝监控文章.local.json' if args.soid else '料商宝关注商家.local.json')
    write_json(output,records)
    print('查询成功，共 {} 条结果'.format(len(records)))
    for row in records:
        if args.soid:
            print('{} | id={} | {}'.format(row.get('create_time',''),row['id'],row.get('title','')))
        else:
            print('{} | user_id={} | s_user_id={}'.format(row.get('name',''),row['user_id'],row.get('s_user_id','')))
    print('已保存：{}'.format(output))
    if args.watch:
        client._article_seen = {args.soid:{str(row['id']) for row in records}}
        print('首次100篇作为基线，不提醒；开始检测新增文章，Ctrl+C停止。',flush=True)
        try:
            while True:
                time.sleep(args.interval)
                try:
                    rows,fresh,_ = client.poll_articles(args.soid)
                    saved = {str(row['id']):row for row in records}
                    saved.update({str(row['id']):row for row in rows})
                    records = sorted(saved.values(),key=lambda row:str(row.get('create_time') or ''),reverse=True)
                    write_json(output,records)
                    print('{} 检查完成，新增 {} 篇'.format(time.strftime('%Y-%m-%d %H:%M:%S'),len(fresh)),flush=True)
                    for row in fresh: print('{} | {}'.format(row.get('create_time',''),row.get('title','')),flush=True)
                except Exception as exc:
                    print('检查失败：{}'.format(str(exc).replace(str(client.sid),'[隐藏]')),flush=True)
        except KeyboardInterrupt:
            print('已停止监控')


if __name__ == '__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
