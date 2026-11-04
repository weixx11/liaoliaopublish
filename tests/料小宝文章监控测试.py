"""Standalone, read-only latest-publication monitoring test."""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from publisher_app.platforms.liaoxiaobao_monitor import LiaoxiaobaoMonitorClient
from publisher_app.config import APP_DIR
from publisher_app.storage import write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--author-id',help='不指定时仅查询关注商家，便于选择authorId')
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--interval',type=int,default=60)
    args = parser.parse_args()
    if args.interval < 10: parser.error('检查间隔至少10秒')
    if args.watch and not args.author_id: parser.error('--watch需要--author-id')
    client = LiaoxiaobaoMonitorClient()
    if not client.logged_in: parser.error('请先在统一工具的料小宝用户监控登录页登录；多账号时请使用统一界面选择账号')
    client._send('/user/profile',{})
    if not args.author_id:
        merchants = client.following_records()
        for row in merchants:
            print('{} | authorId={}'.format(row.get('authorRemarkName') or row.get('authorNickname') or row.get('name') or '',row['authorId']))
        return
    output = APP_DIR/'料小宝最近文章.local.json'
    def progress(page,pages,count):
        if page==1 or page%10==0 or page==pages:
            print(f'分页核对 {page}/{pages}，已读取在售文章{count}篇',flush=True)
    while True:
        start = time.monotonic()
        try:
            rows,fresh,baseline = client.poll_articles(args.author_id,progress)
            fields = ('articleNo','authorId','authorName','title','summary','publishTime','originalPrice','discountPrice','discountPercent','isPinned','isPreSale','isListed','status')
            write_json(output,[{field:row.get(field) for field in fields} for row in rows])
            print('{} {}：保留最近{}篇，新增{}篇，耗时{:.1f}秒'.format(time.strftime('%Y-%m-%d %H:%M:%S'),'首次基线' if baseline else '检查完成',len(rows),len(fresh),time.monotonic()-start),flush=True)
            displayed = sorted(rows if baseline else fresh,
                               key=lambda row:(str(row['publishTime']),str(row['articleNo'])),reverse=True)
            if displayed:
                print('序号 | 发布时间（从新到旧） | 文章ID | 完整标题',flush=True)
            for number,row in enumerate(displayed,1):
                print('{:03d} | {} | {} | {}'.format(number,row['publishTime'],row['articleNo'],row.get('title','')),flush=True)
            print(f'已保存：{output.name}',flush=True)
        except Exception as exc:
            print(f'检查失败：{type(exc).__name__}；未用失败结果覆盖缓存或基线。',flush=True)
            if not args.watch: raise
        if not args.watch: break
        time.sleep(args.interval)


if __name__ == '__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    try: main()
    except KeyboardInterrupt: print('已停止监控')
