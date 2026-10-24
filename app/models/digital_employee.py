from app.models.db import get_connection

class DigitalEmployeeRepository:
    @staticmethod
    def get_list(page=1, limit=20, keyword=''):
        offset = (page - 1) * limit
        where, params = '', []
        if keyword:
            where = """ WHERE (de.name LIKE ? OR de.role_desc LIKE ? OR EXISTS (
                SELECT 1 FROM skills sk
                WHERE (',' || COALESCE(de.skill_ids, '') || ',') LIKE ('%,' || sk.id || ',%')
                AND sk.name LIKE ?))"""
            # CONCAT works on both configured backends through the connection type below.
            params = ['%' + keyword + '%'] * 3
        with get_connection() as conn:
            if conn.db_type == 'mysql':
                where = where.replace("(',' || COALESCE(de.skill_ids, '') || ',')", "CONCAT(',', COALESCE(de.skill_ids, ''), ',')").replace("('%,' || sk.id || ',%')", "CONCAT('%,', sk.id, ',%')")
            rows = conn.execute('SELECT de.*, am.name as model_name FROM digital_employees de '
                                'LEFT JOIN ai_models am ON de.model_engine_id=am.id' + where +
                                ' ORDER BY de.id DESC LIMIT ? OFFSET ?', params + [limit, offset]).fetchall()
            total = conn.execute('SELECT COUNT(1) as cnt FROM digital_employees de' + where, params).fetchone()['cnt']
        return [dict(r) for r in rows], total

    @staticmethod
    def get_all():
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM digital_employees WHERE is_active=1 ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def create(name, role_desc="", model_engine_id=None, skill_ids="", is_active=1):
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO digital_employees (name, role_desc, model_engine_id, skill_ids, is_active) VALUES (?,?,?,?,?)",
                (name, role_desc, model_engine_id, skill_ids, is_active)
            )
            return c.lastrowid

    @staticmethod
    def update(emp_id, name, role_desc, model_engine_id, skill_ids, is_active):
        with get_connection() as conn:
            conn.execute(
                "UPDATE digital_employees SET name=?, role_desc=?, model_engine_id=?, skill_ids=?, is_active=? WHERE id=?",
                (name, role_desc, model_engine_id, skill_ids, is_active, emp_id)
            )
        return True

    @staticmethod
    def delete(emp_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM digital_employees WHERE id=?", (emp_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM digital_employees WHERE id IN ({ph})", ids)
        return True
