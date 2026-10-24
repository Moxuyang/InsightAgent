import tornado.web
import json
from openai import AsyncOpenAI
from app.controllers.base import BaseHandler
from app.models.skill import SkillRepository
from app.models.model_engine import ModelEngineRepository
from app.models.db import get_connection

class SkillPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("skill/list.html", title="技能管理")


class SkillApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        rows, total = SkillRepository.get_list(page, limit, self.get_argument('keyword', '').strip(), self.get_argument('skill_type', ''))
        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "add":
            name = self.get_argument("name", "").strip()
            skill_type = self.get_argument("skill_type", "function_call")
            category = self.get_argument("category", "tool")
            description = self.get_argument("description", "")
            parameters = self.get_argument("parameters", "")
            execute_code = self.get_argument("execute_code", "")
            is_active = int(self.get_argument("is_active", 1))
            # API调用类型字段
            api_url = self.get_argument("api_url", "")
            api_method = self.get_argument("api_method", "POST")
            api_headers = self.get_argument("api_headers", "{}")
            api_body_template = self.get_argument("api_body_template", "")
            api_response_path = self.get_argument("api_response_path", "")
            if not name:
                return self.write({"code": 1, "msg": "名称不能为空"})
            SkillRepository.create(name, skill_type, category, description, parameters, execute_code, is_active,
                                   api_url, api_method, api_headers, api_body_template, api_response_path)
            self.write({"code": 0, "msg": "添加成功"})
        elif action == "edit":
            skill_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            skill_type = self.get_argument("skill_type", "function_call")
            category = self.get_argument("category", "tool")
            description = self.get_argument("description", "")
            parameters = self.get_argument("parameters", "")
            execute_code = self.get_argument("execute_code", "")
            is_active = int(self.get_argument("is_active", 1))
            # API调用类型字段
            api_url = self.get_argument("api_url", "")
            api_method = self.get_argument("api_method", "POST")
            api_headers = self.get_argument("api_headers", "{}")
            api_body_template = self.get_argument("api_body_template", "")
            api_response_path = self.get_argument("api_response_path", "")
            if not skill_id or not name:
                return self.write({"code": 1, "msg": "参数错误"})
            SkillRepository.update(skill_id, name, skill_type, category, description, parameters, execute_code, is_active,
                                   api_url, api_method, api_headers, api_body_template, api_response_path)
            self.write({"code": 0, "msg": "修改成功"})
        elif action == "delete":
            skill_id = int(self.get_argument("id", 0))
            SkillRepository.delete(skill_id)
            self.write({"code": 0, "msg": "删除成功"})
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if SkillRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})
        else:
            self.write({"code": 1, "msg": "未知操作"})


