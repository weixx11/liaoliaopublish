"""Normalize verified Liaoxiaobao monitoring responses for the desktop UI."""
from .liaoxiaobao_monitor import LiaoxiaobaoMonitorClient


class LiaoxiaobaoMonitorAdapter(LiaoxiaobaoMonitorClient):
    def __init__(self, saved=None):
        super().__init__(credentials={} if saved is None else saved)
        self.user_id = str(self.credentials.get('user_id') or '')
        self.merchant_records = {}

    def login(self, phone, password):
        self.credentials = self._login_credentials(phone,password)
        self._authorize()
        profile = self._send('/user/profile',{})
        if profile.get('userId') is None:
            raise ValueError('料小宝本人资料缺少userId')
        self.user_id = str(profile['userId'])
        return dict(self.credentials,platform='料小宝',purpose='user_monitor',
                    user_id=self.user_id,name=profile.get('nickname') or phone,phone=phone)

    def following(self):
        records = self.following_records()
        self.merchant_records = {str(row['authorId']):row for row in records}
        return {key:row.get('authorRemarkName') or row.get('authorNickname') or row.get('name') or key
                for key,row in self.merchant_records.items()}

    def latest(self, author_id, progress=None):
        rows = super().latest(author_id,progress)
        return [dict(row,planId=str(row['articleNo']),planTitle=row.get('title') or '',
                     planSubtitle=row.get('summary') or '',
                     planPublicTime=row['publishTime'],price=row.get('originalPrice'),
                     priceReal=row.get('discountPrice') if row.get('discountPrice') is not None else row.get('originalPrice'),
                     top=bool(row.get('isPinned'))) for row in rows]
