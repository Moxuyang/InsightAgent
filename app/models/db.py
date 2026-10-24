# 数据库链接与建表 - 支持 SQLite / MySQL 双数据库切换
import os
import re
import sqlite3

# 获得项目根路径的方法
def _project_root():
	return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# 获得数据文件的路径
DB_PATH = os.path.join(_project_root(),"database","app.db")

# MySQL 可选依赖
try:
	import pymysql
	HAS_PYMYSQL = True
except ImportError:
	HAS_PYMYSQL = False

# ===== SQLite → MySQL 语法翻译 =====
def _mysql_translate(sql):
	"""将 SQLite 特有语法转换为 MySQL 兼容语法"""
	s = sql

	# ? → %s (参数占位符)
	s = s.replace('?', '%s')

	# AUTOINCREMENT → AUTO_INCREMENT
	s = re.sub(r'\bAUTOINCREMENT\b', 'AUTO_INCREMENT', s, flags=re.IGNORECASE)

	# datetime('now') → CURRENT_TIMESTAMP
	s = re.sub(r"datetime\('now'\)", 'CURRENT_TIMESTAMP', s, flags=re.IGNORECASE)

	# INSERT OR IGNORE / UPDATE OR IGNORE → MySQL 语法
	s = re.sub(r'(INSERT|UPDATE)\s+OR\s+IGNORE', r'\1 IGNORE', s, flags=re.IGNORECASE)

	# CREATE UNIQUE INDEX IF NOT EXISTS → 去掉 IF NOT EXISTS（MySQL 部分版本不支持）
	# 索引已存在时的错误 1061 由 execute() 的 OperationalError 捕获处理
	# TEXT 列上建索引的错误 1170 同样由 execute() 捕获处理
	s = re.sub(
		r'CREATE UNIQUE INDEX IF NOT EXISTS\s+',
		'CREATE UNIQUE INDEX ',
		s, flags=re.IGNORECASE
	)

	# TEXT NOT NULL UNIQUE → VARCHAR(255) NOT NULL UNIQUE (MySQL 不支持 TEXT 索引)
	# 仅对较短字段做此转换
	s = re.sub(r'(\w+)\s+TEXT\s+NOT\s+NULL\s+UNIQUE', r'\1 VARCHAR(255) NOT NULL UNIQUE', s, flags=re.IGNORECASE)

	# MySQL 不允许 TEXT/BLOB 列有默认值 (error 1101)
	# text default '' → text (去掉默认值)
	s = re.sub(r'(text|longtext|mediumtext|tinytext)\s+default\s+[^,)]+', r'\1', s, flags=re.IGNORECASE)

	# ON CONFLICT(...) DO UPDATE SET -> ON DUPLICATE KEY UPDATE
	s = re.sub(
		r'ON\s+CONFLICT\s*\([^)]+\)\s+DO\s+UPDATE\s+SET',
		'ON DUPLICATE KEY UPDATE',
		s, flags=re.IGNORECASE
	)
	# excluded.xxx -> VALUES(xxx)
	s = re.sub(r'excluded\.(\w+)', r'VALUES(\1)', s)

	return s

# ===== 数据库连接包装器 =====
class _SQLiteWrapper:
	def __init__(self, conn):
		self._conn = conn
		self.db_type = 'sqlite'
	def execute(self, sql, params=None):
		if params: return self._conn.execute(sql, params)
		return self._conn.execute(sql)
	def executemany(self, sql, seq_of_params):
		return self._conn.executemany(sql, seq_of_params)
	def commit(self): self._conn.commit()
	def rollback(self): self._conn.rollback()
	def close(self): self._conn.close()
	def __enter__(self): return self
	def __exit__(self, *a):
		self.commit(); self.close()
		return False

