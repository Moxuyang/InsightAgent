from app.models.db import get_connection

class SkillRepository:
    @staticmethod
    def get_list(page=1, limit=20, keyword='', skill_type=''):
        offset = (page - 1) * limit
        clauses, params = [], []
        if keyword:
            clauses.append('(name LIKE ? OR description LIKE ? OR category LIKE ?)')
            params.extend(['%' + keyword + '%'] * 3)
        if skill_type in ('function_call', 'skill.md'):
            clauses.append('skill_type=?')
            params.append(skill_type)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with get_connection() as conn:
            rows = conn.execute('SELECT * FROM skills' + where + ' ORDER BY id DESC LIMIT ? OFFSET ?',
                                params + [limit, offset]).fetchall()
            total = conn.execute('SELECT COUNT(1) as cnt FROM skills' + where, params).fetchone()['cnt']
        return [dict(r) for r in rows], total

    @staticmethod
    def get_all_active():
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM skills WHERE is_active=1 ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def create(name, skill_type="function_call", category="tool", description="", parameters="", execute_code="", is_active=1,
               api_url="", api_method="POST", api_headers="{}", api_body_template="", api_response_path=""):
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO skills (name, skill_type, category, description, parameters, execute_code, is_active, "
                "api_url, api_method, api_headers, api_body_template, api_response_path) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, skill_type, category, description, parameters, execute_code, is_active,
                 api_url, api_method, api_headers, api_body_template, api_response_path)
            )
            return c.lastrowid

    @staticmethod
    def update(skill_id, name, skill_type="function_call", category="tool", description="", parameters="", execute_code="", is_active=1,
               api_url="", api_method="POST", api_headers="{}", api_body_template="", api_response_path=""):
        with get_connection() as conn:
            conn.execute(
                "UPDATE skills SET name=?, skill_type=?, category=?, description=?, parameters=?, execute_code=?, is_active=?, "
                "api_url=?, api_method=?, api_headers=?, api_body_template=?, api_response_path=? WHERE id=?",
                (name, skill_type, category, description, parameters, execute_code, is_active,
                 api_url, api_method, api_headers, api_body_template, api_response_path, skill_id)
            )
        return True

    @staticmethod
    def delete(skill_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM skills WHERE id IN ({ph})", ids)
        return True

    @staticmethod
    def get_names_by_ids(ids):
        """根据ID列表批量获取技能名称"""
        if not ids:
            return []
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            rows = conn.execute(f"SELECT id, name FROM skills WHERE id IN ({ph})", ids).fetchall()
        id_name_map = {r["id"]: r["name"] for r in rows}
        return [id_name_map.get(sid, str(sid)) for sid in ids]
