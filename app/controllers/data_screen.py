"""数智大屏 - 可视化仪表盘展示页面 + 问数主页对话API"""
import os
import uuid
import tornado.web
from app.controllers.base import BaseHandler
from app.models.db import get_connection
from app.models.chat_session import ChatSessionRepository
from app.models.user_query import UserQueryRepository
from app.models.user_file import UserFileRepository


class DataScreenHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        stats = {}
        with get_connection() as conn:
            stats["user_count"] = conn.execute("SELECT COUNT(1) as cnt FROM users").fetchone()["cnt"]
            stats["role_count"] = conn.execute("SELECT COUNT(1) as cnt FROM roles").fetchone()["cnt"]
            stats["model_count"] = conn.execute("SELECT COUNT(1) as cnt FROM ai_models").fetchone()["cnt"]
            stats["spy_data_count"] = conn.execute("SELECT COUNT(1) as cnt FROM spy_data").fetchone()["cnt"]
            stats["session_count"] = conn.execute("SELECT COUNT(1) as cnt FROM chat_sessions").fetchone()["cnt"]
            stats["query_count"] = conn.execute("SELECT COUNT(1) as cnt FROM user_queries").fetchone()["cnt"]
            stats["today_queries"] = conn.execute(
                "SELECT COUNT(1) as cnt FROM user_queries WHERE date(create_at)=date('now')"
            ).fetchone()["cnt"]
        self.render("data_screen/list.html", title="数智大屏", stats=stats)


class UserDashboardHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.set_header('Cache-Control','no-store')
        user = self.current_user
        self.render("user_dashboard/list.html", title="问数主页", username=user.get("username") if user else "")


