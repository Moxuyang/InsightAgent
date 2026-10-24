from app.controllers.base import BaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository


class RegisterHandler(BaseHandler):
    """用户注册 Handler"""
    def get(self):
        self.render("register.html", title="用户注册", error=None)

    def post(self):
        username = self.get_argument("username", "").strip()
        password = self.get_argument("password", "").strip()
        password_confirm = self.get_argument("password_confirm", "").strip()

        if not username or not password:
            return self.render("register.html", title="用户注册", error="用户名和密码不能为空")

        if password != password_confirm:
            return self.render("register.html", title="用户注册", error="两次密码不一致")

        if len(password) < 6:
            return self.render("register.html", title="用户注册", error="密码长度不能少于6位")

        # 查找普通用户角色
        roles = RoleRepository.get_all_roles()
        default_role_id = None
        for r in roles:
            if r.get("code") == "common_user" or r.get("code") == "user":
                default_role_id = r["id"]
                break

        if UserRepository.create_user(username, password, default_role_id):
            self.redirect("/auth/login?msg=注册成功，请登录")
        else:
            self.render("register.html", title="用户注册", error="用户名已存在")
