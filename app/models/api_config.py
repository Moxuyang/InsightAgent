from app.models.db import get_connection

class ApiConfigRepository:
    @staticmethod
    def get_list(page=1, limit=20):
        offset = (page - 1) * limit
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM api_configs ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
            total = conn.execute("SELECT COUNT(1) as cnt FROM api_configs").fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def get_all():
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM api_configs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def create(name, api_url, method="GET", headers="", params="", is_active=1):
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO api_configs (name, api_url, method, headers, params, is_active) VALUES (?,?,?,?,?,?)",
                (name, api_url, method, headers, params, is_active)
            )
            return c.lastrowid

    @staticmethod
    def update(cfg_id, name, api_url, method, headers, params, is_active):
        with get_connection() as conn:
            conn.execute(
                "UPDATE api_configs SET name=?, api_url=?, method=?, headers=?, params=?, is_active=? WHERE id=?",
                (name, api_url, method, headers, params, is_active, cfg_id)
            )
        return True

    @staticmethod
    def delete(cfg_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM api_configs WHERE id=?", (cfg_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM api_configs WHERE id IN ({ph})", ids)
        return True