class DashboardChartApiHandler(BaseHandler):
    """数智大屏图表数据 API —— 问数趋势 & 模块使用分布"""

    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", None)

        if action == "recent_spy":
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT sd.id, sd.title, sd.create_at, ss.name as source_name "
                    "FROM spy_data sd LEFT JOIN spy_sources ss ON sd.source_id = ss.id "
                    "ORDER BY sd.id DESC LIMIT 20"
                ).fetchall()
                self.write({"code": 0, "data": [dict(r) for r in rows]})
            return

        with get_connection() as conn:
            # ------ 系统数据活跃度（每日瞭望采集量 + AI对话量） ------
            # 瞭望采集每日量
            spy_daily = conn.execute(
                "SELECT date(create_at) as day, COUNT(1) as cnt FROM spy_data "
                "GROUP BY date(create_at) ORDER BY day ASC LIMIT 60"
            ).fetchall()
            # 用户问数每日量
            query_daily = conn.execute(
                "SELECT date(create_at) as day, COUNT(1) as cnt FROM user_queries "
                "GROUP BY date(create_at) ORDER BY day ASC LIMIT 60"
            ).fetchall()

            # 合并两方日期
            all_days = set()
            spy_map = {}
            for r in spy_daily:
                all_days.add(r["day"])
                spy_map[r["day"]] = r["cnt"]
            query_map = {}
            for r in query_daily:
                all_days.add(r["day"])
                query_map[r["day"]] = r["cnt"]
            days_sorted = sorted(all_days)

            spy_series = [spy_map.get(d, 0) for d in days_sorted]
            query_series = [query_map.get(d, 0) for d in days_sorted]
            day_labels = [d[5:] + "日" for d in days_sorted]

            trend = {
                "months": day_labels,
                "user": spy_series,
                "sales": query_series,
                "satisfaction": [],
                "series_names": ["瞭望采集量", "AI对话量"],
            }

            # ------ 瞭望数据源分布（真实数据） ------
            source_dist_rows = conn.execute(
                "SELECT ss.name, COUNT(1) as cnt FROM spy_data sd "
                "LEFT JOIN spy_sources ss ON sd.source_id = ss.id "
                "GROUP BY sd.source_id ORDER BY cnt DESC"
            ).fetchall()
            distribution_region = [{"name": r["name"] or "未知来源", "value": r["cnt"]} for r in source_dist_rows]

            # ------ 主题分类分布（从sentiment_reports中提取keywords统计） ------
            topic_rows = conn.execute(
                "SELECT keywords FROM sentiment_reports WHERE keywords IS NOT NULL AND keywords != ''"
            ).fetchall()
            topic_count = {}
            for r in topic_rows:
                for kw in (r["keywords"] or "").split(","):
                    kw = kw.strip()
                    if kw and len(kw) <= 10:
                        topic_count[kw] = topic_count.get(kw, 0) + 1
            # 取前10个热点主题
            distribution_product = [
                {"name": k, "value": v}
                for k, v in sorted(topic_count.items(), key=lambda x: -x[1])[:10]
            ]
            if not distribution_product:
                distribution_product = [{"name": "暂无数据", "value": 1}]

            distribution = {
                "category": distribution_product,
                "region": distribution_region,
                "product": distribution_product,
            }

            # ------ 词云数据（从spy_data标题中提取真实热词） ------
            title_rows = conn.execute(
                "SELECT title FROM spy_data WHERE title IS NOT NULL ORDER BY id DESC LIMIT 300"
            ).fetchall()
            word_freq = {}
            import re as _re
            for r in title_rows:
                title = r["title"] or ""
                # 用正则提取中文词（2-4字词组）
                words = _re.findall(r'[\u4e00-\u9fff]{2,4}', title)
                for w in words:
                    # 过滤无意义停用词
                    if w in ("一个", "可以", "这个", "我们", "他们", "这些", "那些",
                              "不是", "已经", "还是", "什么", "没有", "自己", "知道",
                              "因为", "所以", "如果", "虽然", "但是", "而且", "或者",
                              "最新", "新闻", "今天", "近日", "目前", "相关", "关于"):
                        continue
                    word_freq[w] = word_freq.get(w, 0) + 1
            wordcloud_data = [
                {"name": k, "value": v}
                for k, v in sorted(word_freq.items(), key=lambda x: -x[1])[:50]
            ]
            if not wordcloud_data:
                wordcloud_data = [{"name": "暂无数据", "value": 1}]

            # ------ 3D地球热点数据（根据spy_data真实新闻提取国家/地区） ------
            # 国家/地区 → 经纬度映射（首都/主要城市）
            country_coords = {
                "中国": [116.4, 39.9], "北京": [116.4, 39.9], "上海": [121.5, 31.2],
                "深圳": [114.1, 22.5], "广东": [113.3, 23.1],
                "美国": [-95.7, 37.1], "美": [-95.7, 37.1], "硅谷": [-122.0, 37.4],
                "日本": [139.8, 35.7], "东京": [139.8, 35.7],
                "韩国": [127.0, 37.6], "首尔": [127.0, 37.6],
                "英国": [-0.1, 51.5], "伦敦": [-0.1, 51.5],
                "德国": [13.4, 52.5], "柏林": [13.4, 52.5],
                "法国": [2.4, 48.9], "巴黎": [2.4, 48.9],
                "俄罗斯": [37.6, 55.8], "莫斯科": [37.6, 55.8],
                "印度": [77.2, 28.6], "新德里": [77.2, 28.6],
                "巴西": [-47.9, -15.8],
                "加拿大": [-75.7, 45.4],
                "澳大利亚": [149.1, -35.3], "澳洲": [149.1, -35.3],
                "新加坡": [103.8, 1.35],
                "马来西亚": [101.7, 3.1],
                "泰国": [100.5, 13.8],
                "越南": [105.8, 21.0],
                "印尼": [106.8, -6.2], "印度尼西亚": [106.8, -6.2],
                "菲律宾": [121.0, 14.6],
                "阿联酋": [54.4, 24.5],
                "沙特": [46.7, 24.6],
                "以色列": [35.2, 31.8],
                "土耳其": [32.9, 39.9],
                "意大利": [12.5, 41.9],
                "西班牙": [-3.7, 40.4],
                "荷兰": [4.9, 52.4],
                "瑞士": [7.4, 46.9],
                "瑞典": [18.1, 59.3],
                "欧盟": [4.4, 50.8],
                "台湾": [121.0, 25.0],
                "香港": [114.2, 22.3],
                "澳门": [113.5, 22.2],
                "墨西哥": [-99.1, 19.4],
                "阿根廷": [-58.4, -34.6],
                "南非": [28.2, -26.2],
                "尼日利亚": [7.5, 9.0],
                "埃及": [31.2, 30.0],
                "伊朗": [51.4, 35.7],
                "巴基斯坦": [73.1, 33.7],
                "孟加拉": [90.4, 23.8],
                "乌克兰": [30.5, 50.4],
                "波兰": [21.0, 52.2],
            }

            # 从spy_data中提取国家/地区提及
            spy_news = conn.execute(
                "SELECT title, summary FROM spy_data WHERE title IS NOT NULL ORDER BY id DESC LIMIT 500"
            ).fetchall()

            country_counts = {}
            for row in spy_news:
                title = (row["title"] or "")
                summary = (row["summary"] or "")
                text = title + " " + summary
                for country in country_coords:
                    if country in text:
                        country_counts[country] = country_counts.get(country, 0) + 1

            # 生成地球节点数据
            globe_points = []
            processed = set()
            for country, cnt in sorted(country_counts.items(), key=lambda x: -x[1]):
                coord = country_coords.get(country)
                if not coord:
                    continue
                # 合并重复坐标（取最大值）
                coord_key = f"{coord[0]:.1f},{coord[1]:.1f}"
                if coord_key in processed:
                    continue
                processed.add(coord_key)
                height = max(200, cnt * 50 + 100)
                globe_points.append({
                    "name": country,
                    "value": [coord[0], coord[1], height],
                    "count": cnt,
                    "total_value": cnt,
                })

            # 如果数据库中没有数据，返回空列表（不再使用虚拟回退数据）

        self.write({"code": 0, "data": {
            "trend": trend,
            "distribution": distribution,
            "wordcloud": wordcloud_data,
            "globe_points": globe_points,
        }})


