from app.models.db import get_connection

class RoleRepository:
    @staticmethod
    def get_all_roles():
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM roles ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def create_role(name, code, is_system=0):
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO roles (name, code, is_system) VALUES (?, ?, ?)",
                (name, code, is_system)
            )
            return cursor.lastrowid

    @staticmethod
    def update_role(role_id, name, code):
        with get_connection() as conn:
            # check if system role
            role = conn.execute("SELECT is_system FROM roles WHERE id=?", (role_id,)).fetchone()
            if role and role['is_system'] == 1:
                return False # Cannot update system role
                
            conn.execute("UPDATE roles SET name=?, code=? WHERE id=?", (name, code, role_id))
        return True

    @staticmethod
    def delete_role(role_id):
        with get_connection() as conn:
            role = conn.execute("SELECT is_system FROM roles WHERE id=?", (role_id,)).fetchone()
            if role and role['is_system'] == 1:
                return False # Cannot delete system role
                
            conn.execute("DELETE FROM roles WHERE id=?", (role_id,))
            conn.execute("DELETE FROM role_menus WHERE role_id=?", (role_id,))
            conn.execute("DELETE FROM user_roles WHERE role_id=?", (role_id,))
        return True

    # Permission mapping
    @staticmethod
    def get_role_menus(role_id):
        with get_connection() as conn:
            rows = conn.execute("SELECT menu_id FROM role_menus WHERE role_id=?", (role_id,)).fetchall()
        return [row['menu_id'] for row in rows]

    @staticmethod
    def assign_role_menus(role_id, menu_ids):
        with get_connection() as conn:
            conn.execute("DELETE FROM role_menus WHERE role_id=?", (role_id,))
            for menu_id in menu_ids:
                conn.execute("INSERT INTO role_menus (role_id, menu_id) VALUES (?, ?)", (role_id, menu_id))
        return True