class _MySQLWrapper:
	def __init__(self, conn):
		self._conn = conn
		self.db_type = 'mysql'
	def execute(self, sql, params=None):
		cur = self._conn.cursor()
		s = _mysql_translate(sql)
		try:
			cur.execute(s, params)
		except pymysql.err.DatabaseError as e:
			# PRAGMA queries are SQLite-only, silently ignore on MySQL
			if 'PRAGMA' in sql.upper():
				return _EmptyCursor()
			# 1061: duplicate key (index already exists)
			# 1060: duplicate column (ALTER TABLE ADD COLUMN already exists)
			# 1050: table already exists (CREATE TABLE already exists)
			# 1101: TEXT/BLOB default value not allowed (MySQL strict mode)
			# 1170: TEXT/BLOB used in key without length
			if e.args[0] in (1061, 1060, 1050, 1101, 1170):
				return _EmptyCursor()
			raise
		return _MySQLCursor(cur)
	def executemany(self, sql, seq_of_params):
		cur = self._conn.cursor()
		s = _mysql_translate(sql)
		cur.executemany(s, seq_of_params)
		return _MySQLCursor(cur)
	def commit(self): self._conn.commit()
	def rollback(self): self._conn.rollback()
	def close(self): self._conn.close()
	def __enter__(self): return self
	def __exit__(self, *a):
		self.commit(); self.close()
		return False

class _MySQLCursor:
	def __init__(self, cur):
		self._cur = cur
		try:
			self.lastrowid = cur.lastrowid
			self.rowcount = cur.rowcount
		except Exception:
			self.lastrowid = 0
			self.rowcount = 0
	def fetchone(self):
		r = self._cur.fetchone()
		return _MySQLRow(self._cur.description, r) if r else None
	def fetchall(self):
		return [_MySQLRow(self._cur.description, r) for r in self._cur.fetchall()]
	def __iter__(self):
		for r in self._cur:
			yield _MySQLRow(self._cur.description, r)


class _EmptyCursor:
	"""用于异常恢复场景的空游标，不依赖底层 cursor 的执行结果"""
	lastrowid = 0
	rowcount = 0
	def fetchone(self): return None
	def fetchall(self): return []
	def __iter__(self): return iter([])

class _MySQLRow:
	# datetime 类型映射，供 _normalize 使用
	import datetime as _dt
	_DT_TYPES = (_dt.datetime, _dt.date)
	def __init__(self, desc, vals):
		self._keys = [d[0] for d in desc] if desc else []
		self._vals = [self._normalize(v) for v in vals] if vals else []
	@staticmethod
	def _normalize(v):
		"""将 datetime/date 转为 ISO 字符串，模拟 SQLite 行为"""
		if isinstance(v, _MySQLRow._DT_TYPES):
			return v.isoformat()
		return v
	def keys(self): return self._keys
	def __getitem__(self, k):
		if isinstance(k, int): return self._vals[k]
		return self._vals[self._keys.index(k)]
	def __iter__(self): return iter(self._vals)

def _get_db_config():
	"""从 system_configs 表读取数据库配置"""
	try:
		db_path = DB_PATH
		if not os.path.exists(db_path):
			return {'db_type': 'sqlite'}
		conn = sqlite3.connect(db_path)
		conn.row_factory = sqlite3.Row
		cfg = {}
		for key in ['db_type','mysql_host','mysql_port','mysql_user','mysql_password','mysql_database']:
			r = conn.execute("SELECT config_value FROM system_configs WHERE config_key=?", (key,)).fetchone()
			if r: cfg[key] = r['config_value']
		conn.close()
		return cfg
	except:
		return {'db_type': 'sqlite'}

def sync_db_config_to_sqlite(db_type, mysql_host, mysql_port, mysql_user, mysql_password, mysql_database):
	"""将数据库配置同步写入 SQLite 文件，确保切回 SQLite 时可正确读取"""
	try:
		db_path = DB_PATH
		os.makedirs(os.path.dirname(db_path), exist_ok=True)
		conn = sqlite3.connect(db_path)
		pairs = [
			('db_type', db_type, '数据库配置 - 数据库类型'),
			('mysql_host', mysql_host, '数据库配置 - MySQL主机'),
			('mysql_port', mysql_port, '数据库配置 - MySQL端口'),
			('mysql_user', mysql_user, '数据库配置 - MySQL用户'),
			('mysql_password', mysql_password, '数据库配置 - MySQL密码'),
			('mysql_database', mysql_database, '数据库配置 - MySQL数据库名'),
		]
		for key, value, desc in pairs:
			conn.execute(
				"INSERT OR REPLACE INTO system_configs (config_key, config_value, description, create_at, update_at) "
				"VALUES (?, ?, ?, datetime('now'), datetime('now'))",
				(key, value, desc)
			)
		conn.commit()
		conn.close()
	except Exception:
		pass  # 静默失败，不影响主流程

