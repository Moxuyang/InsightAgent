import tornado.web
from app.controllers.base import BaseHandler
from app.models.user import UserRepository

class UserPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("user/list.html", title="用户管理")

class UserApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        # 供 Layui Table 使用的数据接口
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        users, total = UserRepository.get_users_list(page, limit)
        self.write({
            "code": 0,
            "msg": "",
            "count": total,
            "data": users
        })

    @tornado.web.authenticated
    def post(self):
        # 统一处理增删改等操作
        action = self.get_argument("action", "")
        
        if action == "add":
            username = self.get_argument("username", "").strip()
            password = self.get_argument("password", "").strip()
            role_id = self.get_argument("role_id", "")
            role_id = int(role_id) if role_id else None
            
            if not username or not password:
                return self.write({"code": 1, "msg": "用户名和密码不能为空"})
            
            if UserRepository.create_user(username, password, role_id):
                self.write({"code": 0, "msg": "添加成功"})
            else:
                self.write({"code": 1, "msg": "添加失败，用户名可能已存在"})
                
        elif action == "edit":
            user_id = int(self.get_argument("id", 0))
            username = self.get_argument("username", "").strip()
            password = self.get_argument("password", "").strip()
            role_id = self.get_argument("role_id", "")
            role_id = int(role_id) if role_id else None
            
            if not user_id or not username:
                return self.write({"code": 1, "msg": "参数错误"})
                
            if UserRepository.update_user(user_id, username, password if password else None, role_id):
                self.write({"code": 0, "msg": "修改成功"})
            else:
                self.write({"code": 1, "msg": "修改失败，可能用户名冲突或不允许修改"})
                
        elif action == "delete":
            user_id = int(self.get_argument("id", 0))
            if not user_id:
                return self.write({"code": 1, "msg": "参数错误"})
            if UserRepository.delete_user(user_id):
                self.write({"code": 0, "msg": "删除成功"})
            else:
                self.write({"code": 1, "msg": "系统内置管理员账号不允许删除"})
            
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            if ids_str:
                ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
                if UserRepository.delete_users(ids):
                    self.write({"code": 0, "msg": "批量删除成功(系统管理员将被忽略)"})
                else:
                    self.write({"code": 1, "msg": "没有可以删除的用户"})
            else:
                self.write({"code": 1, "msg": "参数为空"})
            
        else:
            self.write({"code": 1, "msg": "未知操作"})
