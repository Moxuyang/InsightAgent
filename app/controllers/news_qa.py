"""Authenticated LangGraph streaming endpoint; conversation persistence is server-owned."""
import asyncio
import json
import logging
from contextlib import contextmanager
import tornado.web
from tornado.iostream import StreamClosedError
from app.controllers.base import BaseHandler
from app.models.db import get_connection
from app.services.news_qa import build_news_graph,append_source_refs


@contextmanager
def transaction():
    with get_connection() as conn:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise


def prepare_turn(user_id, session_id, question):
    with transaction() as conn:
        if session_id:
            session = conn.execute('SELECT id FROM chat_sessions WHERE id=? AND user_id=? AND is_active=1',(session_id,user_id)).fetchone()
            if not session:
                raise PermissionError('会话不存在或无权访问')
        model = conn.execute('SELECT id,api_key,base_url,model_name FROM ai_models WHERE is_default=1 ORDER BY id LIMIT 1').fetchone()
        if not model or not model['api_key'] or not model['model_name'] or not model['base_url']:
            raise ValueError('请先配置可用的默认模型')
        if not session_id:
            cursor = conn.execute('INSERT INTO chat_sessions (user_id,title) VALUES (?,?)',(user_id,question[:30]))
            session_id = cursor.lastrowid
        history = conn.execute('SELECT role,content FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT 8',(session_id,)).fetchall()
        conn.execute('INSERT INTO chat_messages (session_id,role,content) VALUES (?,?,?)',(session_id,'user',question))
    return session_id, [dict(row) for row in reversed(history)], dict(model)


def persist_answer(user_id, session_id, question, answer, tokens, model_id, sources):
    answer=append_source_refs(answer,sources)
    with transaction() as conn:
        # A session deleted during generation must never get orphan messages.
        if not conn.execute('SELECT id FROM chat_sessions WHERE id=? AND user_id=?',(session_id,user_id)).fetchone():
            raise PermissionError('会话已删除，回答未保存')
        conn.execute('INSERT INTO chat_messages (session_id,role,content,tokens_used) VALUES (?,?,?,?)',(session_id,'assistant',answer,tokens))
        conn.execute('INSERT INTO user_queries (user_id,query_text,response_text,tokens_used) VALUES (?,?,?,?)',(user_id,question,answer,tokens))
        conn.execute("UPDATE chat_sessions SET update_at=datetime('now') WHERE id=?",(session_id,))
        conn.execute('UPDATE ai_models SET total_tokens=total_tokens+? WHERE id=?',(tokens,model_id))


class NewsQaHandler(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        question = self.get_argument('message','').strip()
        try:
            session_id = int(self.get_argument('session_id','0'))
            if not question or len(question)>4000 or session_id<0:
                raise ValueError('请输入 1–4000 字的问题')
            # Fail before saving the turn when the graph dependency is missing.
            import langgraph.graph  # noqa: F401
            from app.services.file_context import load_attachments, bind_attachments
            selected=json.loads(self.get_argument('file_ids','[]'))
            if not isinstance(selected,list):raise ValueError('附件参数格式不正确')
            attachments=await asyncio.to_thread(load_attachments,self.current_user['id'],session_id,selected)
            session_id, history, model = await asyncio.to_thread(prepare_turn,self.current_user['id'],session_id,question)
            if attachments:
                await asyncio.to_thread(bind_attachments,session_id,attachments)
        except (ValueError,PermissionError) as exc:
            self.set_status(403 if isinstance(exc,PermissionError) else 400)
            self.write({'error':str(exc)})
            return
        except ImportError:
            self.set_status(503)
            self.write({'error':'请安装项目依赖后重启服务，当前缺少 LangGraph。'})
            return
        except Exception:
            logging.exception('Unable to prepare news QA')
            self.set_status(503)
            self.write({'error':'暂时无法读取问答配置或会话，请稍后重试。'})
            return

        self.set_header('Content-Type','text/event-stream; charset=utf-8')
        self.set_header('Cache-Control','no-cache')
        self.set_header('X-Accel-Buffering','no')
        async def emit(event):
            self.write('data: '+json.dumps(event,ensure_ascii=False)+'\n\n')
            await self.flush()
        try:
            await emit({'type':'session','session_id':session_id})
            graph = build_news_graph(model)
            final = None
            sources = []
            async with asyncio.timeout(150):
                async for mode, payload in graph.astream({'question':question,'history':history,'user_id':self.current_user['id'],'attachments':attachments},stream_mode=['custom','updates']):
                    if mode=='custom':
                        if payload.get('type')=='sources':
                            sources=payload['sources']
                        await emit(payload)
                    elif mode=='updates' and 'generate_answer' in payload:
                        final = payload['generate_answer']
            if not final:
                raise RuntimeError('问答流程未完成')
            await asyncio.to_thread(persist_answer,self.current_user['id'],session_id,question,final['answer'],final['tokens'],model['id'],sources)
            await emit({'type':'done','tokens':final['tokens'],'saved':True})
            self.write('data: [DONE]\n\n')
            await self.flush()
        except StreamClosedError:
            return
        except Exception:
            logging.exception('News QA failed for session %s',session_id)
            await emit({'type':'error','error':'本次问答未完成，请稍后重试或检查模型连接。未完成的回答不会保存。'})
