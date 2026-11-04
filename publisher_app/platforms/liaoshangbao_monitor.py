"""Read-only Liaoshangbao user monitoring endpoints."""
from .liaoshangbao import LiaoshangbaoPlatform
from ..config import LSB_BASE_URL


class LiaoshangbaoMonitorClient(LiaoshangbaoPlatform):
    def article_page(self, soid, index=1):
        if not self.logged_in:
            raise RuntimeError('请先登录料商宝用户账号')
        if not str(soid or '').strip():
            raise ValueError('查询文章需要关注商家的 s_user_id（soid）')
        response = self.session.get(LSB_BASE_URL + '/getUserSelds', params={
            'uid':self.uid, 'sid':self.sid, 'soid':soid,
            'index':index, 'seltype':1, 'selid':'',
        }, headers=self._headers(), timeout=(10,60))
        response.raise_for_status()
        result = response.json()
        if result.get('status') != 200:
            raise RuntimeError('查询商家文章失败：{}'.format(result.get('msg') or result.get('status')))
        if not isinstance(result.get('data'),list):
            raise ValueError('商家文章响应 data 不是列表')
        return result['data'], int(result.get('msg') or 0)

    def latest(self, soid, pages=None, limit=100):
        if limit < 1:
            raise ValueError('文章数量上限必须大于0')
        articles = {}
        ordinary = set()
        for index in range(1,(pages if pages is not None else 1000)+1):
            rows, maximum = self.article_page(soid,index)
            for row in rows:
                if row.get('id') is None:
                    raise ValueError('商家文章缺少 id')
                articles[str(row['id'])] = row
                if str(row.get('on_seld_top',0)) != '1':
                    ordinary.add(str(row['id']))
            if index >= maximum or not rows: break
            # Old pinned articles must not consume the recent-article quota.
            # The normal list is read in the server's newest-first order.
            if pages is None and len(ordinary) >= limit: break
        return sorted(articles.values(),key=lambda row:str(row.get('create_time') or ''),reverse=True)[:limit]

    def poll_articles(self, soid):
        rows = self.latest(soid)
        if not hasattr(self,'_article_seen'):
            self._article_seen = {}
        baseline = soid not in self._article_seen
        seen = self._article_seen.setdefault(soid,set())
        fresh = [] if baseline else [row for row in rows if str(row['id']) not in seen]
        seen.update(str(row['id']) for row in rows)
        return rows, fresh, baseline

    def following_page(self, index=1):
        if not self.logged_in:
            raise RuntimeError('请先登录料商宝用户账号')
        response = self.session.get(LSB_BASE_URL + '/getMyGuanZhus', params={
            'index': index, 'uid': self.uid, 'sid': self.sid,
            'seltype': 2, 'selid': '',
        }, headers=self._headers(), timeout=(10, 60))
        response.raise_for_status()
        result = response.json()
        if result.get('status') != 200:
            raise RuntimeError('查询关注商家失败：{}'.format(result.get('msg') or result.get('status')))
        data = result.get('data')
        if not isinstance(data,dict) or not isinstance(data.get('lists'),list):
            raise ValueError('关注商家响应缺少 data.lists')
        pages = int(data.get('maxPage',1))
        if not 0 <= pages <= 1000:
            raise ValueError('关注商家分页数异常')
        return data['lists'], pages

    def following_records(self):
        merchants = {}
        index = 1
        while True:
            rows, pages = self.following_page(index)
            for row in rows:
                if row.get('user_id') is None:
                    raise ValueError('关注商家缺少 user_id')
                merchant_id = str(row['user_id'])
                merchants[merchant_id] = dict(row, user_id=merchant_id)
            if index >= pages:
                break
            if not rows:
                raise ValueError('关注列表在末页之前为空，未将不完整结果作为完整关注列表')
            index += 1
            if index > 1000:
                raise ValueError('关注列表超过分页上限')
        return list(merchants.values())

    def following(self):
        return {row['user_id']: row.get('bzName') or row.get('name') or row['user_id']
                for row in self.following_records()}
