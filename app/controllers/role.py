import tornado.web
import sqlite3
from app.controllers.base import BaseHandler
from app.models.role import RoleRepository

class RolePageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("role/list.html", title="角色管理")

class RoleApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        roles = RoleRepository.get_all_roles()
        self.write({"code": 0, "msg": "", "count": len(roles), "data": roles})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        
        if action == "add":
            name = self.get_argument("name", "").strip()
            code = self.get_argument("code", "").strip()
            if not name or not code:
                return self.write({"code": 1, "msg": "名称和标识不能为空"})
            try:
                RoleRepository.create_role(name, code)
                self.write({"code": 0, "msg": "添加成功"})
            except sqlite3.IntegrityError:
                self.write({"code": 1, "msg": "角色名称或标识已存在"})
                
        elif action == "edit":
            role_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            code = self.get_argument("code", "").strip()
            if not role_id or not name:
                return self.write({"code": 1, "msg": "参数错误"})
            try:
                if RoleRepository.update_role(role_id, name, code):
                    self.write({"code": 0, "msg": "修改成功"})
                else:
                    self.write({"code": 1, "msg": "系统内置角色不允许修改"})
            except sqlite3.IntegrityError:
                self.write({"code": 1, "msg": "角色名称或标识已存在"})
                
        elif action == "delete":
            role_id = int(self.get_argument("id", 0))
            if RoleRepository.delete_role(role_id):
                self.write({"code": 0, "msg": "删除成功"})
            else:
                self.write({"code": 1, "msg": "系统内置角色不允许删除"})
                
        elif action == "get_permissions":
            role_id = int(self.get_argument("id", 0))
            menu_ids = RoleRepository.get_role_menus(role_id)
            self.write({"code": 0, "msg": "", "data": menu_ids})
            
        elif action == "assign_permissions":
            role_id = int(self.get_argument("id", 0))
            menu_ids_str = self.get_argument("menu_ids", "")
            menu_ids = [int(i) for i in menu_ids_str.split(",") if i.strip().isdigit()]
            RoleRepository.assign_role_menus(role_id, menu_ids)
            self.write({"code": 0, "msg": "权限分配成功"})
            
        else:
            self.write({"code": 1, "msg": "未知操作"})
