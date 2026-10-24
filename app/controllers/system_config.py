import tornado.web
from app.controllers.base import BaseHandler
from app.models.system_config import SystemConfigRepository
from app.models.db import get_connection, HAS_PYMYSQL, compact_all_sequences, sync_db_config_to_sqlite


class SystemConfigPageHandler(BaseHandler):
	@tornado.web.authenticated
	def get(self):
		db_config = {}
		with get_connection() as conn:
			for key in ['db_type', 'mysql_host', 'mysql_port', 'mysql_user', 'mysql_password', 'mysql_database']:
				row = conn.execute("SELECT config_value FROM system_configs WHERE config_key=?", (key,)).fetchone()
				if row:
					db_config[key] = row['config_value']
		if not db_config.get('db_type'):
			db_config['db_type'] = 'sqlite'
		self.render("system_config/list.html", title="系统设置", db_config=db_config, has_pymysql=HAS_PYMYSQL)


class SystemConfigApiHandler(BaseHandler):
	@tornado.web.authenticated
	def get(self):
		action = self.get_argument("action", "list")
		if action == "db_config":
			with get_connection() as conn:
				cfg = {}
				db_type_row = conn.execute(
					"SELECT config_value FROM system_configs WHERE config_key='db_type'"
				).fetchone()
				cfg['db_type'] = db_type_row['config_value'] if db_type_row else 'sqlite'
				for key in ['mysql_host', 'mysql_port', 'mysql_user', 'mysql_password', 'mysql_database']:
					row = conn.execute(
						"SELECT config_value FROM system_configs WHERE config_key=?", (key,)
					).fetchone()
					if row:
						cfg[key] = row['config_value']
			self.write({"code": 0, "data": cfg, "has_pymysql": HAS_PYMYSQL})
			return

		page = int(self.get_argument("page", 1))
		limit = int(self.get_argument("limit", 20))
		rows, total = SystemConfigRepository.get_list(page, limit)
		self.write({"code": 0, "msg": "", "count": total, "data": rows})

	@tornado.web.authenticated
	def post(self):
		action = self.get_argument("action", "")
		if action == "set":
			key = self.get_argument("config_key", "").strip()
			value = self.get_argument("config_value", "")
			description = self.get_argument("description", "")
			if not key:
				return self.write({"code": 1, "msg": "配置键不能为空"})
			SystemConfigRepository.set_config(key, value, description)
			self.write({"code": 0, "msg": "保存成功"})
		elif action == "delete":
			cfg_id = int(self.get_argument("id", 0))
			SystemConfigRepository.delete(cfg_id)
			self.write({"code": 0, "msg": "删除成功"})
		elif action == "batch_delete":
			ids_str = self.get_argument("ids", "")
			ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
			if SystemConfigRepository.delete_batch(ids):
				self.write({"code": 0, "msg": "批量删除成功"})
			else:
				self.write({"code": 1, "msg": "没有可删除的记录"})
		elif action == "save_db_config":
			db_type = self.get_argument("db_type", "sqlite")
			mysql_host = self.get_argument("mysql_host", "127.0.0.1")
			mysql_port = self.get_argument("mysql_port", "3306")
			mysql_user = self.get_argument("mysql_user", "root")
			mysql_password = self.get_argument("mysql_password", "")
			mysql_database = self.get_argument("mysql_database", "insight_agent")
			fields = [
				('db_type', db_type, "数据库类型"),
				('mysql_host', mysql_host, "MySQL主机"),
				('mysql_port', mysql_port, "MySQL端口"),
				('mysql_user', mysql_user, "MySQL用户"),
				('mysql_password', mysql_password, "MySQL密码"),
				('mysql_database', mysql_database, "MySQL数据库名"),
			]
			for key, value, desc in fields:
				SystemConfigRepository.set_config(key, value, f"数据库配置 - {desc}")
			# 始终同步写入 SQLite 文件，确保切回 SQLite 时配置可正确读取
			sync_db_config_to_sqlite(db_type, mysql_host, mysql_port, mysql_user, mysql_password, mysql_database)
			self.write({"code": 0, "msg": "数据库配置已保存，重启后生效"})
		elif action == "test_mysql":
			if not HAS_PYMYSQL:
				return self.write({"code": 1, "msg": "pymysql 未安装，请先执行: pip install pymysql"})
			try:
				import pymysql
				conn = pymysql.connect(
					host=self.get_argument("mysql_host", "127.0.0.1"),
					port=int(self.get_argument("mysql_port", 3306)),
					user=self.get_argument("mysql_user", "root"),
					password=self.get_argument("mysql_password", ""),
					database=self.get_argument("mysql_database", "insight_agent"),
					charset='utf8mb4'
				)
				conn.close()
				self.write({"code": 0, "msg": "MySQL 连接测试成功！"})
			except pymysql.err.OperationalError as e:
				code = e.args[0] if e.args else 0
				if code == 1045:
					self.write({"code": 1, "msg": "用户名或密码错误，请检查 MySQL 账号密码"})
				elif code == 1049:
					self.write({"code": 1, "msg": "数据库不存在，请先在 MySQL 中创建对应数据库"})
				elif code == 2003:
					self.write({"code": 1, "msg": "无法连接到 MySQL 服务器，请确认 MySQL 已启动且主机/端口正确"})
				else:
					self.write({"code": 1, "msg": f"MySQL 连接失败 (错误码 {code}): {e.args[1] if len(e.args)>1 else str(e)}"})
			except Exception as e:
				self.write({"code": 1, "msg": f"连接失败: {str(e)}"})
		elif action == "compact_sequences":
			try:
				results = compact_all_sequences()
				self.write({"code": 0, "msg": "自增序号压缩完成", "data": results})
			except Exception as e:
				self.write({"code": 1, "msg": f"压缩失败: {str(e)}"})
		else:
			self.write({"code": 1, "msg": "未知操作"})