# 获得数据库连接
def get_connection():
	cfg = _get_db_config()
	db_type = cfg.get('db_type', 'sqlite')

	if db_type == 'mysql' and HAS_PYMYSQL:
		try:
			conn = pymysql.connect(
				host=cfg.get('mysql_host', '127.0.0.1'),
				port=int(cfg.get('mysql_port', 3306)),
				user=cfg.get('mysql_user', 'root'),
				password=cfg.get('mysql_password', ''),
				database=cfg.get('mysql_database', 'insight_agent'),
				charset='utf8mb4',
				cursorclass=pymysql.cursors.Cursor
			)
			return _MySQLWrapper(conn)
		except Exception:
			pass  # fallback to sqlite

	os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
	conn = sqlite3.connect(DB_PATH)
	conn.row_factory = sqlite3.Row
	return _SQLiteWrapper(conn)

# ===== 自增序号重置工具 =====
def reset_auto_increment(table_name: str):
	"""
	重置指定表的自增序号（SQLite: sqlite_sequence, MySQL: ALTER TABLE AUTO_INCREMENT）。
	仅在表完全为空时重置，避免 ID 冲突。
	"""
	with get_connection() as conn:
		count_row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table_name}").fetchone()
		if count_row and count_row['cnt'] == 0:
			if conn.db_type == 'sqlite':
				conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (table_name,))
			elif conn.db_type == 'mysql':
				conn.execute(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1")
		# 如果表非空，不做任何操作

def compact_sequence(table_name: str):
	"""
	将自增序号重置为当前最大 ID + 1（填补因删除产生的间隙）。
	适用于表非空但希望序号紧凑的场景。
	"""
	with get_connection() as conn:
		max_row = conn.execute(f"SELECT MAX(id) as m FROM {table_name}").fetchone()
		if max_row and max_row['m'] is not None:
			next_id = max_row['m'] + 1
			if conn.db_type == 'sqlite':
				conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (table_name,))
				conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table_name, next_id - 1))
			elif conn.db_type == 'mysql':
				conn.execute(f"ALTER TABLE {table_name} AUTO_INCREMENT = {next_id}")

def compact_all_sequences():
	"""批量压缩所有表的自增序号（仅 SQLite 数据库有效）"""
	with get_connection() as conn:
		if conn.db_type != 'sqlite':
			return "该功能仅支持 SQLite"
		tables = conn.execute("SELECT name FROM sqlite_sequence").fetchall()
		results = []
		for t in tables:
			table_name = t['name']
			try:
				max_row = conn.execute(f"SELECT MAX(id) as m FROM {table_name}").fetchone()
				if max_row and max_row['m'] is not None:
					conn.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (max_row['m'], table_name))
					results.append(f"{table_name}: 序号已压缩到 {max_row['m']}")
				else:
					conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (table_name,))
					results.append(f"{table_name}: 表为空，序号已重置")
			except:
				results.append(f"{table_name}: 操作失败（跳过）")
		return results

