from app.models.db import get_connection

class SystemConfigRepository:
    @staticmethod
    def get_list(page=1, limit=20):
        offset = (page - 1) * limit
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM system_configs ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
            total = conn.execute("SELECT COUNT(1) as cnt FROM system_configs").fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def get_by_key(key):
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM system_configs WHERE config_key=?", (key,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def set_config(key, value, description=""):
        with get_connection() as conn:
            existing = conn.execute("SELECT id FROM system_configs WHERE config_key=?", (key,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE system_configs SET config_value=?, description=?, update_at=datetime('now') WHERE config_key=?",
                    (value, description, key)
                )
            else:
                conn.execute(
                    "INSERT INTO system_configs (config_key, config_value, description) VALUES (?,?,?)",
                    (key, value, description)
                )
        return True

    @staticmethod
    def delete(cfg_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM system_configs WHERE id=?", (cfg_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM system_configs WHERE id IN ({ph})", ids)
        return True
