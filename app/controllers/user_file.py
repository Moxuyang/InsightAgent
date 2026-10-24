import tornado.web
from app.controllers.base import BaseHandler
from app.models.user_file import UserFileRepository

class UserFilePageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("user_file/list.html", title="用户文件管理")


class UserFileApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        user_id = self.get_argument("user_id", None)
        if user_id:
            user_id = int(user_id)
        rows, total = UserFileRepository.get_list(page, limit, user_id)
        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "delete":
            file_id = int(self.get_argument("id", 0))
            UserFileRepository.delete(file_id)
            self.write({"code": 0, "msg": "删除成功"})
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if UserFileRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})
        else:
            self.write({"code": 1, "msg": "未知操作"})
