"""协作沟通模块 - 控制器"""
import json
import tornado.web
import asyncio
from app.services.news_qa import build_news_graph, append_source_refs
from app.services.agent_context import is_business_question
from app.controllers.base import BaseHandler
from app.models.collaboration import CollabGroupRepository, CollabMemberRepository, CollabMessageRepository
from app.services.api_skill_executor import execute_api_skill, find_api_skills


class CollabPageHandler(BaseHandler):
    """群组列表页面"""
    @tornado.web.authenticated
    def get(self):
        self.render("collaboration/list.html", title="协作沟通")


class CollabChatPageHandler(BaseHandler):
    """群聊聊天页面"""
    @tornado.web.authenticated
    def get(self):
        group_id = int(self.get_argument("group_id", 0))
        group = CollabGroupRepository.get_by_id(group_id)
        if not group:
            self.redirect("/collaboration/list")
            return
        members = CollabMemberRepository.get_members(group_id)
        self.render("collaboration/chat.html", title=group['name'], group=group, members=members)


class CollabApiHandler(BaseHandler):
    """群组 CRUD + 成员管理 API"""

    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "list")
        user = self.current_user
        user_id = user['id'] if user else 0

        if action == "members":
            group_id = int(self.get_argument("group_id", 0))
            members = CollabMemberRepository.get_members(group_id)
            self.write({"code": 0, "data": members})
            return

        if action == "available_users":
            group_id = self.get_argument("group_id", None)
            if group_id:
                group_id = int(group_id)
            users = CollabMemberRepository.get_available_users(group_id)
            self.write({"code": 0, "data": users})
            return

        if action == "available_employees":
            group_id = self.get_argument("group_id", None)
            if group_id:
                group_id = int(group_id)
            employees = CollabMemberRepository.get_available_employees(group_id)
            self.write({"code": 0, "data": employees})
            return

        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        rows, total = CollabGroupRepository.get_list(page, limit, user_id)
        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        user = self.current_user
        user_id = user['id'] if user else 0

        if action == "add":
            name = self.get_argument("name", "").strip()
            description = self.get_argument("description", "")
            if not name:
                return self.write({"code": 1, "msg": "群组名称不能为空"})
            gid = CollabGroupRepository.create(name, user_id, description)
            self.write({"code": 0, "msg": "群组创建成功", "data": {"id": gid}})

        elif action == "edit":
            group_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            description = self.get_argument("description", "")
            if not group_id or not name:
                return self.write({"code": 1, "msg": "参数错误"})
            CollabGroupRepository.update(group_id, name, description)
            self.write({"code": 0, "msg": "修改成功"})

        elif action == "delete":
            group_id = int(self.get_argument("id", 0))
            CollabGroupRepository.delete(group_id)
            self.write({"code": 0, "msg": "删除成功"})

        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if CollabGroupRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})

        # ---- 成员管理 ----
        elif action == "invite_user":
            group_id = int(self.get_argument("group_id", 0))
            target_user_id = int(self.get_argument("user_id", 0))
            if not group_id or not target_user_id:
                return self.write({"code": 1, "msg": "参数错误"})
            CollabMemberRepository.add_member(group_id, 'user', target_user_id)
            self.write({"code": 0, "msg": "邀请用户成功"})

        elif action == "invite_employee":
            group_id = int(self.get_argument("group_id", 0))
            employee_id = int(self.get_argument("employee_id", 0))
            if not group_id or not employee_id:
                return self.write({"code": 1, "msg": "参数错误"})
            CollabMemberRepository.add_member(group_id, 'employee', employee_id)
            self.write({"code": 0, "msg": "邀请数字员工成功"})

        elif action == "remove_member":
            group_id = int(self.get_argument("group_id", 0))
            member_type = self.get_argument("member_type", "")
            member_id = int(self.get_argument("member_id", 0))
            if not group_id or not member_type or not member_id:
                return self.write({"code": 1, "msg": "参数错误"})
            CollabMemberRepository.remove_member(group_id, member_type, member_id)
            self.write({"code": 0, "msg": "移除成员成功"})

        elif action == "invite_batch":
            group_id = int(self.get_argument("group_id", 0))
            user_ids = self.get_argument("user_ids", "")  # 逗号分隔
            employee_ids = self.get_argument("employee_ids", "")  # 逗号分隔
            if not group_id:
                return self.write({"code": 1, "msg": "参数错误"})
            if user_ids:
                for uid in user_ids.split(","):
                    uid = uid.strip()
                    if uid.isdigit():
                        CollabMemberRepository.add_member(group_id, 'user', int(uid))
            if employee_ids:
                for eid in employee_ids.split(","):
                    eid = eid.strip()
                    if eid.isdigit():
                        CollabMemberRepository.add_member(group_id, 'employee', int(eid))
            self.write({"code": 0, "msg": "批量邀请成功"})

        else:
            self.write({"code": 1, "msg": "未知操作"})


