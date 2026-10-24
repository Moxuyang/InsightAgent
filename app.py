# 程序的主入口
# 承担服务器容器+程序作用
# 服务器容器：提供http容器服务，程序放置于该容器中运行
# 程序：本体-智能瞭望与智能问数系统 B/s架构
import os
import tornado.ioloop
import tornado.web
from tornado.httpserver import HTTPServer

# 引入auth - controller层
from app.controllers.auth import LoginHandler,LogoutHandler
from app.controllers.home import IndexHandler, DashboardHandler
from app.controllers.user import UserPageHandler, UserApiHandler
from app.controllers.menu import MenuPageHandler, MenuApiHandler
from app.controllers.role import RolePageHandler, RoleApiHandler
from app.controllers.model_engine import ModelEnginePageHandler, ModelEngineApiHandler, ModelTestApiHandler
from app.controllers.spy_source import SpySourcePageHandler, SpySourceApiHandler
from app.controllers.data_warehouse import DataWarehousePageHandler, DataWarehouseApiHandler
from app.controllers.spy import SpyPageHandler, SpyRunApiHandler, SpyCommitApiHandler
# 新增模块 controller层
from app.controllers.permission import PermissionPageHandler, PermissionApiHandler
from app.controllers.deep_collect import DeepCollectPageHandler, DeepCollectApiHandler, DeepCollectDataApiHandler, DeepCollectRunApiHandler, DeepCollectResultApiHandler, DeepCollectResultDetailHandler
from app.controllers.api_config import ApiConfigPageHandler, ApiConfigApiHandler
from app.controllers.digital_employee import DigitalEmployeePageHandler, DigitalEmployeeApiHandler
from app.controllers.skill import SkillPageHandler, SkillApiHandler, SkillAiGenerateHandler
from app.controllers.user_query import UserQueryPageHandler, UserQueryApiHandler
from app.controllers.system_config import SystemConfigPageHandler, SystemConfigApiHandler
from app.controllers.user_file import UserFilePageHandler, UserFileApiHandler
from app.controllers.data_screen import DataScreenHandler, UserDashboardHandler, DashboardChatApiHandler, DashboardChartApiHandler, DashboardUploadHandler
from app.controllers.register import RegisterHandler
from app.controllers.collaboration import CollabPageHandler, CollabChatPageHandler, CollabApiHandler, CollabChatApiHandler
from app.controllers.sentiment import SentimentPageHandler, SentimentApiHandler
from app.controllers.chat_session import ChatSessionPageHandler, ChatSessionApiHandler
from app.controllers.news_qa import NewsQaHandler
from app.controllers.export_handler import ExportPdfHandler
from app.controllers.data_analysis import DataAnalysisApiHandler, DataAnalysisPageHandler
# 引入db - model层
from app.models.db import init_db, get_connection
from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.models.menu import MenuRepository

def make_app():
	base_url = os.path.dirname(os.path.abspath(__file__))
	settings = dict(
		# 预留view 层的内容配置
		template_path=os.path.join(base_url,"app","templates"),
		static_path=os.path.join(base_url,"app","static"),
		cookie_secret="demo-cookie-secret-change-me",
		login_url="/auth/login",
		xsrf_cookies=True,
		debug=True,
		autoreload=True
	)
	return tornado.web.Application([
			(r"/",IndexHandler),
			(r"/dashboard", DashboardHandler),
			(r"/auth/login",LoginHandler),
			(r"/auth/logout",LogoutHandler),
			(r"/register", RegisterHandler),
			(r"/user/list", UserPageHandler),
			(r"/api/user", UserApiHandler),
			(r"/menu/list", MenuPageHandler),
			(r"/api/menu", MenuApiHandler),
			(r"/role/list", RolePageHandler),
			(r"/api/role", RoleApiHandler),
			(r"/model_engine/list", ModelEnginePageHandler),
			(r"/api/model_engine", ModelEngineApiHandler),
			(r"/api/model_engine/test", ModelTestApiHandler),
			# 瞭望数据源管理路由
			(r"/spy_source/list", SpySourcePageHandler),
			(r"/api/spy_source", SpySourceApiHandler),
			# 数据仓库路由
			(r"/data_warehouse/list", DataWarehousePageHandler),
			(r"/api/data_warehouse", DataWarehouseApiHandler),
			# 独立瞭望采集界面路由
			(r"/spy", SpyPageHandler),
			(r"/api/spy/run", SpyRunApiHandler),
			(r"/api/spy/commit", SpyCommitApiHandler),
			# ==== 新增模块路由 ====
			(r"/permission/list", PermissionPageHandler),
			(r"/api/permission", PermissionApiHandler),
		(r"/deep_collect/list", DeepCollectPageHandler),
		(r"/api/deep_collect", DeepCollectApiHandler),
		(r"/api/deep_collect/data", DeepCollectDataApiHandler),
		(r"/api/deep_collect/run", DeepCollectRunApiHandler),
		(r"/api/deep_collect/results", DeepCollectResultApiHandler),
		(r"/api/deep_collect/result_detail", DeepCollectResultDetailHandler),
			(r"/api_config/list", ApiConfigPageHandler),
			(r"/api/api_config", ApiConfigApiHandler),
			(r"/digital_employee/list", DigitalEmployeePageHandler),
			(r"/api/digital_employee", DigitalEmployeeApiHandler),
			(r"/skill/list", SkillPageHandler),
			(r"/api/skill", SkillApiHandler),
			(r"/api/skill/ai_generate", SkillAiGenerateHandler),
		(r"/user_query/list", UserQueryPageHandler),
		(r"/api/user_query", UserQueryApiHandler),
		(r"/system_config/list", SystemConfigPageHandler),
		(r"/api/system_config", SystemConfigApiHandler),
		(r"/user_file/list", UserFilePageHandler),
		(r"/api/user_file", UserFileApiHandler),
		(r"/data_screen", DataScreenHandler),
		(r"/user_dashboard", UserDashboardHandler),
		(r"/api/dashboard_chat", DashboardChatApiHandler),
		(r"/api/news_qa", NewsQaHandler),
		(r"/api/dashboard_charts", DashboardChartApiHandler),
		# ==== 协作沟通模块 ====
		(r"/collaboration/list", CollabPageHandler),
		(r"/collaboration/chat", CollabChatPageHandler),
		(r"/api/collaboration", CollabApiHandler),
		(r"/api/collaboration/chat", CollabChatApiHandler),
		# ==== 智能舆情分析 ====
		(r"/sentiment", SentimentPageHandler),
		(r"/api/sentiment", SentimentApiHandler),
		# ==== 会话管理 ====
		(r"/chat_session/list", ChatSessionPageHandler),
		(r"/api/chat_session", ChatSessionApiHandler),
		# ==== PDF导出 ====
		(r"/api/export/pdf", ExportPdfHandler),
		# ==== 数据分析 ====
		(r"/data_analysis", DataAnalysisPageHandler),
		(r"/api/data_analysis", DataAnalysisApiHandler),
		# ==== 文件上传（问数主页） ====
		(r"/api/dashboard/upload", DashboardUploadHandler),
		],
		**settings
	)

