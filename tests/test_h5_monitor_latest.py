import unittest
from unittest.mock import Mock
from publisher_app.platforms.h5_monitor import MonitorClient


class LatestArticlesTests(unittest.TestCase):
    def test_subtitle_uses_title_fields_not_free_summary(self):
        client=MonitorClient('红料')
        client.call=Mock(return_value=[dict(planId=1,planTitle='主标题',title2='副标题'),dict(planId=2,planTitle='主标题',summary='免费内容')])
        rows=client.latest('expert')
        self.assertEqual(rows[0]['planSubtitle'],'副标题')
        self.assertEqual(rows[1]['planSubtitle'],'')

    def test_both_platforms_keep_latest_100(self):
        rows = [dict(planId=i,planPublicTime=f'2026-11-04 {i//60:02d}:{i%60:02d}:00') for i in range(120)]
        for platform in ('壹料','红料'):
            for response in (rows,dict(rows=rows)):
                with self.subTest(platform=platform,response_type=type(response)):
                    client = MonitorClient(platform,dict(user_id='user'))
                    client.call = Mock(return_value=response)
                    result = client.latest('expert')
                    self.assertEqual(len(result),100)
                    self.assertEqual(result[0]['planId'],119)
                    self.assertEqual(result[-1]['planId'],20)
                    self.assertEqual(client.call.call_args.args[0],'/plan/app-plan-do/expertLastPlan')

    def test_fewer_than_100_keeps_actual_count(self):
        client = MonitorClient('壹料')
        client.call = Mock(return_value=[dict(planId=1,planPublicTime='2026-11-04 01:00:00')])
        self.assertEqual(len(client.latest('expert')),1)


if __name__ == '__main__': unittest.main()