# 初始化数据库表
def init_db():
	with get_connection() as conn:
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS users(
				id integer PRIMARY KEY AUTOINCREMENT,
				username TEXT NOT NULL UNIQUE,
				password_hash TEXT NOT NULL,
				salt TEXT NOT NULL,
				create_at TEXT NOT NULL DEFAULT(datetime('now'))
			)
			"""
		)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS roles(
				id integer PRIMARY KEY AUTOINCREMENT,
				name TEXT NOT NULL UNIQUE,
				code TEXT NOT NULL UNIQUE,
				is_system integer DEFAULT 0,
				create_at TEXT NOT NULL DEFAULT(datetime('now'))
			)
			"""
		)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS menus(
				id integer PRIMARY KEY AUTOINCREMENT,
				parent_id integer DEFAULT 0,
				name TEXT NOT NULL,
				url TEXT,
				icon TEXT,
				order_num integer DEFAULT 0,
				create_at TEXT NOT NULL DEFAULT(datetime('now'))
			)
			"""
		)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS role_menus(
				role_id integer,
				menu_id integer,
				PRIMARY KEY (role_id, menu_id)
			)
			"""
		)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS user_roles(
				user_id integer,
				role_id integer,
				PRIMARY KEY (user_id, role_id)
			)
			"""
		)
		
		# 建立模型引擎表 (ai_models)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS ai_models(
				id integer primary key autoincrement,
				name varchar(100) not null,         -- 别名/展示名
				model_name varchar(100) not null,   -- API实际调用的模型名称 (如 deepseek-v3)
				api_key varchar(255) not null,
				base_url varchar(255) not null,
				is_default integer default 0,       -- 1为系统默认全局优先调用
				total_tokens integer default 0,     -- token消耗统计
				create_at datetime default current_timestamp
			)
			"""
		)

		# 建立瞭望数据源管理表 (spy_sources)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS spy_sources(
				id integer primary key autoincrement,
				name varchar(100) not null,          -- 来源名称，如"百度新闻"
				entry_url text not null,             -- 采集入口 URL 模板
				request_headers text not null,       -- JSON 格式存储的 Headers
				is_active integer default 1,         -- 是否启用
				create_at datetime default current_timestamp
			)
			"""
		)

		# 建立数据仓库表 (spy_data)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS spy_data(
				id integer primary key autoincrement,
				source_id integer not null,          -- 关联的 spy_sources.id
				keyword varchar(255) not null,       -- 采集时用的关键词
				title text not null,                 -- 抓取到的标题
				url text not null,                   -- 抓取到的目标链接
				summary text,                        -- 抓取到的摘要或正文
				create_at datetime default current_timestamp,
				update_at datetime
			)
			"""
		)

		# 历史版本兼容：老表没有 update_at 时补列
		try:
			conn.execute("ALTER TABLE spy_data ADD COLUMN update_at datetime")
		except sqlite3.OperationalError:
			pass

		# 防止重复入库：同一来源下 URL 唯一
		conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_spy_data_source_url ON spy_data(source_id, url)")

		# ===== 以下为新增业务模块表 =====

		# 深度采集任务表 (deep_collects)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS deep_collects(
				id integer primary key autoincrement,
				name varchar(200) not null,
				target_url text not null,
				collect_type varchar(50) default 'webpage',
				cron_expression varchar(100),
				is_active integer default 1,
				last_run_at datetime,
				create_at datetime default current_timestamp
			)
			"""
		)

		# 接口管理表 (api_configs)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS api_configs(
				id integer primary key autoincrement,
				name varchar(200) not null,
				api_url text not null,
				method varchar(10) default 'GET',
				headers text,
				params text,
				is_active integer default 1,
				create_at datetime default current_timestamp
			)
			"""
		)

		# 数字员工表 (digital_employees)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS digital_employees(
				id integer primary key autoincrement,
				name varchar(200) not null,
				role_desc text,
				model_engine_id integer,
				skill_ids text,
				is_active integer default 1,
				create_at datetime default current_timestamp
			)
			"""
		)

		# 技能管理表 (skills) - 新版：支持function_call/skill.md架构
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS skills(
				id integer primary key autoincrement,
				name varchar(200) not null,
				skill_type varchar(50) default 'function_call',
				category varchar(100) default 'tool',
				description text,
				parameters text,
				execute_code text,
				is_active integer default 1,
				create_at datetime default current_timestamp,
				api_url text default '',
				api_method varchar(10) default 'POST',
				api_headers text default '{}',
				api_body_template text default '',
				api_response_path text default ''
			)
			"""
		)
		
		# 兼容旧版：如果老表缺少列，自动补齐
		try:
			cols = conn.execute("PRAGMA table_info(skills)").fetchall()
			col_names = [c[1] for c in cols]
			_migrate = {
				'category': "varchar(100) default 'tool'",
				'description': 'text',
				'execute_code': 'text',
				'api_url': "text default ''",
				'api_method': "varchar(10) default 'POST'",
				'api_headers': "text default '{}'",
				'api_body_template': "text default ''",
				'api_response_path': "text default ''",
			}
			for col, col_def in _migrate.items():
				if col not in col_names:
					conn.execute(f"ALTER TABLE skills ADD COLUMN {col} {col_def}")
		except sqlite3.OperationalError:
			pass

		# 会话管理表 (chat_sessions)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS chat_sessions(
				id integer primary key autoincrement,
				user_id integer not null,
				title varchar(200) default '新对话',
				employee_id integer,
				is_active integer default 1,
				create_at datetime default current_timestamp,
				update_at datetime
			)
			"""
		)

		# 对话消息表 (chat_messages)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS chat_messages(
				id integer primary key autoincrement,
				session_id integer not null,
				role varchar(20) not null,
				content text not null,
				tokens_used integer default 0,
				create_at datetime default current_timestamp
			)
			"""
		)

		# 系统配置表 (system_configs)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS system_configs(
				id integer primary key autoincrement,
				config_key varchar(100) not null unique,
				config_value text,
				description varchar(255),
				create_at datetime default current_timestamp,
				update_at datetime
			)
			"""
		)

		# 用户文件表 (user_files)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS user_files(
				id integer primary key autoincrement,
				user_id integer not null,
				file_name varchar(255) not null,
				file_path text not null,
				file_type varchar(50),
				file_size integer,
				create_at datetime default current_timestamp
			)
			"""
		)

		# 用户问数记录表 (user_queries)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS user_queries(
				id integer primary key autoincrement,
				user_id integer not null,
				query_text text not null,
				response_text text,
				tokens_used integer default 0,
				create_at datetime default current_timestamp
			)
			"""
		)

		# 业务数据表 (business_data) —— AI问数分析的数据源
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS business_data(
				id integer primary key autoincrement,
				category varchar(100) not null,
				item_name varchar(200) not null,
				metric_value real,
				metric_date date,
				region varchar(50),
				remark text,
				create_at datetime default current_timestamp
			)
			"""
		)

		# ===== 协作沟通模块表 =====

		# 群组表 (collab_groups)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS collab_groups(
				id integer primary key autoincrement,
				name varchar(200) not null,
				description text,
				creator_id integer not null,
				is_active integer default 1,
				create_at datetime default current_timestamp
			)
			"""
		)

		# 群组成员表 (collab_group_members)
		# member_type: 'user' 或 'employee'
		# member_id: users.id 或 digital_employees.id
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS collab_group_members(
				id integer primary key autoincrement,
				group_id integer not null,
				member_type varchar(20) not null,
				member_id integer not null,
				role varchar(20) default 'member',
				join_at datetime default current_timestamp
			)
			"""
		)
		conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cgm_group_member ON collab_group_members(group_id, member_type, member_id)")

		# ===== 智能舆情分析模块表 =====
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS sentiment_reports(
				id integer primary key autoincrement,
				source_type varchar(50) not null,
				source_id integer,
				content text,
				risk_level varchar(20),
				keywords text,
				summary text,
				analysis_result text,
				analyzed_at datetime default current_timestamp
			)
			"""
		)

		# 群聊消息表 (collab_messages)
		# sender_type: 'user' 或 'employee'
		# sender_id: users.id 或 digital_employees.id
		# mentioned_id: 被@的数字员工ID (employee_id)，可为空
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS collab_messages(
				id integer primary key autoincrement,
				group_id integer not null,
				sender_type varchar(20) not null,
				sender_id integer not null,
				content text not null,
				mentioned_id integer,
				tokens_used integer default 0,
				create_at datetime default current_timestamp
			)
			"""
		)

		# 深度采集结果表 (deep_collect_results)
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS deep_collect_results(
				id integer primary key autoincrement,
				spy_data_id integer not null,
				task_id integer,
				title text not null,
				url text not null,
				full_content text,
				content_html text,
				images_json text,
				crawl_status varchar(20) default 'pending',
				error_msg text,
				crawl_at datetime,
				create_at datetime default current_timestamp
			)
			"""
		)