class DashboardChatApiHandler(BaseHandler):
    """问数主页专用的对话 API —— 加载历史 / 保存消息 / 获取业务数据上下文"""

    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "history")

        if action == "sessions":
            # 返回当前用户的所有会话列表
            user = self.current_user
            user_id = user['id'] if user else 0
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, title, update_at, is_active FROM chat_sessions WHERE user_id=? ORDER BY update_at DESC",
                    (user_id,)
                ).fetchall()
                sessions = []
                for r in rows:
                    d = dict(r)
                    d['updated_at'] = str(d.get('update_at', ''))
                    sessions.append(d)
            self.write({"code": 0, "data": sessions})
            return

        if action == "context":
            # 返回完整项目上下文，让 AI 深度了解整个系统的数据库结构、实时数据和所有功能模块
            with get_connection() as conn:
                lines = []

                # ========== 一、系统概述 ==========
                lines.append("""===【系统概述】===
你正在运行的系统是「InsightAgent 智能瞭望与智能问数系统」。
这是一个集数据采集、AI智能分析、3D数据可视化大屏、协作沟通于一体的企业级智能平台。
核心价值：让管理者在一个界面中完成「监测→分析→决策」的闭环。
技术栈：Python Tornado + SQLite/MySQL + Layui + ECharts 3D
运行端口：10086

===【系统模块架构】===
1. 用户与权限：用户管理、角色管理、权限管理（RBAC模型）
2. 模型引擎：管理多个AI大模型配置（API Key、Base URL），支持设置默认模型
3. 瞭望系统：数据源管理、瞭望采集（爬虫自动抓取新闻）、数据仓库（采集结果存储）
4. 数据采集扩展：深度采集任务（定时爬取）、接口管理（API接入）
5. 问数对话：AI智能问答、会话管理、对话记录、文件上传
6. 数字员工：可配置的AI代理，绑定技能和模型，参与群聊协作
7. 技能管理：function_call/skill.md架构的技能插件系统（真实API调用）
8. 协作沟通：群组聊天，支持@数字员工让AI参与讨论
9. 智能舆情：情感分析报告、关键词提取、风险评级
10. 数智大屏：3D地球热点分布、趋势图、饼图、词云、排行榜
11. 系统设置：数据库配置、全局参数管理

""")

                # ========== 二、实时数据总览 ==========
                total_users = conn.execute("SELECT COUNT(1) as cnt FROM users").fetchone()["cnt"]
                total_roles = conn.execute("SELECT COUNT(1) as cnt FROM roles").fetchone()["cnt"]
                total_models = conn.execute("SELECT COUNT(1) as cnt FROM ai_models").fetchone()["cnt"]
                total_spy_sources = conn.execute("SELECT COUNT(1) as cnt FROM spy_sources").fetchone()["cnt"]
                total_spy_data = conn.execute("SELECT COUNT(1) as cnt FROM spy_data").fetchone()["cnt"]
                total_sessions = conn.execute("SELECT COUNT(1) as cnt FROM chat_sessions").fetchone()["cnt"]
                total_queries = conn.execute("SELECT COUNT(1) as cnt FROM user_queries").fetchone()["cnt"]
                total_employees = conn.execute("SELECT COUNT(1) as cnt FROM digital_employees").fetchone()["cnt"]
                total_skills = conn.execute("SELECT COUNT(1) as cnt FROM skills").fetchone()["cnt"]
                total_groups = conn.execute("SELECT COUNT(1) as cnt FROM collab_groups").fetchone()["cnt"]
                total_sentiment = conn.execute("SELECT COUNT(1) as cnt FROM sentiment_reports").fetchone()["cnt"]
                today_queries = conn.execute(
                    "SELECT COUNT(1) as cnt FROM user_queries WHERE date(create_at)=date('now')"
                ).fetchone()["cnt"]

                lines.append(f"""===【实时数据总览】===
系统用户数：{total_users} 人
角色数：{total_roles} 个
AI模型引擎：{total_models} 个
瞭望数据源：{total_spy_sources} 个
累计采集新闻：{total_spy_data} 条
对话会话数：{total_sessions} 个
累计提问数：{total_queries} 次（今日：{today_queries} 次）
数字员工：{total_employees} 人
技能插件：{total_skills} 个
协作群组：{total_groups} 个
舆情报告：{total_sentiment} 份

""")

                # ========== 三、全部数据库表结构 ==========
                lines.append("""===【数据库表结构】===
以下是系统中所有数据表及其字段定义。你可以针对这些表回答用户关于数据查询、统计、分析的问题。

1. users（用户表）
   - id (主键), username (用户名), password_hash (密码哈希), salt (盐), create_at (创建时间)

2. roles（角色表）
   - id (主键), name (角色名), code (角色编码如super_admin), is_system (是否系统角色), create_at

3. menus（菜单表）
   - id (主键), parent_id (父菜单ID), name (菜单名), url (路由), icon (图标), order_num (排序), create_at

4. user_roles（用户-角色关联）
   - user_id, role_id (联合主键)

5. role_menus（角色-菜单关联）
   - role_id, menu_id (联合主键)

6. ai_models（AI模型引擎表）
   - id (主键), name (别名), model_name (API模型名), api_key, base_url, is_default (是否默认), total_tokens (累计消耗), create_at

7. spy_sources（瞭望数据源表）
   - id (主键), name (来源名称如"百度新闻"), entry_url (采集URL模板), request_headers (JSON Headers), is_active, create_at

8. spy_data（瞭望采集数据仓库）
   - id (主键), source_id (关联spy_sources.id), keyword (采集关键词), title (标题), url (源链接), summary (摘要), create_at, update_at

9. deep_collects（深度采集任务表）
   - id (主键), name (任务名), target_url (目标URL), collect_type (采集类型), cron_expression (定时规则), is_active, last_run_at, create_at

10. api_configs（接口管理表）
    - id (主键), name (接口名), api_url, method (GET/POST), headers, params, is_active, create_at

11. digital_employees（数字员工表）
    - id (主键), name (员工名), role_desc (角色描述), model_engine_id (关联ai_models.id), skill_ids (绑定的技能ID列表), is_active, create_at

12. skills（技能管理表）
    - id (主键), name (技能名), skill_type (类型如function_call/skill.md), category (分类如tool/data_analysis), description (描述), parameters (参数定义), execute_code (执行代码/提示词), is_active, create_at, api_url, api_method, api_headers, api_body_template, api_response_path

13. chat_sessions（对话会话表）
    - id (主键), user_id (关联users.id), title (会话标题), employee_id (关联digital_employees.id), is_active, create_at, update_at

14. chat_messages（对话消息表）
    - id (主键), session_id (关联chat_sessions.id), role (user/assistant), content (消息内容), tokens_used (消耗Token数), create_at

15. system_configs（系统配置表）
    - id (主键), config_key (配置键), config_value (配置值), description (描述), create_at, update_at

16. user_files（用户文件表）
    - id (主键), user_id, file_name, file_path, file_type, file_size, create_at

17. user_queries（用户问数记录表）
    - id (主键), user_id, query_text (问题), response_text (AI回答), tokens_used, create_at

18. business_data（业务数据表 - AI分析用）
    - id (主键), category (分类), item_name (指标名), metric_value (数值), metric_date (日期), region (区域), remark (备注), create_at

19. collab_groups（协作群组表）
    - id (主键), name (群名), description (描述), creator_id, is_active, create_at

20. collab_group_members（群组成员表）
    - id (主键), group_id, member_type (user/employee), member_id, role (角色), join_at

21. collab_messages（群聊消息表）
    - id (主键), group_id, sender_type (user/employee), sender_id, content (消息), mentioned_id (被@的员工ID), tokens_used, create_at

22. sentiment_reports（舆情分析报告表）
    - id (主键), source_type (来源类型), source_id, content (内容), risk_level (风险等级), keywords (关键词), summary (摘要), analysis_result (分析结果), analyzed_at

""")

                # ========== 四、表间关系 ==========
                lines.append("""===【关键表间关系】===
- users.id → user_roles.user_id → roles.id（用户通过角色获取权限）
- roles.id → role_menus.role_id → menus.id（角色通过菜单获取访问权限）
- spy_data.source_id → spy_sources.id（采集数据关联数据源）
- chat_sessions.user_id → users.id（会话归属用户）
- chat_messages.session_id → chat_sessions.id（消息归属会话）
- digital_employees.model_engine_id → ai_models.id（数字员工使用AI模型）
- digital_employees.skill_ids → skills.id（数字员工绑定技能）
- collab_groups.id → collab_group_members.group_id → member_id（群组成员关系）
- collab_messages.group_id → collab_groups.id（消息归属群组）
- user_queries.user_id → users.id（提问归属用户）
- user_files.user_id → users.id（文件归属用户）
- sentiment_reports.source_id → spy_data.id（舆情关联采集源）

""")

                # ========== 五、核心任务指引 ==========
                lines.append("""===【你的核心任务】===
你是InsightAgent的数据分析助手，你的回答将直接展示给用户。
你收到的上下文已经包含了系统的真实数据（新闻、舆情、业务指标、会话记录等）。

回答原则：
- 直接分析数据，用具体数字和真实内容说话
- 列出数据时引用实际条目，不要说"可能"、"应该"
- 不要输出SQL代码，这句话是禁止的
- 如果上下文中有数据就充分使用，没有的才说明暂无
- 用清晰的结构化文本呈现分析结果（标题、列表、分类对比等）
- 保持简洁、准确、可操作

""")

                # ========== 六、AI模型和数字员工列表 ==========
                models = conn.execute("SELECT id, name, model_name, is_default, total_tokens FROM ai_models WHERE 1=1 ORDER BY id").fetchall()
                if models:
                    lines.append("===【当前配置的AI模型】===")
                    for m in models:
                        default_mark = " [默认]" if m["is_default"] else ""
                        lines.append(f"  - {m['name']} (模型:{m['model_name']}){default_mark}，累计消耗Token: {m['total_tokens']}")
                    lines.append("")

                employees = conn.execute("SELECT id, name, role_desc FROM digital_employees WHERE is_active=1").fetchall()
                if employees:
                    lines.append("===【活跃的数字员工】===")
                    for e in employees:
                        desc = (e["role_desc"] or "未设定")[:60]
                        lines.append(f"  - {e['name']}：{desc}")

                skills_list = conn.execute("SELECT id, name, skill_type, category, description FROM skills WHERE is_active=1").fetchall()
                if skills_list:
                    lines.append("\n===【已启用的技能插件】===")
                    for s in skills_list:
                        desc = (s["description"] or "无描述")[:80]
                        lines.append(f"  - {s['name']} (类型:{s['skill_type']}, 分类:{s['category']})：{desc}")

                sources = conn.execute("SELECT id, name, is_active FROM spy_sources ORDER BY id").fetchall()
                if sources:
                    lines.append("\n===【瞭望数据源列表】===")
                    for src in sources:
                        status = "启用" if src["is_active"] else "停用"
                        lines.append(f"  - {src['name']} [{status}]")

                lines.append("")

                # ========== 七、业务数据详情 ==========
                biz_rows = conn.execute(
                    "SELECT category, item_name, metric_value, metric_date, region, remark FROM business_data ORDER BY category, metric_date"
                ).fetchall()
                if biz_rows:
                    lines.append("===【业务数据详情】===")
                    cur_cat = ""
                    for r in biz_rows:
                        cat = r["category"]
                        if cat != cur_cat:
                            cur_cat = cat
                            cat_names = {"user_metrics": "用户数据", "sales": "销售数据", "product": "产品数据", "customer": "客户满意度", "system": "系统运营数据"}
                            lines.append(f"\n【{cat_names.get(cat, cat)}】")
                        date_str = f" ({r['metric_date']})" if r["metric_date"] else ""
                        region_str = f" [{r['region']}]" if r["region"] else ""
                        remark_str = f" —— {r['remark']}" if r["remark"] else ""
                        lines.append(f"  - {r['item_name']}{date_str}{region_str}: {r['metric_value']}{remark_str}")
                    lines.append("")

                # ========== 八、新闻数据仓库实际数据（REAL DATA - 直接使用） ==========
                news_rows = conn.execute(
                    "SELECT s.name as source_name, d.keyword, d.title, d.summary, d.url, d.create_at "
                    "FROM spy_data d LEFT JOIN spy_sources s ON d.source_id = s.id "
                    "ORDER BY d.create_at DESC LIMIT 30"
                ).fetchall()
                if news_rows:
                    lines.append("===【新闻数据仓库 - 最近30条真实数据（直接用于回答）】===")
                    for i, r in enumerate(news_rows, 1):
                        src = r["source_name"] or "未知来源"
                        kw = r["keyword"] or ""
                        title = r["title"] or "无标题"
                        summary = (r["summary"] or "")[:200]
                        url = r["url"] or ""
                        date_str = r["create_at"] or ""
                        lines.append(f"  [{i}] {title}")
                        lines.append(f"      来源:{src} | 关键词:{kw} | 时间:{date_str}")
                        if summary:
                            lines.append(f"      摘要:{summary}")
                        if url:
                            lines.append(f"      链接:{url}")
                    lines.append("")

                # ========== 九、舆情报告实际数据（REAL DATA - 直接使用） ==========
                sentiment_rows = conn.execute(
                    "SELECT source_type, content, risk_level, keywords, summary, analysis_result, analyzed_at "
                    "FROM sentiment_reports ORDER BY analyzed_at DESC LIMIT 15"
                ).fetchall()
                if sentiment_rows:
                    lines.append("===【舆情报告 - 最近15条真实数据（直接用于回答）】===")
                    for i, r in enumerate(sentiment_rows, 1):
                        risk = r["risk_level"] or "未评级"
                        kw = r["keywords"] or ""
                        content_preview = (r["content"] or "")[:150]
                        summary = (r["summary"] or "")[:150]
                        analysis = (r["analysis_result"] or "")[:200]
                        date_str = r["analyzed_at"] or ""
                        lines.append(f"  [{i}] 风险等级:{risk} | 关键词:{kw} | 时间:{date_str}")
                        if content_preview:
                            lines.append(f"      内容:{content_preview}")
                        if summary:
                            lines.append(f"      摘要:{summary}")
                        if analysis:
                            lines.append(f"      分析结果:{analysis}")
                    lines.append("")

                # ========== 十、最近活跃会话摘要 ==========
                session_stats = conn.execute(
                    "SELECT cs.id, cs.title, cs.create_at, "
                    "(SELECT COUNT(1) FROM chat_messages cm WHERE cm.session_id=cs.id) as msg_count "
                    "FROM chat_sessions cs WHERE cs.is_active=1 ORDER BY cs.update_at DESC LIMIT 10"
                ).fetchall()
                if session_stats:
                    lines.append("===【最近活跃会话】===")
                    for s in session_stats:
                        title = s["title"] or "未命名会话"
                        lines.append(f"  - {title} (消息数:{s['msg_count']}) - {s['create_at']}")
                    lines.append("")

                # ========== 核心指令 ==========
                lines.append("""===【重要指令：你必须基于真实数据回答】===
1. 上面的新闻数据、舆情报告、业务数据全部来自数据库的真实记录
2. 直接引用这些数据回答用户，用具体数字和内容说话
3. 不要输出SQL代码，不要说"可以执行以下查询"
4. 用户问新闻 → 直接列出上面真实新闻的标题和摘要
5. 用户问舆情 → 直接用上面的舆情报告数据
6. 用户问趋势/统计 → 基于上面的真实数据进行归纳分析
7. 只有上面完全没有的数据，才告诉用户目前缺少该数据
""")

                context = "\n".join(lines)
            self.write({"code": 0, "data": {"context": context}})
            return

        if action != "history":
            self.write({"code": 1, "msg": "未知操作"})
            return

        user = self.current_user
        user_id = user['id'] if user else 0
        session_id_arg = self.get_argument("session_id", None)

        with get_connection() as conn:
            if session_id_arg:
                # 加载指定会话的历史消息
                session = conn.execute(
                    "SELECT * FROM chat_sessions WHERE id=? AND user_id=?",
                    (int(session_id_arg), user_id)
                ).fetchone()
                if not session:
                    self.write({"code": 0, "data": {"session": None, "messages": []}})
                    return
                session_dict = dict(session)
                messages = conn.execute(
                    "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id ASC",
                    (int(session_id_arg),)
                ).fetchall()
                self.write({"code": 0, "data": {
                    "session": session_dict,
                    "messages": [dict(m) for m in messages]
                }})
            else:
                # 默认加载最近活跃会话
                session = conn.execute(
                    "SELECT * FROM chat_sessions WHERE user_id=? AND is_active=1 ORDER BY update_at DESC LIMIT 1",
                    (user_id,)
                ).fetchone()
                if not session:
                    self.write({"code": 0, "data": {"session": None, "messages": []}})
                    return
                session_dict = dict(session)
                messages = conn.execute(
                    "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id ASC",
                    (session_dict['id'],)
                ).fetchall()
                self.write({"code": 0, "data": {
                    "session": session_dict,
                    "messages": [dict(m) for m in messages]
                }})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        user = self.current_user
        user_id = user['id'] if user else 0

        if action == "delete_session":
            session_id = int(self.get_argument("session_id", 0))
            if not session_id:
                self.write({"code": 1, "msg": "session_id 必填"})
                return
            # 验证会话属于当前用户
            with get_connection() as conn:
                session = conn.execute(
                    "SELECT id FROM chat_sessions WHERE id=? AND user_id=?",
                    (session_id, user_id)
                ).fetchone()
                if not session:
                    self.write({"code": 1, "msg": "会话不存在或无权操作"})
                    return
            ChatSessionRepository.delete(session_id)
            self.write({"code": 0, "msg": "删除成功"})

        elif action == "save_user_msg":
            content = self.get_argument("content", "")
            title = content[:30] + ("..." if len(content) > 30 else "")
            session_id = int(self.get_argument("session_id", 0))

            if not session_id:
                session_id = ChatSessionRepository.create(user_id, title)
            ChatSessionRepository.add_message(session_id, "user", content)
            self.write({"code": 0, "session_id": session_id})

        elif action == "save_assistant_msg":
            session_id = int(self.get_argument("session_id", 0))
            content = self.get_argument("content", "")
            tokens_used = int(self.get_argument("tokens_used", 0))
            if not session_id:
                self.write({"code": 1, "msg": "session_id 必填"})
                return
            ChatSessionRepository.add_message(session_id, "assistant", content, tokens_used)

            # 同步写入 user_queries 表，使"对话管理"页面能看到记录
            with get_connection() as conn:
                last_user = conn.execute(
                    "SELECT content FROM chat_messages WHERE session_id=? AND role='user' ORDER BY id DESC LIMIT 1",
                    (session_id,)
                ).fetchone()
                if last_user:
                    UserQueryRepository.create(user_id, last_user["content"], content, tokens_used)

            self.write({"code": 0, "msg": "saved"})

        else:
            self.write({"code": 1, "msg": "未知操作"})


