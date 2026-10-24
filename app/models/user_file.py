from app.models.db import get_connection

class UserFileRepository:
    @staticmethod
    def get_list(page=1, limit=20, user_id=None):
        offset = (page - 1) * limit
        with get_connection() as conn:
            if user_id:
                rows = conn.execute("""
                    SELECT uf.*, u.username
                    FROM user_files uf
                    LEFT JOIN users u ON uf.user_id = u.id
                    WHERE uf.user_id = ?
                    ORDER BY uf.id DESC LIMIT ? OFFSET ?
                """, (user_id, limit, offset)).fetchall()
                total = conn.execute(
                    "SELECT COUNT(1) as cnt FROM user_files WHERE user_id=?", (user_id,)
                ).fetchone()["cnt"]
            else:
                rows = conn.execute("""
                    SELECT uf.*, u.username
                    FROM user_files uf
                    LEFT JOIN users u ON uf.user_id = u.id
                    ORDER BY uf.id DESC LIMIT ? OFFSET ?
                """, (limit, offset)).fetchall()
                total = conn.execute("SELECT COUNT(1) as cnt FROM user_files").fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def create(user_id, file_name, file_path, file_type="", file_size=0):
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO user_files (user_id, file_name, file_path, file_type, file_size) VALUES (?,?,?,?,?)",
                (user_id, file_name, file_path, file_type, file_size)
            )
            return c.lastrowid

    @staticmethod
    def delete(file_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM user_files WHERE id=?", (file_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM user_files WHERE id IN ({ph})", ids)
        return True
