from app.models.db import get_connection

class DeepCollectResultRepository:
    @staticmethod
    def get_list(page=1, limit=20, keyword=""):
        offset = (page - 1) * limit
        with get_connection() as conn:
            if keyword:
                kw = f"%{keyword}%"
                rows = conn.execute(
                    """SELECT r.*, d.keyword as spy_keyword, s.name as source_name
                       FROM deep_collect_results r
                       LEFT JOIN spy_data d ON r.spy_data_id = d.id
                       LEFT JOIN spy_sources s ON d.source_id = s.id
                       WHERE r.title LIKE ? OR d.keyword LIKE ?
                       ORDER BY r.id DESC LIMIT ? OFFSET ?""",
                    (kw, kw, limit, offset)
                ).fetchall()
                total = conn.execute(
                    "SELECT COUNT(1) as cnt FROM deep_collect_results r LEFT JOIN spy_data d ON r.spy_data_id = d.id WHERE r.title LIKE ? OR d.keyword LIKE ?",
                    (kw, kw)
                ).fetchone()["cnt"]
            else:
                rows = conn.execute(
                    """SELECT r.*, d.keyword as spy_keyword, s.name as source_name
                       FROM deep_collect_results r
                       LEFT JOIN spy_data d ON r.spy_data_id = d.id
                       LEFT JOIN spy_sources s ON d.source_id = s.id
                       ORDER BY r.id DESC LIMIT ? OFFSET ?""",
                    (limit, offset)
                ).fetchall()
                total = conn.execute("SELECT COUNT(1) as cnt FROM deep_collect_results").fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def get_by_id(result_id):
        with get_connection() as conn:
            row = conn.execute(
                """SELECT r.*, d.keyword as spy_keyword, d.summary as spy_summary,
                          d.url as spy_url, s.name as source_name
                   FROM deep_collect_results r
                   LEFT JOIN spy_data d ON r.spy_data_id = d.id
                   LEFT JOIN spy_sources s ON d.source_id = s.id
                   WHERE r.id = ?""",
                (result_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_spy_data_id(spy_data_id):
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM deep_collect_results WHERE spy_data_id=? ORDER BY id DESC LIMIT 1",
                (spy_data_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def create(spy_data_id, title, url, task_id=None):
        with get_connection() as conn:
            # 先检查是否已有采集记录
            existing = conn.execute(
                "SELECT id FROM deep_collect_results WHERE spy_data_id=? AND crawl_status='success'",
                (spy_data_id,)
            ).fetchone()
            if existing:
                return None  # 已成功采集过

            c = conn.execute(
                """INSERT INTO deep_collect_results
                   (spy_data_id, task_id, title, url, crawl_status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                (spy_data_id, task_id, title, url)
            )
            return c.lastrowid

    @staticmethod
    def update_result(result_id, full_content, content_html, images_json, crawl_status, error_msg=None):
        with get_connection() as conn:
            conn.execute(
                """UPDATE deep_collect_results
                   SET full_content=?, content_html=?, images_json=?,
                       crawl_status=?, error_msg=?, crawl_at=datetime('now')
                   WHERE id=?""",
                (full_content, content_html, images_json, crawl_status, error_msg, result_id)
            )
        return True

    @staticmethod
    def delete(result_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM deep_collect_results WHERE id=?", (result_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM deep_collect_results WHERE id IN ({ph})", ids)
        return True