if __name__ == "__main__":
	# 启动服务之前,检查并初始化数据库表
	init_db()
	
	# 确保超管角色存在（系统运行必需）
	roles = RoleRepository.get_all_roles()
	super_role_id = None
	for r in roles:
		if r['code'] == 'super_admin':
			super_role_id = r['id']
			break
	if not super_role_id:
		super_role_id = RoleRepository.create_role("超级管理员", "super_admin", is_system=1)
	
	# 确保默认菜单存在（系统运行必需）
	menus = MenuRepository.get_all_menus()
	if not menus:
		sys_id = MenuRepository.create_menu("系统管理", "", "layui-icon-set", 0, 1)
		MenuRepository.create_menu("用户管理", "/user/list", "layui-icon-user", sys_id, 1)
		MenuRepository.create_menu("角色管理", "/role/list", "layui-icon-group", sys_id, 2)
		MenuRepository.create_menu("功能管理", "/menu/list", "layui-icon-app", sys_id, 3)
	
	# 确保默认管理员存在（系统运行必需）
	admin_user = UserRepository.get_user_by_username("admin")
	if not admin_user:
		UserRepository.create_user("admin", "admin888", super_role_id)
	else:
		with get_connection() as conn:
			conn.execute("INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)", (admin_user['id'], super_role_id))
	
	with get_connection() as conn:
		# 清理已废弃的菜单ID
		conn.execute("DELETE FROM role_menus WHERE menu_id IN (15)")
		conn.execute("DELETE FROM menus WHERE id IN (15)")
		
		# 插入系统必需的功能菜单
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (5, 0, '模型引擎', 'layui-icon-engine', '/model_engine/list', 5))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (6, 0, '瞭望管理', 'layui-icon-find-fill', '', 6))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (7, 6, '数据源管理', '', '/spy_source/list', 1))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (8, 6, '瞭望采集', '', '/spy', 2))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (9, 0, '数据仓库', 'layui-icon-table', '/data_warehouse/list', 7))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (10, 0, '权限管理', 'layui-icon-vercode', '/permission/list', 4))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (11, 0, '深度采集', 'layui-icon-survey', '/deep_collect/list', 8))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (12, 1, '接口管理', 'layui-icon-link', '/api_config/list', 3))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (13, 0, '数字员工', 'layui-icon-user', '/digital_employee/list', 10))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (14, 1, '技能管理', 'layui-icon-templeate-1', '/skill/list', 4))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (16, 1, '对话管理', 'layui-icon-notice', '/user_query/list', 5))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (17, 1, '用户文件管理', 'layui-icon-file', '/user_file/list', 6))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (18, 0, '数智大屏', 'layui-icon-chart-screen', '/data_screen', 14))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (19, 0, '系统设置', 'layui-icon-set', '/system_config/list', 15))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (20, 0, '问数主页', 'layui-icon-home', '/user_dashboard', 16))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (21, 0, '协作沟通', 'layui-icon-dialogue', '/collaboration/list', 9))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (22, 0, '智能舆情', 'layui-icon-chart', '/sentiment', 13))
		conn.execute("INSERT OR IGNORE INTO menus (id, parent_id, name, icon, url, order_num) VALUES (?, ?, ?, ?, ?, ?)", (23, 0, '会话管理', 'layui-icon-chat', '/chat_session/list', 12))
		
		# 给超管赋予所有菜单权限
		all_menu_ids = [r['id'] for r in conn.execute("SELECT id FROM menus").fetchall()]
		for mid in all_menu_ids:
			conn.execute("INSERT OR IGNORE INTO role_menus (role_id, menu_id) VALUES (?, ?)", (super_role_id, mid))
	
	# ===== 所有业务数据（模型、技能、业务数据、数据源等）由用户通过系统界面自行管理，不再注入任何虚拟种子数据 =====
	
	app = make_app()
	server = HTTPServer(app)
	server.bind(10086)
	server.start()

	try:
		print("====== Server 启动成功 ======== 端口：10086 ======", flush=True)
	except OSError:
		pass
	tornado.ioloop.IOLoop.current().start()
