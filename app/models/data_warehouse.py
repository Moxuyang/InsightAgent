from app.models.db import get_connection, compact_sequence

class DataWarehouseRepository:
    
    @staticmethod
    def get_data_list(page: int, limit: int, keyword='', source_id=None):
        offset = (page - 1) * limit
        clauses, params = [], []
        if keyword:
            clauses.append('(d.title LIKE ? OR d.summary LIKE ? OR d.keyword LIKE ?)')
            params.extend(['%' + keyword + '%'] * 3)
        if source_id:
            clauses.append('d.source_id=?')
            params.append(source_id)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with get_connection() as conn:
            rows = conn.execute('SELECT d.*, s.name as source_name FROM spy_data d '
                                'LEFT JOIN spy_sources s ON d.source_id=s.id' + where +
                                ' ORDER BY d.id DESC LIMIT ? OFFSET ?', params + [limit, offset]).fetchall()
            total = conn.execute('SELECT COUNT(1) as cnt FROM spy_data d' + where, params).fetchone()['cnt']
        return [dict(row) for row in rows], total

    @staticmethod
    def insert_data(source_id: int, keyword: str, title: str, url: str, summary: str):
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO spy_data (source_id, keyword, title, url, summary) VALUES (?, ?, ?, ?, ?)",
                    (source_id, keyword, title, url, summary)
                )
            return True
        except Exception:
            return False

    @staticmethod
    def upsert_batch(items: list) -> dict:
        if not items:
            return {"total": 0, "inserted": 0, "updated": 0}

        normalized = {}
        for it in items:
            try:
                source_id = int(it.get("source_id", 0))
            except Exception:
                source_id = 0
            url = (it.get("url") or "").strip()
            title = (it.get("title") or "").strip()
            keyword = (it.get("keyword") or "").strip()
            summary = (it.get("summary") or "").strip()
            if not source_id or not url or not title:
                continue
            if len(summary) > 500:
                summary = summary[:500]
            normalized[(source_id, url)] = {
                "source_id": source_id,
                "keyword": keyword,
                "title": title,
                "url": url,
                "summary": summary,
            }

        keys = list(normalized.keys())
        if not keys:
            return {"total": 0, "inserted": 0, "updated": 0}

        existing = set()
        with get_connection() as conn:
            for i in range(0, len(keys), 100):
                chunk = keys[i:i + 100]
                where = " OR ".join(["(source_id=? AND url=?)"] * len(chunk))
                params = []
                for sid, u in chunk:
                    params.extend([sid, u])
                rows = conn.execute(f"SELECT source_id, url FROM spy_data WHERE {where}", params).fetchall()
                for r in rows:
                    existing.add((r["source_id"], r["url"]))

            payload = []
            for (sid, u) in keys:
                item = normalized[(sid, u)]
                payload.append((item["source_id"], item["keyword"], item["title"], item["url"], item["summary"]))

            conn.executemany(
                """
                INSERT INTO spy_data (source_id, keyword, title, url, summary, update_at)
                VALUES (?, ?, ?, ?, ?, current_timestamp)
                ON CONFLICT(source_id, url) DO UPDATE SET
                    keyword=excluded.keyword,
                    title=excluded.title,
                    summary=excluded.summary,
                    update_at=current_timestamp
                """,
                payload
            )

        updated = len(existing.intersection(keys))
        total = len(keys)
        inserted = total - updated
        return {"total": total, "inserted": inserted, "updated": updated}

    @staticmethod
    def delete_data(data_id: int) -> bool:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM spy_data WHERE id=?", (data_id,))
            # 单条删除后检查是否表已空，压缩序号
            remaining = conn.execute("SELECT COUNT(*) as cnt FROM spy_data").fetchone()
            if remaining and remaining['cnt'] == 0:
                compact_sequence('spy_data')
            return True
        except Exception:
            return False

    @staticmethod
    def delete_batch(ids: list) -> bool:
        if not ids: return False
        placeholders = ",".join("?" * len(ids))
        try:
            with get_connection() as conn:
                conn.execute(f"DELETE FROM spy_data WHERE id IN ({placeholders})", ids)
            # 批量删除后压缩自增序号
            compact_sequence('spy_data')
            return True
        except Exception:
            return False
