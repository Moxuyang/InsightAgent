import tornado.web
import json
from openai import AsyncOpenAI
from app.controllers.base import BaseHandler
from app.models.model_engine import ModelEngineRepository

class ModelEnginePageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("model_engine/list.html", title="模型引擎管理")

class ModelEngineApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "list")
        
        if action == "get_default":
            from app.models.db import get_connection
            with get_connection() as conn:
                row = conn.execute("SELECT * FROM ai_models WHERE is_default = 1 LIMIT 1").fetchone()
                if not row:
                    row = conn.execute("SELECT * FROM ai_models ORDER BY id ASC LIMIT 1").fetchone()
            if row:
                self.write({"code": 0, "data": dict(row)})
            else:
                self.write({"code": 1, "msg": "尚未配置AI模型，请先在模型引擎中添加"})
            return
            
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 6))
        
        models, total = ModelEngineRepository.get_models_list(page, limit)
        self.write({
            "code": 0,
            "msg": "",
            "count": total,
            "data": models
        })

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        
        if action == "add":
            name = self.get_argument("name", "").strip()
            model_name = self.get_argument("model_name", "").strip()
            api_key = self.get_argument("api_key", "").strip()
            base_url = self.get_argument("base_url", "").strip()
            
            if not all([name, model_name, api_key, base_url]):
                return self.write({"code": 1, "msg": "所有配置项都必须填写"})
                
            if ModelEngineRepository.create_model(name, model_name, api_key, base_url):
                self.write({"code": 0, "msg": "新增模型成功"})
            else:
                self.write({"code": 1, "msg": "新增失败"})
                
        elif action == "edit":
            model_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            model_name = self.get_argument("model_name", "").strip()
            api_key = self.get_argument("api_key", "").strip()
            base_url = self.get_argument("base_url", "").strip()
            
            if not model_id or not all([name, model_name, api_key, base_url]):
                return self.write({"code": 1, "msg": "参数错误或必填项为空"})
                
            if ModelEngineRepository.update_model(model_id, name, model_name, api_key, base_url):
                self.write({"code": 0, "msg": "修改成功"})
            else:
                self.write({"code": 1, "msg": "修改失败"})
                
        elif action == "delete":
            model_id = int(self.get_argument("id", 0))
            if not model_id:
                return self.write({"code": 1, "msg": "参数错误"})
                
            if ModelEngineRepository.delete_model(model_id):
                self.write({"code": 0, "msg": "删除成功"})
            else:
                self.write({"code": 1, "msg": "删除失败"})
                
        elif action == "set_default":
            model_id = int(self.get_argument("id", 0))
            if not model_id:
                return self.write({"code": 1, "msg": "参数错误"})
                
            if ModelEngineRepository.set_default(model_id):
                self.write({"code": 0, "msg": "已设为系统默认模型"})
            else:
                self.write({"code": 1, "msg": "设置失败"})

class ModelTestApiHandler(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        model_id = int(self.get_argument("id", 0))
        message = self.get_argument("message", "你好")
        
        # 设置流式响应头 (SSE)
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Cache-Control', 'no-cache')
        self.set_header('Connection', 'keep-alive')
        
        model_info = ModelEngineRepository.get_model_by_id(model_id)
        if not model_info:
            self.write(f"data: {json.dumps({'error': '模型不存在'})}\n\n")
            await self.flush()
            return
            
        try:
            # 初始化异步 OpenAI 客户端
            client = AsyncOpenAI(
                api_key=model_info['api_key'],
                base_url=model_info['base_url']
            )
            
            # 发起流式请求
            response = await client.chat.completions.create(
                model=model_info['model_name'],
                messages=[{"role": "user", "content": message}],
                stream=True,
                stream_options={"include_usage": True}
            )
            
            total_tokens = 0
            
            async for chunk in response:
                if len(chunk.choices) > 0 and chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    self.write(f"data: {json.dumps({'content': content})}\n\n")
                    await self.flush()
                    
                # 兼容 stream_options 返回的 usage 信息
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    total_tokens = chunk.usage.total_tokens
            
            # 记录消耗的 tokens
            if total_tokens > 0:
                ModelEngineRepository.add_tokens(model_id, total_tokens)
                self.write(f"data: {json.dumps({'tokens': total_tokens})}\n\n")
                await self.flush()
                
            self.write("data: [DONE]\n\n")
            await self.flush()
            
        except Exception as e:
            self.write(f"data: {json.dumps({'error': f'模型调用失败: {str(e)}'})}\n\n")
            await self.flush()
