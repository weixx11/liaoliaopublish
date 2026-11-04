"""Convert Liaoshangbao user responses to the shared monitoring fields."""
from decimal import Decimal, InvalidOperation
from .liaoshangbao_monitor import LiaoshangbaoMonitorClient


class LiaoshangbaoMonitorAdapter(LiaoshangbaoMonitorClient):
    initial_limit = 100

    def __init__(self, saved=None):
        saved = saved or {}
        super().__init__(uid=saved.get('uid'),sid=saved.get('sid'))
        self.user_id = str(saved.get('user_id') or saved.get('uid') or '')
        self.session.cookies.update(saved.get('cookies',{}))
        self.merchant_records = {}

    def login(self, mobile, password):
        saved = super().login(mobile,password)
        self.user_id = str(saved['uid'])
        return dict(saved,user_id=self.user_id,name=mobile,phone=mobile,
                    cookies=self.session.cookies.get_dict(),platform='料商宝')

    def following(self):
        records = self.following_records()
        if any(not row.get('s_user_id') for row in records):
            raise ValueError('关注商家缺少 s_user_id，无法查询文章')
        self.merchant_records = {str(row['s_user_id']):row for row in records}
        return {key:row.get('bzName') or row.get('name') or row['user_id']
                for key,row in self.merchant_records.items()}

    def latest(self, expert):
        rows = super().latest(expert)
        result = []
        for row in rows:
            price = row.get('price')
            actual = price
            try:
                discount = Decimal(str(row.get('all_zk',10)))
                if 0 < discount < 10:
                    actual = str((Decimal(str(price))*discount/10).quantize(Decimal('.01')))
            except (InvalidOperation,TypeError):
                pass
            result.append(dict(row,planId=str(row['id']),planTitle=row.get('title') or '',
                               planSubtitle=row.get('short_msg') or '',
                               planPublicTime=row.get('create_time') or '',priceReal=actual,
                               top=str(row.get('on_seld_top',0))=='1'))
        return result
