import tornado.web
from app.controllers.base import BaseHandler
from app.models.role import RoleRepository
from app.models.menu import MenuRepository

class PermissionPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        roles = RoleRepository.get_all_roles()
        self.render("permission/list.html", title="权限管理", roles=roles)


class PermissionApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "list")
        if action == "list":
            roles = RoleRepository.get_all_roles()
            result = []
            for r in roles:
                menu_ids = RoleRepository.get_role_menus(r["id"])
                menus = MenuRepository.get_all_menus()
                menu_names = [m["name"] for m in menus if m["id"] in menu_ids]
                result.append({
                    "role_id": r["id"],
                    "role_name": r["name"],
                    "role_code": r["code"],
                    "menu_ids": menu_ids,
                    "menu_names": ", ".join(menu_names),
                    "is_system": r["is_system"]
                })
            self.write({"code": 0, "msg": "", "data": result})
        elif action == "detail":
            role_id = int(self.get_argument("role_id", 0))
            menu_ids = RoleRepository.get_role_menus(role_id)
            self.write({"code": 0, "data": menu_ids})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "save":
            role_id = int(self.get_argument("role_id", 0))
            menu_ids_str = self.get_argument("menu_ids", "")
            menu_ids = [int(i) for i in menu_ids_str.split(",") if i.strip().isdigit()]
            RoleRepository.assign_role_menus(role_id, menu_ids)
            self.write({"code": 0, "msg": "权限保存成功"})
        else:
            self.write({"code": 1, "msg": "未知操作"})
