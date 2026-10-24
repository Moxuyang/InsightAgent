import unittest
from datetime import datetime
from app.services.news_qa import CHINA, time_scope
from app.services.agent_context import wants_watch_analysis


class AgentIntentTest(unittest.TestCase):
    def test_empty_result_word_is_not_a_watch_request(self):
        self.assertFalse(wants_watch_analysis('昨天采集了哪些新闻？没有命中就说明，不要补今天的。'))
        self.assertTrue(wants_watch_analysis('今天我的关键词命中了哪些新闻'))

    def test_first_relative_day_keeps_query_target(self):
        start,end,label,kind=time_scope('昨天采集了哪些新闻？不要把今天补进来。',datetime(2026,10,22,tzinfo=CHINA))
        self.assertEqual(start.day,21)
        self.assertEqual(end.day,22)
        self.assertEqual(label,'昨天')

    def test_today_query_with_yesterday_exclusion(self):
        start,end,label,kind=time_scope('今天的新闻，不要混入昨天的',datetime(2026,10,22,tzinfo=CHINA))
        self.assertEqual(start.day,22)


if __name__=='__main__':unittest.main()
