import tornado.web
from app.controllers.base import BaseHandler
from app.models.api_config import ApiConfigRepository

class ApiConfigPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("api_config/list.html", title="接口管理")


class ApiConfigApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        rows, total = ApiConfigRepository.get_list(page, limit)
        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "add":
            name = self.get_argument("name", "").strip()
            api_url = self.get_argument("api_url", "").strip()
            method = self.get_argument("method", "GET")
            headers = self.get_argument("headers", "")
            params = self.get_argument("params", "")
            is_active = int(self.get_argument("is_active", 1))
            if not name or not api_url:
                return self.write({"code": 1, "msg": "名称和接口URL不能为空"})
            ApiConfigRepository.create(name, api_url, method, headers, params, is_active)
            self.write({"code": 0, "msg": "添加成功"})
        elif action == "edit":
            cfg_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            api_url = self.get_argument("api_url", "").strip()
            method = self.get_argument("method", "GET")
            headers = self.get_argument("headers", "")
            params = self.get_argument("params", "")
            is_active = int(self.get_argument("is_active", 1))
            if not cfg_id or not name:
                return self.write({"code": 1, "msg": "参数错误"})
            ApiConfigRepository.update(cfg_id, name, api_url, method, headers, params, is_active)
            self.write({"code": 0, "msg": "修改成功"})
        elif action == "delete":
            cfg_id = int(self.get_argument("id", 0))
            ApiConfigRepository.delete(cfg_id)
            self.write({"code": 0, "msg": "删除成功"})
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if ApiConfigRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})
        else:
            self.write({"code": 1, "msg": "未知操作"})
