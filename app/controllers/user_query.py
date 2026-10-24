import tornado.web
from app.controllers.base import BaseHandler
from app.models.user_query import UserQueryRepository

class UserQueryPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("user_query/list.html", title="对话管理")


class UserQueryApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        user_id = self.get_argument("user_id", None)
        if user_id:
            user_id = int(user_id)
        rows, total = UserQueryRepository.get_list(page, limit, user_id)
        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "delete":
            query_id = int(self.get_argument("id", 0))
            UserQueryRepository.delete(query_id)
            self.write({"code": 0, "msg": "删除成功"})
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if UserQueryRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})
        else:
            self.write({"code": 1, "msg": "未知操作"})
