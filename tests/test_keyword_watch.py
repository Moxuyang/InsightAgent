"""Keyword watchlists: literal matching, full-text evidence, dates and user isolation."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app.services.keyword_watch import match_news, normalize_keywords, save_keywords, saved_keywords, saved_watchlist


class KeywordWatchTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.temp.name)/'watch.db')
        with self.connection() as c:
            c.executescript('''
            CREATE TABLE spy_sources(id INTEGER PRIMARY KEY,name TEXT);
            CREATE TABLE spy_data(id INTEGER PRIMARY KEY,source_id INTEGER,title TEXT,url TEXT,summary TEXT,create_at TEXT,update_at TEXT);
            CREATE TABLE deep_collect_results(id INTEGER PRIMARY KEY,spy_data_id INTEGER,full_content TEXT,crawl_status TEXT,crawl_at TEXT,create_at TEXT);
            CREATE TABLE system_configs(id INTEGER PRIMARY KEY,config_key TEXT UNIQUE,config_value TEXT,description TEXT,update_at TEXT);
            INSERT INTO spy_sources VALUES (1,'测试来源');
            INSERT INTO spy_data VALUES (1,1,'企业发布召回公告','https://example.com/1','收到多起投诉','2026-10-22 03:00:00','2026-10-22 03:00:00');
            INSERT INTO spy_data VALUES (2,1,'企业技术发布','https://example.com/2','正常升级','2026-10-22 03:00:01','2026-10-22 03:00:01');
            INSERT INTO spy_data VALUES (3,1,'六月投诉新闻','https://example.com/3','历史投诉','2026-06-11 03:00:00','2026-06-11 03:00:00');
            INSERT INTO spy_data VALUES (4,1,'跨午夜新闻','https://example.com/4','边界投诉','2026-10-21 16:00:00','2026-10-21 16:00:00');
            INSERT INTO spy_data VALUES (5,1,'特殊字符','https://example.com/5','增长100%和a_b；C++','2026-10-22 04:00:00','2026-10-22 04:00:00');
            INSERT INTO deep_collect_results VALUES (1,2,'早期正文','success','2026-10-22 03:00:01','2026-10-22 03:00:01');
            INSERT INTO deep_collect_results VALUES (2,2,'技术发布正文提及数据泄露和AI治理。','success','2026-10-22 03:30:00','2026-10-22 03:30:00');
            ''')
        self.patches=[patch('app.services.keyword_watch.get_connection',self.connection),patch('app.models.system_config.get_connection',self.connection)]
        for p in self.patches:p.start()

    @contextmanager
    def connection(self):
        c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row
        try:
            yield c;c.commit()
        except Exception:
            c.rollback();raise
        finally:c.close()

    def tearDown(self):
        for p in self.patches:p.stop()
        self.temp.cleanup()

    def test_normalization_and_limits(self):
        self.assertEqual(normalize_keywords('投诉， AI\nai;召回、投诉'),['投诉','AI','召回'])
        for value in [[1],['x'*41],[str(i) for i in range(101)]]:
            with self.assertRaises(ValueError):normalize_keywords(value)

    def test_any_matches_titles_summaries_and_full_text(self):
        result=match_news(['召回','数据泄露'],'2026-10-22')
        self.assertEqual(result['count'],2)
        self.assertEqual(result['scanned_count'],4)
        self.assertEqual([r['id'] for r in result['items']],[2,1])
        article=result['items'][0]
        self.assertEqual(article['matched_keywords'],['数据泄露'])
        self.assertEqual(article['content_kind'],'正文')
        self.assertEqual(article['collected_at'],'2026-10-22 11:30:00')
        self.assertTrue(any(p['field']=='正文' and '数据泄露' in p['text'] for p in article['passages']))

    def test_all_can_match_across_fields(self):
        self.assertEqual([r['id'] for r in match_news(['召回','投诉'],'2026-10-22','all')['items']],[1])
        self.assertEqual(match_news(['召回','数据泄露'],'2026-10-22','all')['count'],0)

    def test_day_boundaries_and_no_historical_fallback(self):
        self.assertEqual({r['id'] for r in match_news(['投诉'],'2026-10-22')['items']},{1,4})
        self.assertEqual(match_news(['投诉'],'2026-10-23')['count'],0)

    def test_wildcards_are_literal_not_query_operators(self):
        for word in ['%','_','C++']:
            self.assertEqual([r['id'] for r in match_news([word],'2026-10-22')['items']],[5])
        self.assertEqual(match_news(["' OR 1=1 --"],'2026-10-22')['count'],0)

    def test_saved_watchlists_are_per_user_and_can_clear(self):
        save_keywords(1,['投诉']);save_keywords(2,['召回'])
        self.assertEqual(saved_keywords(1),['投诉'])
        self.assertEqual(saved_keywords(2),['召回'])
        save_keywords(1,[])
        self.assertEqual(saved_keywords(1),[])
        self.assertEqual(saved_keywords(2),['召回'])

    def test_pagination_counts_all_matches_without_duplicates(self):
        first=match_news(['投诉'],'2026-10-22',page=1,limit=1)
        second=match_news(['投诉'],'2026-10-22',page=2,limit=1)
        self.assertEqual(first['count'],2)
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])

    def test_rejects_invalid_inputs(self):
        for args in [([],None),(['投诉'],'bad-date')]:
            with self.assertRaises(ValueError):match_news(*args)
        with self.assertRaises(ValueError):match_news(['投诉'],'2026-10-22','unknown')

    def test_date_range_includes_start_and_end_days(self):
        result=match_news(['投诉'],start_date='2026-06-11',end_date='2026-10-22')
        self.assertEqual({x['id'] for x in result['items']},{1,3,4})
        self.assertEqual(result['start_date'],'2026-06-11')
        self.assertEqual(result['end_date'],'2026-10-22')
        with self.assertRaises(ValueError):match_news(['投诉'],start_date='2026-10-23',end_date='2026-10-22')

    def test_keyword_statistics_cover_all_pages_and_keep_zero_hits(self):
        r=match_news(['投诉','召回','数据泄露','不存在'],start_date='2026-06-11',end_date='2026-10-22',limit=1,levels={'投诉':'问题词','数据泄露':'风险词'})
        self.assertEqual(len(r['items']),1)
        stats={s['keyword']:s for s in r['keyword_stats']}
        self.assertEqual(stats['投诉']['news_count'],3)
        self.assertEqual(stats['召回']['news_count'],1)
        self.assertEqual(stats['数据泄露']['news_count'],1)
        self.assertEqual(stats['不存在']['news_count'],0)
        self.assertEqual(stats['投诉']['category'],'问题词')

    def test_categories_are_saved_and_old_keyword_banks_still_load(self):
        save_keywords(1,['投诉','召回'],{'投诉':'问题词','召回':'风险词'})
        self.assertEqual(saved_watchlist(1)['levels'],{'投诉':'问题词','召回':'风险词'})
        save_keywords(1,['投诉'])
        self.assertEqual(saved_watchlist(1)['levels'],{'投诉':'问题词'})
        with self.connection() as c:
            c.execute("INSERT INTO system_configs(config_key,config_value) VALUES (?,?)",('sentiment_watchlist_2','["AI"]'))
        self.assertEqual(saved_watchlist(2),{'keywords':['AI'],'levels':{'AI':'关注词'}})

    def test_agent_watch_tool_uses_only_requesting_users_bank(self):
        from app.services.agent_context import watch_context
        save_keywords(1,['召回']);save_keywords(2,['数据泄露'])
        scope={'start':'2026-10-22T00:00:00+08:00','end_exclusive':'2026-10-23T00:00:00+08:00'}
        one,sources_one=watch_context('今天的关注词',1,scope)
        two,sources_two=watch_context('今天的关注词',2,scope)
        self.assertEqual(one['keywords'],['召回'])
        self.assertEqual(two['keywords'],['数据泄露'])
        self.assertEqual(sources_one[0]['id'],1)
        self.assertEqual(sources_two[0]['id'],2)

    def test_group_agent_does_not_read_private_banks(self):
        from app.services.agent_context import watch_context
        with patch('app.services.keyword_watch.saved_watchlist',side_effect=AssertionError('private read')):
            context,sources=watch_context('分析我的舆情',None,{})
        self.assertFalse(context['available'])
        self.assertIsNone(sources)

    def test_risk_evidence_survives_many_generic_matches(self):
        from app.services.agent_context import watch_context
        save_keywords(1,['企业','数据泄露'],{'企业':'关注词','数据泄露':'风险词'})
        with self.connection() as c:
            for i in range(6,14):
                c.execute('INSERT INTO spy_data VALUES (?,1,?,?,?,?,?)',(i,'企业普通进展','https://example.com/'+str(i),'常规消息','2026-10-22 05:00:00','2026-10-22 05:00:00'))
        context,sources=watch_context('今天的风险词',1,{'start':'2026-10-22T00:00:00+08:00','end_exclusive':'2026-10-23T00:00:00+08:00'})
        self.assertEqual(sources[0]['id'],2)
        self.assertEqual(len(sources),6)


if __name__=='__main__':unittest.main()
