import tornado.web
from app.controllers.base import BaseHandler
from app.models.data_warehouse import DataWarehouseRepository
from app.controllers.deep_collect import _normalize_url

class DataWarehousePageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("data_warehouse/list.html", title="数据仓库")

class DataWarehouseApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        source_id = self.get_argument('source_id', '')
        source_id = int(source_id) if source_id.isdigit() else None
        data_list, total = DataWarehouseRepository.get_data_list(page, limit, self.get_argument('keyword', '').strip(), source_id)
        # 将百度相对路径 URL 转为可点击的绝对 URL
        for row in data_list:
            row["url"] = _normalize_url(row.get("url") or "")
        self.write({"code": 0, "msg": "", "count": total, "data": data_list})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        
        if action == "delete":
            data_id = int(self.get_argument("id", 0))
            if DataWarehouseRepository.delete_data(data_id):
                self.write({"code": 0, "msg": "删除成功"})
            else:
                self.write({"code": 1, "msg": "删除失败"})
                
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            if ids_str:
                ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
                if DataWarehouseRepository.delete_batch(ids):
                    self.write({"code": 0, "msg": "批量删除成功"})
                else:
                    self.write({"code": 1, "msg": "删除失败"})
            else:
                self.write({"code": 1, "msg": "参数为空"})