class SkillAiGenerateHandler(BaseHandler):
    """AI智能生成技能内容"""
    @tornado.web.authenticated
    async def post(self):
        # 用户必选参数
        model_id = self.get_argument("model_id", "").strip()
        skill_type = self.get_argument("skill_type", "").strip()
        category = self.get_argument("category", "").strip()
        description = self.get_argument("description", "").strip()

        # 可选：API 详细提示字段（帮助 AI 更准确理解 API）
        api_request_example = self.get_argument("api_request_example", "").strip()
        api_method_hint = self.get_argument("api_method_hint", "").strip()
        api_response_format = self.get_argument("api_response_format", "").strip()
        api_param_desc = self.get_argument("api_param_desc", "").strip()
        api_response_example = self.get_argument("api_response_example", "").strip()

        if not model_id:
            return self.write({"code": 1, "msg": "请选择要调用的AI模型"})
        if not skill_type:
            return self.write({"code": 1, "msg": "请选择技能类型"})
        if not category:
            return self.write({"code": 1, "msg": "请选择技能分类"})
        if not description:
            return self.write({"code": 1, "msg": "请填写生成要求"})

        # 根据用户选择的模型ID获取模型信息
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM ai_models WHERE id=?", (int(model_id),)).fetchone()

        if not row:
            return self.write({"code": 1, "msg": "所选模型不存在"})

        model_info = dict(row)

        # 构造提示词让AI生成技能内容（根据类型不同，提示也不同）
        if skill_type == 'function_call':
            # 拼接额外的 API 上下文提示
            extra_context = ""
            if api_method_hint:
                extra_context += f"""\n【用户指定的请求方式】：{api_method_hint}"""
            if api_request_example:
                extra_context += f"""\n【API请求示例】：{api_request_example}"""
            if api_response_format:
                extra_context += f"""\n【API返回格式】：{api_response_format}"""
            if api_param_desc:
                extra_context += f"""\n【请求参数说明】：{api_param_desc}"""
            if api_response_example:
                extra_context += f"""\n【API返回示例】：{api_response_example}"""

            prompt = f"""你是一个API技能配置专家。用户需要创建一个调用外部API的技能，请根据用户提供的所有信息生成完整的API配置。

【技能类型】：function_call（外部API调用，真实发起HTTP请求）
【技能分类】：{category}
【生成要求】：{description}{extra_context}

重要规则：
- api_url 如果是GET请求，参数用?key=值拼接到URL中，用户输入用 {{query}} 占位符标记
- api_url 如果是POST请求，参数放在 api_body_template 中，用 {{query}} 占位符
- api_response_path 用点号分隔JSON路径，如 data.result.content
- 请求头非必填，不需要鉴权的API直接填 {{}}
- 如果用户提供了API请求示例和返回示例，请严格参照它们来配置
- 如果用户给出了请求方式，必须使用用户指定的方式（GET/POST）

请严格按以下JSON格式输出，不要输出任何其他内容：
{{
    "name": "技能名称（简洁明了，5-15字）",
    "description": "技能功能描述，说明用途和API来源，50-200字",
    "api_url": "https://api.example.com/endpoint?key={{query}}",
    "api_method": "GET或POST",
    "api_headers": "{{}}",
    "api_body_template": "POST请求时的JSON请求体模板，GET请求留空",
    "api_response_path": "响应数据的提取路径，如 data.result"
}}"""
        else:  # skill.md
            prompt = f"""你是一个AI技能设计专家。请为用户创建一个skill.md类型的AI提示词模板技能。

【技能类型】：skill.md（提示词模板，让数字员工按模板回复）
【技能分类】：{category}
【生成要求】：{description}

请严格按以下JSON格式输出，不要输出任何其他内容：
{{
    "name": "技能名称（简洁明了，5-15字）",
    "description": "技能功能的详细描述，说明使用场景和预期效果，50-200字",
    "parameters": {{"type":"object","properties":{{"topic":{{"type":"string","description":"用户输入的主题"}}}},"required":["topic"]}},
    "execute_code": "# 提示词模板\\nSYSTEM_PROMPT = '''你是一个专业的[角色]...'''"
}}

注意：
- parameters 定义用户需要提供的参数
- execute_code 中包含完整的系统提示词模板，以SYSTEM_PROMPT变量开头"""


        try:
            client = AsyncOpenAI(
                api_key=model_info['api_key'],
                base_url=model_info['base_url']
            )

            response = await client.chat.completions.create(
                model=model_info['model_name'],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2000
            )

            content = response.choices[0].message.content.strip()

            # 处理可能的markdown代码块包裹
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
                content = content.strip()

            result = json.loads(content)

            # 记录token消耗
            if hasattr(response, 'usage') and response.usage:
                ModelEngineRepository.add_tokens(model_info['id'], response.usage.total_tokens)

            # 处理 parameters - 确保是字符串格式的JSON
            params = result.get("parameters", "{}")
            if isinstance(params, dict):
                params = json.dumps(params, ensure_ascii=False)

            resp_data = {
                "name": result.get("name", ""),
                "description": result.get("description", ""),
                "parameters": params,
                "execute_code": result.get("execute_code", "")
            }

            # function_call 类型需要额外返回API专属字段
            if skill_type == 'function_call':
                resp_data['api_url'] = result.get('api_url', '')
                resp_data['api_method'] = result.get('api_method', 'GET')
                resp_data['api_headers'] = result.get('api_headers', '{}')
                resp_data['api_body_template'] = result.get('api_body_template', '')
                resp_data['api_response_path'] = result.get('api_response_path', '')

            self.write({
                "code": 0,
                "data": resp_data,
                "msg": "AI智能生成完成！请检查并修改后保存"
            })

        except json.JSONDecodeError:
            # JSON解析失败，用原始内容填充description
            self.write({
                "code": 0,
                "data": {
                    "name": description[:15],
                    "description": content,
                    "parameters": "{}",
                    "execute_code": ""
                },
                "msg": "AI已生成内容，但格式不标准，已自动填入描述区域"
            })
        except Exception as e:
            self.write({"code": 1, "msg": f"AI生成失败: {str(e)}"})
