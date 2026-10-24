from app.models.db import get_connection

class SpySourceRepository:
    
    @staticmethod
    def get_sources_list(page: int, limit: int, keyword='', is_active=''):
        offset = (page - 1) * limit
        clauses, params = [], []
        if keyword:
            clauses.append('(name LIKE ? OR entry_url LIKE ?)')
            params.extend(['%' + keyword + '%'] * 2)
        if str(is_active) in ('0', '1'):
            clauses.append('is_active=?')
            params.append(int(is_active))
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with get_connection() as conn:
            rows = conn.execute('SELECT * FROM spy_sources' + where + ' ORDER BY id DESC LIMIT ? OFFSET ?', params + [limit, offset]).fetchall()
            total = conn.execute('SELECT COUNT(1) as cnt FROM spy_sources' + where, params).fetchone()['cnt']
        return [dict(row) for row in rows], total

    @staticmethod
    def get_active_sources():
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM spy_sources WHERE is_active = 1 ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def get_source_by_id(source_id: int):
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM spy_sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def create_source(name: str, entry_url: str, request_headers: str, is_active: int) -> bool:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO spy_sources (name, entry_url, request_headers, is_active) VALUES (?, ?, ?, ?)",
                    (name, entry_url, request_headers, is_active)
                )
            return True
        except Exception:
            return False

    @staticmethod
    def update_source(source_id: int, name: str, entry_url: str, request_headers: str, is_active: int) -> bool:
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE spy_sources SET name=?, entry_url=?, request_headers=?, is_active=? WHERE id=?",
                    (name, entry_url, request_headers, is_active, source_id)
                )
            return True
        except Exception:
            return False

    @staticmethod
    def delete_source(source_id: int) -> bool:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM spy_sources WHERE id=?", (source_id,))
            return True
        except Exception:
            return False