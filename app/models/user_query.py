from app.models.db import get_connection

class UserQueryRepository:
    @staticmethod
    def get_list(page=1, limit=20, user_id=None):
        offset = (page - 1) * limit
        with get_connection() as conn:
            if user_id:
                rows = conn.execute("""
                    SELECT uq.*, u.username
                    FROM user_queries uq
                    LEFT JOIN users u ON uq.user_id = u.id
                    WHERE uq.user_id = ?
                    ORDER BY uq.id DESC LIMIT ? OFFSET ?
                """, (user_id, limit, offset)).fetchall()
                total = conn.execute(
                    "SELECT COUNT(1) as cnt FROM user_queries WHERE user_id=?", (user_id,)
                ).fetchone()["cnt"]
            else:
                rows = conn.execute("""
                    SELECT uq.*, u.username
                    FROM user_queries uq
                    LEFT JOIN users u ON uq.user_id = u.id
                    ORDER BY uq.id DESC LIMIT ? OFFSET ?
                """, (limit, offset)).fetchall()
                total = conn.execute("SELECT COUNT(1) as cnt FROM user_queries").fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def create(user_id, query_text, response_text="", tokens_used=0):
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO user_queries (user_id, query_text, response_text, tokens_used) VALUES (?,?,?,?)",
                (user_id, query_text, response_text, tokens_used)
            )
            return c.lastrowid

    @staticmethod
    def delete(query_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM user_queries WHERE id=?", (query_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM user_queries WHERE id IN ({ph})", ids)
        return True
