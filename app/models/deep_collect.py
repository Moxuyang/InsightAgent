from app.models.db import get_connection

class DeepCollectRepository:
    @staticmethod
    def get_list(page=1, limit=20, keyword=""):
        offset = (page - 1) * limit
        where = " WHERE name LIKE ? OR target_url LIKE ?" if keyword else ""
        params = [f"%{keyword}%"] * 2 if keyword else []
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM deep_collects" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [limit, offset]
            ).fetchall()
            total = conn.execute("SELECT COUNT(1) as cnt FROM deep_collects" + where, params).fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def get_all():
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM deep_collects ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def create(name, target_url, collect_type="webpage", cron_expression="", is_active=1):
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO deep_collects (name, target_url, collect_type, cron_expression, is_active) VALUES (?,?,?,?,?)",
                (name, target_url, collect_type, cron_expression, is_active)
            )
            return c.lastrowid

    @staticmethod
    def update(collect_id, name, target_url, collect_type, cron_expression, is_active):
        with get_connection() as conn:
            conn.execute(
                "UPDATE deep_collects SET name=?, target_url=?, collect_type=?, cron_expression=?, is_active=? WHERE id=?",
                (name, target_url, collect_type, cron_expression, is_active, collect_id)
            )
        return True

    @staticmethod
    def delete(collect_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM deep_collects WHERE id=?", (collect_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM deep_collects WHERE id IN ({ph})", ids)
        return True
