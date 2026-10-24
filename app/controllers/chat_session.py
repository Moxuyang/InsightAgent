"""会话管理 - 控制器层"""
import tornado.web
from app.controllers.base import BaseHandler
from app.models.chat_session import ChatSessionRepository
from app.models.db import get_connection


class ChatSessionPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("chat_session/list.html", title="会话管理")


class ChatSessionApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "list")
        if action == "messages":
            session_id = int(self.get_argument("session_id", 0))
            if not session_id:
                self.write({"code": 1, "msg": "session_id 必填"})
                return
            messages = ChatSessionRepository.get_messages(session_id)
            self.write({"code": 0, "data": messages})
            return

        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        keyword = self.get_argument("keyword", "").strip()

        if keyword:
            rows, total = self._search_sessions(page, limit, keyword)
        else:
            rows, total = ChatSessionRepository.get_list(page, limit)

        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "delete":
            session_id = int(self.get_argument("id", 0))
            if not session_id:
                return self.write({"code": 1, "msg": "参数错误"})
            ChatSessionRepository.delete(session_id)
            self.write({"code": 0, "msg": "删除成功"})
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if ChatSessionRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})
        else:
            self.write({"code": 1, "msg": "未知操作"})

    def _search_sessions(self, page, limit, keyword):
        offset = (page - 1) * limit
        like_kw = f"%{keyword}%"
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT cs.*, u.username,
                   (SELECT COUNT(1) FROM chat_messages WHERE session_id=cs.id) as msg_count
                   FROM chat_sessions cs
                   LEFT JOIN users u ON cs.user_id = u.id
                   WHERE u.username LIKE ? OR cs.title LIKE ?
                   ORDER BY cs.update_at DESC LIMIT ? OFFSET ?""",
                (like_kw, like_kw, limit, offset)
            ).fetchall()
            total = conn.execute(
                """SELECT COUNT(1) as cnt FROM chat_sessions cs
                   LEFT JOIN users u ON cs.user_id = u.id
                   WHERE u.username LIKE ? OR cs.title LIKE ?""",
                (like_kw, like_kw)
            ).fetchone()["cnt"]
        return [dict(r) for r in rows], total