class DashboardUploadHandler(BaseHandler):
    """问数主页文件上传 API"""
    def check_xsrf_cookie(self):
        """手动校验 xsrf，用 JSON 返回错误而非 403 页"""
        try:
            super().check_xsrf_cookie()
        except tornado.web.HTTPError as e:
            self.set_status(e.status_code)
            self.write({"code": 1, "msg": "安全校验失败，请刷新页面后重试"})
            self.finish()
            return False
        return True

    def post(self):
        # 手动校验 xsrf（不抛异常，返回 JSON）
        if not self.check_xsrf_cookie():
            return

        # 手动校验登录态（不用 @authenticated 避免 302 跳转）
        user = self.current_user
        if not user:
            self.write({"code": 1, "msg": "请先登录"})
            return
        user_id = user.get('id', 0)
        if not user_id:
            self.write({"code": 1, "msg": "请先登录"})
            return

        file_info = self.request.files.get('file', None)
        if not file_info:
            self.write({"code": 1, "msg": "未选择文件"})
            return

        f = file_info[0]
        original_name = f['filename']
        body = f['body']

        if not original_name:
            self.write({"code": 1, "msg": "文件名为空"})
            return

        # 限制文件大小 (50MB)
        max_size = 50 * 1024 * 1024
        if len(body) > max_size:
            self.write({"code": 1, "msg": "文件过大，最大支持50MB"})
            return

        # 生成唯一文件名，防止冲突
        ext = os.path.splitext(original_name)[1]
        safe_name = uuid.uuid4().hex + ext

        # 上传目录
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        upload_dir = os.path.join(base_dir, 'uploads')
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, safe_name)
        with open(file_path, 'wb') as fp:
            fp.write(body)

        # 获取文件类型
        file_type = ext.lstrip('.').lower() if ext else 'unknown'

        # 存储记录
        try:
            file_id = UserFileRepository.create(
                user_id=user_id,
                file_name=original_name,
                file_path='uploads/' + safe_name,
                file_type=file_type,
                file_size=len(body)
            )
        except Exception as e:
            self.write({"code": 1, "msg": f"存储记录失败: {str(e)}"})
            return

        self.write({
            "code": 0,
            "msg": "上传成功",
            "data": {
                "id": file_id,
                "file_name": original_name,
                "file_type": file_type,
                "file_size": len(body),
                "file_path": 'uploads/' + safe_name
            }
        })
