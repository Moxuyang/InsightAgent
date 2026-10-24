from app.models.db import get_connection

class MenuRepository:
    @staticmethod
    def get_all_menus():
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM menus ORDER BY order_num ASC, id ASC").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def get_menu_tree(role_id=None):
        if role_id is None:
            menus = MenuRepository.get_all_menus()
        else:
            with get_connection() as conn:
                role_row = conn.execute("SELECT code FROM roles WHERE id=?", (role_id,)).fetchone()
                if role_row and role_row["code"] == "super_admin":
                    menus = MenuRepository.get_all_menus()
                else:
                    rows = conn.execute("""
                        SELECT m.* FROM menus m
                        INNER JOIN role_menus rm ON m.id = rm.menu_id
                        WHERE rm.role_id = ?
                        ORDER BY m.order_num ASC, m.id ASC
                    """, (role_id,)).fetchall()
                    menus = [dict(row) for row in rows]
            
        # Build tree
        menu_dict = {}
        ordered_ids = []
        for m in menus:
            mm = dict(m)
            mm["children"] = []
            menu_dict[mm["id"]] = mm
            ordered_ids.append(mm["id"])

        tree = []
        for mid in ordered_ids:
            m = menu_dict[mid]
            parent_id = m.get("parent_id", 0) or 0
            if parent_id == 0 or parent_id not in menu_dict:
                tree.append(m)
            else:
                menu_dict[parent_id]["children"].append(m)
        return tree

    @staticmethod
    def create_menu(name, url, icon, parent_id=0, order_num=0):
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO menus (name, url, icon, parent_id, order_num) VALUES (?, ?, ?, ?, ?)",
                (name, url, icon, parent_id, order_num)
            )
            return cursor.lastrowid

    @staticmethod
    def update_menu(menu_id, name, url, icon, parent_id=0, order_num=0):
        with get_connection() as conn:
            conn.execute(
                "UPDATE menus SET name=?, url=?, icon=?, parent_id=?, order_num=? WHERE id=?",
                (name, url, icon, parent_id, order_num, menu_id)
            )
        return True

    @staticmethod
    def delete_menu(menu_id):
        with get_connection() as conn:
            # check if has children
            children = conn.execute("SELECT count(1) as cnt FROM menus WHERE parent_id=?", (menu_id,)).fetchone()
            if children['cnt'] > 0:
                return False
            conn.execute("DELETE FROM menus WHERE id=?", (menu_id,))
            # clean up role mapping
            conn.execute("DELETE FROM role_menus WHERE menu_id=?", (menu_id,))
        return True
