"""Smoke-test page rendering against a temporary SQLite database copy."""
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import closing
import gc

import tornado.testing
import tornado.web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.models import db
from app.models.user import UserRepository
from app.models.collaboration import CollabGroupRepository
from app.models.chat_session import ChatSessionRepository


class FrontendPagesTest(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        self._temporary = tempfile.TemporaryDirectory(prefix='insight-ui-test-')
        self._old_path = db.DB_PATH
        self._old_config = db._get_db_config
        db.DB_PATH = str(Path(self._temporary.name) / 'test.db')
        with closing(sqlite3.connect(ROOT / 'database' / 'app.db')) as source:
            with closing(sqlite3.connect(db.DB_PATH)) as target:
                source.backup(target)
        db._get_db_config = lambda: {'db_type': 'sqlite'}
        db.init_db()
        UserRepository.create_user('frontend_smoke_test', 'local-fixture-only')
        user = UserRepository.get_user_by_username('frontend_smoke_test')
        self.group_id = CollabGroupRepository.create('UI test', user['id'])
        self.session_id = ChatSessionRepository.create(user['id'], 'UI test')
        spec = importlib.util.spec_from_file_location('frontend_entry', ROOT / 'app.py')
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with patch('tornado.autoreload.start'):
            app = entry.make_app()
        app.settings.update(debug=False, autoreload=False, compiled_template_cache=False)
        self.cookie = 'username=' + tornado.web.create_signed_value(
            app.settings['cookie_secret'], 'username', user['username']
        ).decode('ascii')
        return app

    def tearDown(self):
        super().tearDown()
        db.DB_PATH = self._old_path
        db._get_db_config = self._old_config
        gc.collect()
        self._temporary.cleanup()

    def test_all_page_routes_render(self):
        routes = [
            '/', '/dashboard', '/auth/login', '/register', '/user/list',
            '/menu/list', '/role/list', '/model_engine/list', '/spy_source/list',
            '/data_warehouse/list', '/spy', '/permission/list', '/deep_collect/list',
            '/api_config/list', '/digital_employee/list', '/skill/list',
            '/user_query/list', '/system_config/list', '/user_file/list',
            '/data_screen', '/user_dashboard', '/collaboration/list',
            f'/collaboration/chat?group_id={self.group_id}', '/sentiment',
            '/chat_session/list', '/data_analysis',
            '/api/export/pdf?type=queries&ids=0',
            f'/api/export/pdf?type=session&session_id={self.session_id}',
        ]
        for route in routes:
            with self.subTest(route=route):
                response = self.fetch(route, headers={'Cookie': self.cookie})
                self.assertEqual(response.code, 200)
                self.assertIn(b'<html', response.body.lower())
                self.assertNotIn(b'Traceback', response.body)

    def test_collaboration_plain_message_and_invitation(self):
        from urllib.parse import urlencode
        from app.models.collaboration import CollabMemberRepository
        from app.models.digital_employee import DigitalEmployeeRepository
        self._app.settings['xsrf_cookies'] = False
        employee_id = DigitalEmployeeRepository.create('Invitation fixture', 'Test role', None, '', 1)
        headers = {'Cookie': self.cookie, 'Content-Type': 'application/x-www-form-urlencoded'}
        invited = self.fetch('/api/collaboration', method='POST', headers=headers,
                             body=urlencode({'action': 'invite_batch', 'group_id': self.group_id,
                                             'employee_ids': str(employee_id)}))
        import json
        self.assertEqual(json.loads(invited.body)['code'], 0)
        members = CollabMemberRepository.get_members(self.group_id)
        self.assertTrue(any(m['member_type'] == 'employee' and m['member_id'] == employee_id for m in members))
        sent = self.fetch('/api/collaboration/chat', method='POST', headers=headers,
                          body=urlencode({'action': 'send', 'group_id': self.group_id,
                                          'content': 'Plain team discussion without an AI mention'}))
        self.assertEqual(sent.code, 200)
        self.assertEqual(json.loads(sent.body)['code'], 0)
        messages = self.fetch('/api/collaboration/chat?action=messages&group_id=' + str(self.group_id), headers=headers)
        self.assertEqual(json.loads(messages.body)['data'][-1]['content'], 'Plain team discussion without an AI mention')

    def test_employee_multiple_skills_survive_save(self):
        from urllib.parse import urlencode
        from app.models.skill import SkillRepository
        import json
        self._app.settings['xsrf_cookies'] = False
        first = SkillRepository.create('First fixture')
        second = SkillRepository.create('Second fixture')
        headers = {'Cookie': self.cookie, 'Content-Type': 'application/x-www-form-urlencoded'}
        created = self.fetch('/api/digital_employee', method='POST', headers=headers,
                             body=urlencode({'action': 'add', 'name': 'Multi skill fixture',
                                             'skill_ids': str(first) + ',' + str(second)}))
        self.assertEqual(json.loads(created.body)['code'], 0)
        listed = self.fetch('/api/digital_employee?limit=100', headers=headers)
        employee = next(e for e in json.loads(listed.body)['data'] if e['name'] == 'Multi skill fixture')
        self.assertEqual(set(employee['skill_ids'].split(',')), {str(first), str(second)})

    def test_group_history_and_agent_invocations_require_membership(self):
        from urllib.parse import urlencode
        from app.models.digital_employee import DigitalEmployeeRepository
        import json
        UserRepository.create_user('other_group_owner','fixture-only')
        other=UserRepository.get_user_by_username('other_group_owner')
        group=CollabGroupRepository.create('Other private group',other['id'])
        headers={'Cookie':self.cookie,'Content-Type':'application/x-www-form-urlencoded'}
        self._app.settings['xsrf_cookies']=False
        read=self.fetch('/api/collaboration/chat?action=messages&group_id='+str(group),headers=headers)
        self.assertEqual(read.code,403)
        denied=self.fetch('/api/collaboration/chat',method='POST',headers=headers,body=urlencode({'action':'send','group_id':group,'content':'not allowed'}))
        self.assertEqual(denied.code,403)

    def test_employee_uses_graph_and_saves_sources_and_tokens(self):
        from urllib.parse import urlencode
        from app.models.digital_employee import DigitalEmployeeRepository
        from app.models.collaboration import CollabMemberRepository
        import json
        with db.get_connection() as conn:
            model=conn.execute("INSERT INTO ai_models(name,model_name,api_key,base_url) VALUES (?,?,?,?)",('Graph fixture','fixture','fixture-only','https://example.invalid')).lastrowid
        employee=DigitalEmployeeRepository.create('Graph fixture employee','新闻分析',model,'',1)
        CollabMemberRepository.add_member(self.group_id,'employee',employee)
        captured=[]
        class FakeGraph:
            async def astream(self,state,stream_mode):
                captured.append(state)
                yield 'custom',{'type':'status','stage':'retrieve','message':'正在检索'}
                yield 'custom',{'type':'sources','sources':[{'number':1,'title':'fixture news','url':'https://example.com/news','source_name':'fixture','content_kind':'正文'}]}
                yield 'custom',{'type':'content','content':'新闻回答 [1]'}
                yield 'updates',{'generate_answer':{'answer':'新闻回答 [1]','tokens':11}}
        self._app.settings['xsrf_cookies']=False
        headers={'Cookie':self.cookie,'Content-Type':'application/x-www-form-urlencoded'}
        with patch('app.controllers.collaboration.build_news_graph',return_value=FakeGraph()):
            response=self.fetch('/api/collaboration/chat',method='POST',headers=headers,body=urlencode({'action':'send','group_id':self.group_id,'mentioned_id':employee,'content':'今天采集的新闻'}))
        self.assertEqual(response.code,200)
        self.assertIn('text/event-stream',response.headers['Content-Type'])
        self.assertNotIn('user_id',captured[0])
        self.assertEqual(captured[0]['persona']['name'],'Graph fixture employee')
        with db.get_connection() as conn:
            message=conn.execute("SELECT content,tokens_used FROM collab_messages WHERE group_id=? AND sender_type='employee' ORDER BY id DESC LIMIT 1",(self.group_id,)).fetchone()
            self.assertIn('https://example.com/news',message['content'])
            self.assertEqual(message['tokens_used'],11)
        employee=DigitalEmployeeRepository.create('Outside employee','Fixture',None,'',1)
        denied=self.fetch('/api/collaboration/chat',method='POST',headers=headers,body=urlencode({'action':'send','group_id':self.group_id,'mentioned_id':employee,'content':'@Outside employee 新闻'}))
        self.assertEqual(denied.code,403)

    def test_directory_search_and_session_message_counts(self):
        from app.models.skill import SkillRepository
        from app.models.digital_employee import DigitalEmployeeRepository
        import json
        skill_id = SkillRepository.create('Unique directory fixture', 'skill.md')
        DigitalEmployeeRepository.create('Search employee', 'Fixture role', None, str(skill_id), 1)
        headers = {'Cookie': self.cookie}
        skills = self.fetch('/api/skill?keyword=Unique%20directory&skill_type=skill.md', headers=headers)
        result = json.loads(skills.body)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['data'][0]['id'], skill_id)
        employees = self.fetch('/api/digital_employee?keyword=Unique%20directory', headers=headers)
        self.assertEqual(json.loads(employees.body)['data'][0]['name'], 'Search employee')
        ChatSessionRepository.add_message(self.session_id, 'user', 'Archive fixture')
        sessions = self.fetch('/api/chat_session?limit=100', headers=headers)
        session = next(s for s in json.loads(sessions.body)['data'] if s['id'] == self.session_id)
        self.assertEqual(session['msg_count'], 1)

    def test_source_and_article_library_filters(self):
        from app.models.spy_source import SpySourceRepository
        from app.models.data_warehouse import DataWarehouseRepository
        import json
        SpySourceRepository.create_source('Unique connector fixture', 'https://example.invalid/search?q={关键字}', '', 1)
        source = SpySourceRepository.get_sources_list(1, 10, 'Unique connector fixture', '1')[0][0]
        DataWarehouseRepository.insert_data(source['id'], 'library fixture topic', 'Unique article fixture',
                                            'https://example.invalid/article', 'A searchable summary fixture')
        headers = {'Cookie': self.cookie}
        sources = json.loads(self.fetch('/api/spy_source?keyword=Unique%20connector&is_active=1', headers=headers).body)
        self.assertEqual(sources['count'], 1)
        disabled = json.loads(self.fetch('/api/spy_source?keyword=Unique%20connector&is_active=0', headers=headers).body)
        self.assertEqual(disabled['count'], 0)
        articles = json.loads(self.fetch('/api/data_warehouse?keyword=searchable%20summary&source_id=' + str(source['id']), headers=headers).body)
        self.assertEqual(articles['count'], 1)
        self.assertEqual(articles['data'][0]['title'], 'Unique article fixture')
        # The deep-collection caller continues to work with its original signature.
        self.assertGreaterEqual(DataWarehouseRepository.get_data_list(1, 20)[1], 1)

    def test_deep_collection_search_filters_before_pagination(self):
        import json
        from app.models.spy_source import SpySourceRepository
        from app.models.data_warehouse import DataWarehouseRepository
        from app.models.deep_collect import DeepCollectRepository
        headers = {'Cookie': self.cookie}
        SpySourceRepository.create_source('Deep collection source fixture', 'https://example.invalid', '', 1)
        source = SpySourceRepository.get_sources_list(1, 10, 'Deep collection source fixture', '1')[0][0]
        for title, summary in [('Older article', 'DeepSearchFixture'), ('Newer article', 'DeepSearchFixture'), ('Unrelated newest', 'Other summary')]:
            DataWarehouseRepository.insert_data(source['id'], 'test', title, 'https://example.invalid/' + title.replace(' ', '-'), summary)
        query = '/api/deep_collect/data?keyword=DeepSearchFixture&source_id=' + str(source['id']) + '&limit=1&page='
        first = json.loads(self.fetch(query + '1', headers=headers).body)
        second = json.loads(self.fetch(query + '2', headers=headers).body)
        self.assertEqual(first['count'], 2)
        self.assertEqual(second['count'], 2)
        self.assertEqual(first['data'][0]['title'], 'Newer article')
        self.assertEqual(second['data'][0]['title'], 'Older article')
        DeepCollectRepository.create('DeepTaskFixture', 'https://example.invalid/target')
        DeepCollectRepository.create('Unrelated task', 'https://example.invalid/other')
        tasks = json.loads(self.fetch('/api/deep_collect?keyword=DeepTaskFixture&limit=1', headers=headers).body)
        self.assertEqual(tasks['count'], 1)
        self.assertEqual(tasks['data'][0]['name'], 'DeepTaskFixture')

    def test_shared_assets_are_served(self):
        for path in ['/static/css/components.css', '/static/css/forms.css', '/static/css/deep-collect.css', '/static/js/deep-collect.js', '/static/js/globe.js', '/static/images/earth-map.jpg', '/static/dist/echarts/echarts.min.js', '/static/dist/echarts-gl/echarts-gl.min.js', '/static/dist/echarts/echarts-wordcloud.min.js', '/static/js/base.js', '/static/css/product.css', '/static/js/messenger.js', '/static/js/session-library.js', '/static/js/navigation.js', '/static/js/article-library.js']:
            with self.subTest(path=path):
                response = self.fetch(path)
                self.assertEqual(response.code, 200)
                self.assertGreater(len(response.body), 100)


if __name__ == '__main__':
    unittest.main()
