"""News retrieval, graph streaming, persistence and ownership without external API calls."""
import asyncio
from contextlib import contextmanager
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from datetime import datetime
from unittest.mock import patch

from app.services.news_qa import build_news_graph, retrieve_news, make_messages, CHINA
from app.controllers.news_qa import prepare_turn, persist_answer


class NewsQaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name)/'qa.db')
        with self.connection() as c:
            c.executescript('''
                CREATE TABLE spy_sources(id INTEGER PRIMARY KEY,name TEXT);
                CREATE TABLE spy_data(id INTEGER PRIMARY KEY,source_id INTEGER,title TEXT,url TEXT,summary TEXT,keyword TEXT,create_at TEXT,update_at TEXT);
                CREATE TABLE deep_collect_results(id INTEGER PRIMARY KEY,spy_data_id INTEGER,full_content TEXT,crawl_status TEXT,crawl_at TEXT,create_at TEXT);
                CREATE TABLE ai_models(id INTEGER PRIMARY KEY,name TEXT,model_name TEXT,api_key TEXT,base_url TEXT,is_default INTEGER,total_tokens INTEGER DEFAULT 0);
                CREATE TABLE chat_sessions(id INTEGER PRIMARY KEY,user_id INTEGER,title TEXT,is_active INTEGER DEFAULT 1,update_at TEXT);
                CREATE TABLE chat_messages(id INTEGER PRIMARY KEY,session_id INTEGER,role TEXT,content TEXT,tokens_used INTEGER);
                CREATE TABLE user_queries(id INTEGER PRIMARY KEY,user_id INTEGER,query_text TEXT,response_text TEXT,tokens_used INTEGER);
                CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT);
                INSERT INTO spy_sources VALUES (1,'测试新闻源');
                INSERT INTO spy_data VALUES (1,1,'新能源产业新闻','https://example.com/energy','新能源摘要','新能源','2026-10-21','2026-10-21');
                INSERT INTO spy_data VALUES (2,1,'体育赛事','https://example.com/sport','体育摘要','体育','2026-10-22','2026-10-22');
                INSERT INTO deep_collect_results VALUES (1,1,'新能源行业正文：本周发布行业研究报告。','success','2026-10-21','2026-10-21');
                INSERT INTO deep_collect_results VALUES (2,1,'新能源最新正文：本周新增三项研究。','success','2026-10-23','2026-10-23');
                INSERT INTO ai_models(id,name,model_name,api_key,base_url,is_default) VALUES (1,'千问','qwen-plus','test-secret','https://example.com/v1',1);
            ''')
        self.patches = [patch('app.services.news_qa.get_connection',self.connection),patch('app.controllers.news_qa.get_connection',self.connection),patch('app.services.news_qa.current_time',return_value=datetime(2026,10,23,12,tzinfo=CHINA))]
        for p in self.patches: p.start()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def test_retrieval_uses_latest_full_text_and_deduplicates(self):
        sources = retrieve_news('总结新能源新闻')
        self.assertEqual(len(sources),1)
        self.assertIn('三项研究',sources[0]['excerpt'])
        self.assertEqual(sources[0]['content_kind'],'正文')
        self.assertEqual(sources[0]['number'],1)

    def test_no_match_does_not_use_unrelated_news(self):
        self.assertEqual(retrieve_news('量子计算'),[])
        self.assertEqual(len(retrieve_news('最近有哪些新闻')),2)
        sources=retrieve_news('这些再详细说明',[{'role':'user','content':'新能源'}])
        self.assertEqual(sources[0]['id'],1)

    def test_natural_latest_requests_return_saved_news(self):
        for question in ['我最新采集的新闻','我最近采集了什么新闻','最新采集的新闻有哪些',
                         '帮我看看刚刚抓取的新闻','最近有什么资讯','我刚才收集的文章']:
            with self.subTest(question=question):
                sources=retrieve_news(question)
                self.assertEqual(len(sources),2 if '最近' in question else 1)
                self.assertEqual(sources[0]['id'],1)
                self.assertEqual(sources[0]['collected_at'],'2026-10-23 08:00:00')

    def test_today_filters_china_day_boundaries_in_sql(self):
        with self.connection() as c:
            for i,stamp in [(3,'2026-10-21 16:00:00'),(4,'2026-10-21 15:59:59'),(5,'2026-10-22 15:59:59'),(6,'2026-10-22 16:00:00'),(7,'2026-06-11 12:00:00')]:
                c.execute('INSERT INTO spy_data VALUES (?,1,?,?,?,?,?,?)',(i,'边界新闻','https://example.com/'+str(i),'摘要','',stamp,stamp))
        rows,meta=retrieve_news('今天收集到的新闻是什么',now=datetime(2026,10,22,12,tzinfo=CHINA),with_meta=True)
        self.assertEqual({s['id'] for s in rows},{2,3,5})
        self.assertEqual(meta['matched_count'],3)
        self.assertEqual(meta['start'],'2026-10-22T00:00:00+08:00')
        self.assertEqual(next(s for s in rows if s['id']==3)['collected_at'],'2026-10-22 00:00:00')

    def test_empty_today_never_fills_with_older_news(self):
        self.assertEqual(retrieve_news('今天的新闻',now=datetime(2026,10,25,12,tzinfo=CHINA)),[])

    def test_latest_day_does_not_pad_with_june_records(self):
        with self.connection() as c:
            c.execute("INSERT INTO spy_data VALUES (99,1,'六月旧新闻','https://example.com/old','旧摘要','','2026-06-11','2026-06-11')")
        rows,meta=retrieve_news('最新采集的新闻',with_meta=True)
        self.assertEqual([s['id'] for s in rows],[1])
        self.assertEqual(meta['scope'],'最新采集日 2026-10-23')
        self.assertEqual(meta['matched_count'],1)

    def test_result_limit_does_not_change_total_matching_count(self):
        with self.connection() as c:
            for i in range(3,10):
                c.execute('INSERT INTO spy_data VALUES (?,1,?,?,?,?,?,?)',(i,'最新新闻','https://example.com/'+str(i),'摘要','','2026-10-23 01:00:00','2026-10-23 01:00:00'))
        rows,meta=retrieve_news('最新三条新闻',with_meta=True)
        self.assertEqual(len(rows),3)
        self.assertEqual(meta['shown_count'],3)
        self.assertEqual(meta['matched_count'],8)

    def test_relative_day_window_is_not_a_keyword(self):
        rows=retrieve_news('最近3天的新闻',now=datetime(2026,10,25,12,tzinfo=CHINA))
        self.assertEqual([s['id'] for s in rows],[1])

    def test_explicit_date_and_topic_are_both_constraints(self):
        now=datetime(2026,10,22,12,tzinfo=CHINA)
        self.assertEqual(retrieve_news('今天的新能源新闻',now=now),[])
        self.assertEqual([s['id'] for s in retrieve_news('2026年10月22日的新闻',now=now)],[2])

    def test_handoff_date_range_includes_both_dates(self):
        rows,meta=retrieve_news('分析2026-10-21至2026-10-23采集的新闻',with_meta=True)
        self.assertEqual({s['id'] for s in rows},{1,2})
        self.assertEqual(meta['kind'],'range')
        with self.assertRaises(ValueError):retrieve_news('2026-10-23至2026-10-21的新闻')

    def test_role_and_business_context_cannot_replace_base_rules(self):
        messages=make_messages('分析新闻',[],[],business={'keyword_watch':{'matched_count':2}},persona={'name':'新闻分析员','role':'行业分析'})
        self.assertIn('不得编造',messages[0]['content'])
        self.assertTrue(any('已执行的只读业务工具' in m['content'] for m in messages))
        self.assertTrue(any('新闻分析员' in m['content'] for m in messages))

    def test_watch_graph_replaces_generic_sources_with_user_matches(self):
        from unittest.mock import AsyncMock
        source={'id':99,'number':1,'title':'监测命中新闻','url':'https://example.com/watch','source_name':'fixture','content_kind':'摘要','excerpt':'投诉命中'}
        context={'available':True,'matched_count':1,'start_date':'2026-10-23','end_date':'2026-10-23'}
        class Client:
            def __init__(self,**kwargs):self.chat=NS(completions=self)
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def create(self,**kwargs):
                self.test_messages=kwargs['messages']
                async def chunks():yield NS(choices=[NS(delta=NS(content='监测结论 [1]'))],usage=NS(total_tokens=2))
                return chunks()
        async def run():
            graph=build_news_graph({'api_key':'fixture','base_url':'https://example.com','model_name':'qwen-plus'},Client)
            events=[]
            async for mode,event in graph.astream({'question':'今天的关注词命中了什么','history':[],'user_id':1},stream_mode=['custom','updates']):
                if mode=='custom':events.append(event)
            return events
        with patch('app.services.agent_context.watch_context',return_value=(context,[source])):
            events=asyncio.run(run())
        sources=[e for e in events if e['type']=='sources']
        self.assertEqual(len(sources),1)
        self.assertEqual(sources[0]['sources'][0]['id'],99)

    def test_prompt_uses_current_clock_over_bad_historical_answer(self):
        rows,meta=retrieve_news('今天的新闻',with_meta=True)
        messages=make_messages('今天的新闻',[{'role':'assistant','content':'今天是2024年6月18日，2026年是模拟数据'}],rows,retrieval=meta)
        self.assertIn('2026-10-23',messages[0]['content'])
        self.assertIn('北京时间',messages[0]['content'])
        self.assertIn('时间过滤',messages[-3]['content'])

    def test_latest_topic_does_not_fall_back_to_unrelated_news(self):
        self.assertEqual([s['id'] for s in retrieve_news('最新新能源新闻')],[1])
        self.assertEqual(retrieve_news('最新量子计算新闻'),[])

    def test_recent_discovery_orders_ahead_of_older_full_text(self):
        with self.connection() as c:
            c.execute("UPDATE spy_data SET update_at='2026-10-24' WHERE id=2")
        self.assertEqual(retrieve_news('最新采集的新闻')[0]['id'],2)

    def test_prompt_has_separate_system_rules_and_evidence(self):
        messages=make_messages('新能源',[],retrieve_news('新能源'))
        self.assertEqual(messages[0]['role'],'system')
        self.assertIn('不得编造',messages[0]['content'])
        self.assertIn('新能源最新正文',messages[-2]['content'])
        self.assertEqual(messages[-1],{'role':'user','content':'新能源'})

    def test_turn_ownership_and_atomic_persistence(self):
        sid, history, model=prepare_turn(11,0,'新能源')
        self.assertEqual(history,[])
        with self.assertRaises(PermissionError): prepare_turn(22,sid,'不能写入')
        persist_answer(11,sid,'新能源','参考 [1]',9,model['id'],retrieve_news('新能源'))
        with self.connection() as c:
            rows=c.execute('SELECT role,content FROM chat_messages ORDER BY id').fetchall()
            self.assertEqual([r['role'] for r in rows],['user','assistant'])
            self.assertIn('https://example.com/energy',rows[-1]['content'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM user_queries').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT total_tokens FROM ai_models').fetchone()[0],9)

    def test_real_graph_streams_sources_then_tokens(self):
        class FakeClient:
            def __init__(self,**kwargs): self.chat=NS(completions=self)
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def create(self,**kwargs):
                self.asserted=kwargs
                async def chunks():
                    yield NS(choices=[NS(delta=NS(content='根据新闻'))],usage=None)
                    yield NS(choices=[NS(delta=NS(content=' [1]'))],usage=None)
                    yield NS(choices=[],usage=NS(total_tokens=9))
                return chunks()
        async def run():
            graph=build_news_graph({'api_key':'secret','base_url':'https://example.com','model_name':'qwen-plus'},FakeClient)
            events=[]
            async for mode, payload in graph.astream({'question':'新能源','history':[]},stream_mode=['custom','updates']):
                events.append((mode,payload))
            return events
        events=asyncio.run(run())
        custom=[v for k,v in events if k=='custom']
        self.assertEqual([x['type'] for x in custom],['status','sources','status','content','content'])
        self.assertNotIn('excerpt',custom[1]['sources'][0])
        final=next(v['generate_answer'] for k,v in events if k=='updates' and 'generate_answer' in v)
        self.assertEqual(final,{'answer':'根据新闻 [1]','tokens':9})

    def test_failed_save_rolls_back_assistant_and_query(self):
        sid, _, model=prepare_turn(11,0,'新能源')
        with self.connection() as c:
            c.execute("CREATE TRIGGER reject_query BEFORE INSERT ON user_queries BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            persist_answer(11,sid,'新能源','回答',9,model['id'],[])
        with self.connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM chat_messages WHERE role='assistant'").fetchone()[0],0)
            self.assertEqual(c.execute('SELECT total_tokens FROM ai_models').fetchone()[0],0)


if __name__=='__main__': unittest.main()
