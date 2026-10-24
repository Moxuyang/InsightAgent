import tornado.web
from app.controllers.base import BaseHandler
from app.models.menu import MenuRepository

class MenuPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("menu/list.html", title="功能管理")

class MenuApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "tree")
        if action == "tree":
            tree = MenuRepository.get_menu_tree()
            self.write({"code": 0, "msg": "", "data": tree})
        elif action == "list":
            menus = MenuRepository.get_all_menus()
            self.write({"code": 0, "msg": "", "count": len(menus), "data": menus})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "add":
            name = self.get_argument("name", "").strip()
            url = self.get_argument("url", "").strip()
            icon = self.get_argument("icon", "").strip()
            parent_id = int(self.get_argument("parent_id", 0))
            order_num = int(self.get_argument("order_num", 0))
            
            if not name:
                return self.write({"code": 1, "msg": "菜单名称不能为空"})
                
            MenuRepository.create_menu(name, url, icon, parent_id, order_num)
            self.write({"code": 0, "msg": "添加成功"})
            
        elif action == "edit":
            menu_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            url = self.get_argument("url", "").strip()
            icon = self.get_argument("icon", "").strip()
            parent_id = int(self.get_argument("parent_id", 0))
            order_num = int(self.get_argument("order_num", 0))
            
            if not menu_id or not name:
                return self.write({"code": 1, "msg": "参数错误"})
                
            MenuRepository.update_menu(menu_id, name, url, icon, parent_id, order_num)
            self.write({"code": 0, "msg": "修改成功"})
            
        elif action == "delete":
            menu_id = int(self.get_argument("id", 0))
            if MenuRepository.delete_menu(menu_id):
                self.write({"code": 0, "msg": "删除成功"})
            else:
                self.write({"code": 1, "msg": "请先删除子菜单"})
        else:
            self.write({"code": 1, "msg": "未知操作"})