class CollabChatApiHandler(BaseHandler):
    """群聊消息 API —— 获取消息 / 发送消息 / AI流式回复"""

    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "messages")
        group_id = int(self.get_argument("group_id", 0))

        if not group_id:
            self.write({"code": 1, "msg": "group_id 必填"})
            return

        if not self._can_access_group(group_id,self.current_user['id']):
            self.set_status(403)
            self.write({'code':1,'msg':'你不是该群组成员'})
            return

        if action == "messages":
            limit = int(self.get_argument("limit", 100))
            before_id = self.get_argument("before_id", None)
            if before_id:
                before_id = int(before_id)
            messages = CollabMessageRepository.get_messages(group_id, limit, before_id)
            self.write({"code": 0, "data": messages})
            return

        if action == "group_info":
            group = CollabGroupRepository.get_by_id(group_id)
            members = CollabMemberRepository.get_members(group_id)
            self.write({"code": 0, "data": {"group": group, "members": members}})
            return

        self.write({"code": 1, "msg": "未知操作"})

    @tornado.web.authenticated
    async def post(self):
        action = self.get_argument("action", "")
        user = self.current_user
        user_id = user['id'] if user else 0

        if action == "send":
            group_id = int(self.get_argument("group_id", 0))
            content = self.get_argument("content", "").strip()
            mentioned_id = self.get_argument("mentioned_id", None)
            # 防御：前端可能传字符串 "null" / "undefined" / 空字符串
            if mentioned_id and mentioned_id not in ("null", "undefined", ""):
                try:
                    mentioned_id = int(mentioned_id)
                except (ValueError, TypeError):
                    mentioned_id = None
            else:
                mentioned_id = None

            if not group_id or not content:
                self.write({"code": 1, "msg": "群组ID和消息内容不能为空"})
                return

            if not self._can_access_group(group_id,user_id):
                self.set_status(403)
                self.write({'code':1,'msg':'你不是该群组成员'})
                return
            if mentioned_id and not any(m['member_type']=='employee' and m['member_id']==mentioned_id for m in CollabMemberRepository.get_members(group_id)):
                self.set_status(403)
                self.write({'code':1,'msg':'该数字员工不在当前群组'})
                return
            if len(content)>4000:
                self.set_status(400)
                self.write({'code':1,'msg':'消息最多4000字'})
                return

            # 保存用户消息
            msg_id = CollabMessageRepository.add_message(group_id, 'user', user_id, content, mentioned_id)

            # 如果@了数字员工，需要AI回复
            if mentioned_id:
                await self._handle_employee_reply(group_id, mentioned_id, content, user_id, msg_id)
            elif '@' in content:
                # Only attempt AI routing when a member is mentioned.
                await self._handle_mention_reply(group_id, content, user_id, msg_id)
            else:
                self.write({"code": 0, "msg": "消息已发送", "data": {"id": msg_id}})

        else:
            self.write({"code": 1, "msg": "未知操作"})

    @staticmethod
    def _can_access_group(group_id,user_id):
        group=CollabGroupRepository.get_by_id(group_id)
        if not group or not group.get('is_active',1):return False
        return group.get('creator_id')==user_id or any(m['member_type']=='user' and m['member_id']==user_id for m in CollabMemberRepository.get_members(group_id))

    def _send_sse_event(self, data: dict, done: bool = False):
        """发送SSE事件片段（不设置headers，调用者需先设置）"""
        payload = dict(data)
        payload['done'] = done
        self.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")

    async def _handle_employee_reply(self, group_id, employee_id, content, user_id, trigger_msg_id):
        """处理对数字员工的@回复 —— 优先调用API技能，无则降级AI"""
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        emp_info = CollabMessageRepository.get_employee_info(employee_id)
        if not emp_info:
            self._send_sse_event({"error": True, "content": "数字员工不存在或已被删除。"}, done=True)
            await self.flush()
            self.finish()
            return

        # 提取用户真实问题（去掉@提及部分）
        import re
        clean_query = re.sub(r'@\S+\s*', '', content).strip()
        if not clean_query:
            clean_query = content

        # ---- 优先：尝试执行 API 技能 ----
        api_skills = find_api_skills(emp_info)
        if api_skills and not is_business_question(clean_query):
            await self._execute_api_skills(group_id, employee_id, emp_info, api_skills, clean_query, content, trigger_msg_id)
            return

        # ---- 降级：AI 模型回复 ----
        actual_model = emp_info.get('model_id_name') or emp_info.get('model_name', '')
        if not emp_info.get('api_key') or not actual_model:
            self._send_sse_event({"error": True, "content": f"数字员工「{emp_info['name']}」未绑定AI模型，且没有可执行的API技能。请在数字员工管理中为其绑定模型引擎或API技能。"}, done=True)
            await self.flush()
            self.finish()
            return

        await self._stream_ai_response(group_id, employee_id, emp_info, clean_query, trigger_msg_id)

    async def _handle_mention_reply(self, group_id, content, user_id, trigger_msg_id):
        """解析消息中的@数字员工，自动触发回复（优先API技能）"""
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        members = CollabMemberRepository.get_members(group_id)
        employees = [m for m in members if m['member_type'] == 'employee']

        if not employees:
            self._send_sse_event({"error": True, "content": "当前群组没有数字员工。"}, done=True)
            await self.flush()
            self.finish()
            return

        import re
        mentioned_emp = None
        for emp in employees:
            emp_name = emp.get('display_name', '') or emp.get('member_name', '')
            if emp_name and ('@' + emp_name) in content:
                mentioned_emp = emp
                break

        if not mentioned_emp:
            self._send_sse_event({"error": True, "content": "未在消息中找到@提及的数字员工。"}, done=True)
            await self.flush()
            self.finish()
            return

        employee_id = mentioned_emp['member_id']
        emp_info = CollabMessageRepository.get_employee_info(employee_id)
        if not emp_info:
            self._send_sse_event({"error": True, "content": "数字员工不存在或已被删除。"}, done=True)
            await self.flush()
            self.finish()
            return

        # 提取真实问题
        clean_query = re.sub(r'@\S+\s*', '', content).strip()
        if not clean_query:
            clean_query = content

        # ---- 优先：尝试执行 API 技能 ----
        api_skills = find_api_skills(emp_info)
        if api_skills and not is_business_question(clean_query):
            await self._execute_api_skills(group_id, employee_id, emp_info, api_skills, clean_query, content, trigger_msg_id)
            return

        # ---- 降级：AI 模型回复 ----
        actual_model = emp_info.get('model_id_name') or emp_info.get('model_name', '')
        if not emp_info.get('api_key') or not actual_model:
            self._send_sse_event({"error": True, "content": f"数字员工「{emp_info['name']}」未绑定AI模型，且没有可执行的API技能。"}, done=True)
            await self.flush()
            self.finish()
            return

        await self._stream_ai_response(group_id, employee_id, emp_info, clean_query, trigger_msg_id)

    async def _execute_api_skills(self, group_id, employee_id, emp_info, api_skills, clean_query, original_content, trigger_msg_id):
        """执行API类型技能，通过SSE返回结果"""
        emp_name = emp_info['name']
        total_skills = len(api_skills)

        # 检查 query 是否为空
        if not clean_query or not clean_query.strip():
            self._send_sse_event({
                "status": "thinking",
                "status_text": f"⚠️ 请提供具体问题，如：@英语老师tim average"
            })
            await self.flush()
            self._send_sse_event({
                "content": f"👋 你好！我是「{emp_name}」，请告诉我你想查询什么？\n\n"
                           f"💡 用法示例：\n@英语老师tim average\n@百科助手 人工智能",
                "employee_id": employee_id,
                "emp_name": emp_name
            })
            await self.flush()
            CollabMessageRepository.add_message(group_id, 'employee', employee_id,
                f"👋 你好！我是「{emp_name}」，请告诉我你想查询什么？\n\n💡 用法示例：@英语老师tim average")
            self._send_sse_event({"employee_id": employee_id}, done=True)
            await self.flush()
            self.finish()
            return

        # 发送开始状态
        self._send_sse_event({
            "status": "thinking",
            "status_text": f"⚡ 正在调用 {emp_name} 的API技能（共{total_skills}个）..."
        })
        await self.flush()

        all_results = []
        success_count = 0

        for idx, skill in enumerate(api_skills):
            skill_name = skill.get('name', f'技能{idx+1}')
            api_url = skill.get('api_url', '')

            # 发送单技能执行状态
            if total_skills > 1:
                self._send_sse_event({
                    "status": "generating",
                    "status_text": f"⚡ [{idx+1}/{total_skills}] 调用「{skill_name}」..."
                })
                await self.flush()

            # 在线程池中执行同步的API调用
            import tornado.ioloop
            result = await tornado.ioloop.IOLoop.current().run_in_executor(
                None, lambda s=skill, q=clean_query: execute_api_skill(s, q)
            )

            if result.get('success'):
                success_count += 1
                # 美化结果展示
                skill_result = f"━━━ {skill_name} ━━━\n{result['content']}"
                all_results.append(skill_result)
            else:
                error_msg = result.get('error', '未知错误')
                all_results.append(f"━━━ {skill_name} ━━━\n⚠️ 调用失败: {error_msg}")

        # 拼接所有结果
        separator = "\n\n"
        final_content = separator.join(all_results)

        # 发送完成状态
        status_emoji = "✅" if success_count == total_skills else "⚠️"
        self._send_sse_event({
            "status": "generating",
            "status_text": f"{status_emoji} API调用完成 ({success_count}/{total_skills}成功)"
        })
        await self.flush()

        # 流式发送结果
        chunk_size = 5
        for i in range(0, len(final_content), chunk_size):
            chunk = final_content[i:i+chunk_size]
            self._send_sse_event({"content": chunk, "employee_id": employee_id, "emp_name": emp_name})
            await self.flush()
            await asyncio.sleep(0.008)

        # 保存到数据库
        CollabMessageRepository.add_message(group_id, 'employee', employee_id, final_content)

        self._send_sse_event({"employee_id": employee_id}, done=True)
        await self.flush()
        self.finish()

    async def _stream_ai_response(self, group_id, employee_id, emp_info, question, trigger_msg_id):
        """Use the same evidence graph as private QA, without private watchlists."""
        sources=[]
        final=None
        try:
            from app.models.db import get_connection
            from app.models.model_engine import ModelEngineRepository
            with get_connection() as conn:
                rows=conn.execute("SELECT sender_type,content FROM collab_messages WHERE group_id=? AND id<? ORDER BY id DESC LIMIT 8",(group_id,trigger_msg_id)).fetchall()
            history=[{'role':'assistant' if row['sender_type']=='employee' else 'user','content':row['content']} for row in reversed(rows)]
            model={'api_key':emp_info['api_key'],'base_url':emp_info.get('base_url'),'model_name':emp_info.get('model_id_name') or emp_info.get('model_name')}
            persona={'name':emp_info['name'],'role':emp_info.get('role_desc',''),'skills':[{'name':s.get('name'),'description':s.get('description','')} for s in emp_info.get('skill_details',[])]}
            graph=build_news_graph(model)
            async with asyncio.timeout(150):
                async for mode,event in graph.astream({'question':question,'history':history,'persona':persona},stream_mode=['custom','updates']):
                    if mode=='custom':
                        if event.get('type')=='status':
                            self._send_sse_event({'status':event.get('stage','thinking'),'status_text':event['message']})
                        elif event.get('type')=='sources':
                            sources=event['sources']
                        elif event.get('type')=='content':
                            self._send_sse_event({'content':event['content'],'employee_id':employee_id,'emp_name':emp_info['name']})
                        await self.flush()
                    elif mode=='updates' and 'generate_answer' in event:
                        final=event['generate_answer']
            if not final:
                raise RuntimeError('问答未完成')
            answer=append_source_refs(final['answer'],sources)
            suffix=answer[len(final['answer']):]
            if suffix:
                self._send_sse_event({'content':suffix,'employee_id':employee_id,'emp_name':emp_info['name']})
                await self.flush()
            CollabMessageRepository.add_message(group_id,'employee',employee_id,answer,tokens_used=final['tokens'])
            if emp_info.get('model_engine_id'):
                ModelEngineRepository.add_tokens(emp_info['model_engine_id'],final['tokens'])
            self._send_sse_event({'employee_id':employee_id},done=True)
            await self.flush()
        except Exception:
            import logging
            logging.exception('Digital employee graph failed in group %s',group_id)
            if not self._finished:
                self._send_sse_event({'error':True,'content':'数字员工本次任务未完成，请检查模型连接后重试。'},done=True)
                await self.flush()
        finally:
            if not self._finished:self.finish()
