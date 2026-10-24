from app.models.db import get_connection

class ChatSessionRepository:
    @staticmethod
    def get_list(page=1, limit=20, user_id=None):
        offset = (page - 1) * limit
        with get_connection() as conn:
            if user_id:
                rows = conn.execute("""
                    SELECT cs.*, u.username,
                        (SELECT COUNT(1) FROM chat_messages WHERE session_id=cs.id) AS msg_count
                    FROM chat_sessions cs
                    LEFT JOIN users u ON cs.user_id = u.id
                    WHERE cs.user_id = ?
                    ORDER BY cs.update_at DESC LIMIT ? OFFSET ?
                """, (user_id, limit, offset)).fetchall()
                total = conn.execute(
                    "SELECT COUNT(1) as cnt FROM chat_sessions WHERE user_id=?", (user_id,)
                ).fetchone()["cnt"]
            else:
                rows = conn.execute("""
                    SELECT cs.*, u.username,
                        (SELECT COUNT(1) FROM chat_messages WHERE session_id=cs.id) AS msg_count
                    FROM chat_sessions cs
                    LEFT JOIN users u ON cs.user_id = u.id
                    ORDER BY cs.update_at DESC LIMIT ? OFFSET ?
                """, (limit, offset)).fetchall()
                total = conn.execute("SELECT COUNT(1) as cnt FROM chat_sessions").fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def create(user_id, title="新对话", employee_id=None):
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO chat_sessions (user_id, title, employee_id) VALUES (?,?,?)",
                (user_id, title, employee_id)
            )
            return c.lastrowid

    @staticmethod
    def update(session_id, title=None, is_active=None):
        with get_connection() as conn:
            if title is not None:
                conn.execute(
                    "UPDATE chat_sessions SET title=?, update_at=datetime('now') WHERE id=?",
                    (title, session_id)
                )
            if is_active is not None:
                conn.execute("UPDATE chat_sessions SET is_active=? WHERE id=?", (is_active, session_id))
        return True

    @staticmethod
    def delete(session_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM chat_messages WHERE session_id IN ({ph})", ids)
            conn.execute(f"DELETE FROM chat_sessions WHERE id IN ({ph})", ids)
        return True

    @staticmethod
    def get_messages(session_id):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id ASC",
                (session_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def add_message(session_id, role, content, tokens_used=0):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, tokens_used) VALUES (?,?,?,?)",
                (session_id, role, content, tokens_used)
            )
            conn.execute("UPDATE chat_sessions SET update_at=datetime('now') WHERE id=?", (session_id,))
        return True
