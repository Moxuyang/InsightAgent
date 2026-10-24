"""PDF导出控制器"""
import tornado.web
from app.controllers.base import BaseHandler
from app.models.chat_session import ChatSessionRepository
from app.models.db import get_connection


class ExportPdfHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        export_type = self.get_argument("type", "session")
        user = self.current_user
        user_id = user['id'] if user else 0

        if export_type == "session":
            session_id = int(self.get_argument("session_id", 0))
            if not session_id:
                self.write("<h3 style='color:red;padding:40px;text-align:center;'>缺少 session_id 参数</h3>")
                return

            with get_connection() as conn:
                session = conn.execute(
                    "SELECT * FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user_id)
                ).fetchone()

            if not session:
                self.write("<h3 style='color:red;padding:40px;text-align:center;'>会话不存在或无权访问</h3>")
                return

            session_dict = dict(session)
            messages = ChatSessionRepository.get_messages(session_id)
            username = user.get("username", "未知用户") if user else "未知用户"

            self.render("export_pdf.html", title=session_dict.get("title", "对话记录"),
                        username=username, export_type="session",
                        session=session_dict, messages=messages)

        elif export_type == "queries":
            ids_str = self.get_argument("ids", "")
            if not ids_str:
                self.write("<h3 style='color:red;padding:40px;text-align:center;'>请选择要导出的记录</h3>")
                return

            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if not ids:
                self.write("<h3 style='color:red;padding:40px;text-align:center;'>无效的记录ID</h3>")
                return

            with get_connection() as conn:
                ph = ",".join("?" * len(ids))
                rows = conn.execute(
                    f"SELECT uq.*, u.username FROM user_queries uq "
                    f"LEFT JOIN users u ON uq.user_id = u.id "
                    f"WHERE uq.id IN ({ph}) ORDER BY uq.id ASC",
                    ids
                ).fetchall()

            queries = [dict(r) for r in rows]
            username = user.get("username", "未知用户") if user else "未知用户"

            self.render("export_pdf.html", title="对话记录导出",
                        username=username, export_type="queries",
                        queries=queries)

        else:
            self.write("<h3 style='color:red;padding:40px;text-align:center;'>不支持的导出类型</h3>")
