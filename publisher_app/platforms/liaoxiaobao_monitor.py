"""Read-only merchant monitoring, ordered by actual publication time."""
from .liaoxiaobao import LiaoxiaobaoPlatform
from ..storage import load_session


class LiaoxiaobaoMonitorClient(LiaoxiaobaoPlatform):
    initial_limit = 100

    def __init__(self, credentials=None):
        if credentials is None:
            accounts = load_session('H5监控账号')
            matches = [data for data in accounts.values() if data.get('platform')=='料小宝' and data.get('purpose')=='user_monitor']
            credentials = matches[0] if len(matches)==1 else {}
        super().__init__(credentials=credentials)

    def _records(self, route, payload):
        data = self._send(route,payload)
        if not isinstance(data,dict) or not isinstance(data.get('records'),list):
            raise ValueError('监控响应缺少records列表')
        pages = int(data.get('pages') or 0)
        if not 0 <= pages <= 1000:
            raise ValueError('监控分页数异常，停止读取')
        return data['records'],pages

    def following_records(self):
        merchants = {}
        for page in range(1,1001):
            rows,pages = self._records(f'/follow/list/{page}/100',{'blocked':False})
            for row in rows:
                if row.get('authorId') is None:
                    raise ValueError('关注记录缺少authorId')
                merchants[str(row['authorId'])] = row
            if page >= pages: return list(merchants.values())
            if not rows: raise ValueError('关注列表末页之前为空，未返回不完整数据')
        raise ValueError('关注列表超过分页上限')

    def latest(self, author_id, progress=None):
        articles = {}
        # The API does not order reliably by publishTime. Until a server-side
        # sort option is verified, all pages are needed for an exact top 100.
        for page in range(1,1001):
            rows,pages = self._records(f'/article/list/{page}/100',{
                'followedOnly':True,'authorId':author_id,
            })
            for row in rows:
                if str(row.get('authorId')) != str(author_id):
                    raise ValueError('文章返回商家与请求authorId不匹配')
                if row.get('articleNo') is None:
                    raise ValueError('文章缺少articleNo')
                if row.get('isListed') is not True or row.get('status') != 1:
                    continue
                if not row.get('publishTime'):
                    continue
                articles[str(row['articleNo'])] = row
            if progress: progress(page,pages,len(articles))
            if page >= pages:
                return sorted(articles.values(),key=lambda row:(str(row['publishTime']),str(row['articleNo'])),reverse=True)[:100]
            if not rows: raise ValueError('文章末页之前为空，未返回不完整数据')
        raise ValueError('文章列表超过分页上限')

    def poll_articles(self, author_id, progress=None):
        rows = self.latest(author_id,progress)
        if not hasattr(self,'_seen'): self._seen = {}
        key = str(author_id)
        baseline = key not in self._seen
        seen = self._seen.setdefault(key,set())
        fresh = [] if baseline else [row for row in rows if str(row['articleNo']) not in seen]
        seen.update(str(row['articleNo']) for row in rows)
        return rows,fresh,baseline
