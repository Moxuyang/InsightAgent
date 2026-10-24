import tornado.web
from app.controllers.base import BaseHandler
from app.models.spy_source import SpySourceRepository

class SpySourcePageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("spy/source_list.html", title="瞭望数据源管理")

class SpySourceApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        # 兼容下拉框获取所有激活的数据源
        action = self.get_argument("action", "")
        if action == "active_list":
            sources = SpySourceRepository.get_active_sources()
            return self.write({"code": 0, "data": sources})
            
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        sources, total = SpySourceRepository.get_sources_list(page, limit, self.get_argument('keyword', '').strip(), self.get_argument('is_active', ''))
        self.write({"code": 0, "msg": "", "count": total, "data": sources})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        
        if action == "add":
            name = self.get_argument("name", "").strip()
            entry_url = self.get_argument("entry_url", "").strip()
            request_headers = self.get_argument("request_headers", "").strip()
            is_active = int(self.get_argument("is_active", 1))
            
            if not all([name, entry_url]):
                return self.write({"code": 1, "msg": "名称和采集入口不能为空"})
                
            if SpySourceRepository.create_source(name, entry_url, request_headers, is_active):
                self.write({"code": 0, "msg": "新增成功"})
            else:
                self.write({"code": 1, "msg": "新增失败"})
                
        elif action == "edit":
            source_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            entry_url = self.get_argument("entry_url", "").strip()
            request_headers = self.get_argument("request_headers", "").strip()
            is_active = int(self.get_argument("is_active", 1))
            
            if not source_id or not all([name, entry_url]):
                return self.write({"code": 1, "msg": "参数错误"})
                
            if SpySourceRepository.update_source(source_id, name, entry_url, request_headers, is_active):
                self.write({"code": 0, "msg": "修改成功"})
            else:
                self.write({"code": 1, "msg": "修改失败"})
                
        elif action == "delete":
            source_id = int(self.get_argument("id", 0))
            if SpySourceRepository.delete_source(source_id):
                self.write({"code": 0, "msg": "删除成功"})
            else:
                self.write({"code": 1, "msg": "删除失败"})