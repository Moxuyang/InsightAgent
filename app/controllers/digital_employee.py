import tornado.web
from app.controllers.base import BaseHandler
from app.models.digital_employee import DigitalEmployeeRepository
from app.models.skill import SkillRepository

class DigitalEmployeePageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("digital_employee/list.html", title="数字员工")


class DigitalEmployeeApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "list")
        
        if action == "skills":
            # 返回所有启用的技能列表，供前端复选框使用
            skills = SkillRepository.get_all_active()
            self.write({"code": 0, "data": skills})
            return
            
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        rows, total = DigitalEmployeeRepository.get_list(page, limit, self.get_argument('keyword', '').strip())
        # 为每行附加技能名称列表
        for row in rows:
            skill_ids_str = row.get("skill_ids", "")
            if skill_ids_str:
                ids = [int(s.strip()) for s in skill_ids_str.split(",") if s.strip().isdigit()]
                skill_names = SkillRepository.get_names_by_ids(ids)
                row["skill_names"] = ", ".join(skill_names) if skill_names else skill_ids_str
            else:
                row["skill_names"] = ""
        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "add":
            name = self.get_argument("name", "").strip()
            role_desc = self.get_argument("role_desc", "")
            model_engine_id = self.get_argument("model_engine_id", "")
            model_engine_id = int(model_engine_id) if model_engine_id else None
            # 支持数组形式的技能ID（复选框多选）
            skill_ids = self.get_arguments("skill_ids")
            if skill_ids:
                # 过滤空值和非法值
                skill_ids = ",".join(part.strip() for value in skill_ids for part in value.split(",") if part.strip().isdigit())
            else:
                # 兼容旧的逗号分隔字符串形式
                skill_ids = self.get_argument("skill_ids", "")
            is_active = int(self.get_argument("is_active", 1))
            if not name:
                return self.write({"code": 1, "msg": "名称不能为空"})
            DigitalEmployeeRepository.create(name, role_desc, model_engine_id, skill_ids, is_active)
            self.write({"code": 0, "msg": "添加成功"})
        elif action == "edit":
            emp_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            role_desc = self.get_argument("role_desc", "")
            model_engine_id = self.get_argument("model_engine_id", "")
            model_engine_id = int(model_engine_id) if model_engine_id else None
            # 支持数组形式的技能ID（复选框多选）
            skill_ids = self.get_arguments("skill_ids")
            if skill_ids:
                skill_ids = ",".join(part.strip() for value in skill_ids for part in value.split(",") if part.strip().isdigit())
            else:
                skill_ids = self.get_argument("skill_ids", "")
            is_active = int(self.get_argument("is_active", 1))
            if not emp_id or not name:
                return self.write({"code": 1, "msg": "参数错误"})
            DigitalEmployeeRepository.update(emp_id, name, role_desc, model_engine_id, skill_ids, is_active)
            self.write({"code": 0, "msg": "修改成功"})
        elif action == "delete":
            emp_id = int(self.get_argument("id", 0))
            DigitalEmployeeRepository.delete(emp_id)
            self.write({"code": 0, "msg": "删除成功"})
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if DigitalEmployeeRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})
        else:
            self.write({"code": 1, "msg": "未知操作"})
