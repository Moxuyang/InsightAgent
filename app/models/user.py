import hashlib
import secrets
import sqlite3

from app.models.db import get_connection, compact_sequence

# 密码加密方法
def _hash_password(password:str,salt:bytes) -> str:
	dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
	return dk.hex()

# 用户对象类
class UserRepository:
	# 创建用户方法
	@staticmethod
	def create_user(username:str,password:str, role_id:int=None) -> bool:
		salt = secrets.token_bytes(16)
		password_hash = _hash_password(password,salt)

		try:
			with get_connection() as conn:
				cursor = conn.execute("insert into users(username,password_hash,salt) values(?,?,?)",(username,password_hash,salt.hex()),)
				user_id = cursor.lastrowid
				if role_id:
					conn.execute("INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)", (user_id, role_id))
			return True
		except sqlite3.IntegrityError:
			return False

	# 通过用户名检索用户信息的方法
	@staticmethod
	def get_user_by_username(username:str):
		with get_connection() as conn:
			row = conn.execute("""
				SELECT u.id, u.username, u.password_hash, u.salt, ur.role_id
				FROM users u
				LEFT JOIN user_roles ur ON u.id = ur.user_id
				WHERE u.username = ?
			""",(username,)).fetchone()
		return dict(row) if row else None
	
	# 验证用户名和密码的方法
	@staticmethod
	def verify_user(username:str,password:str) -> bool:
		row = UserRepository.get_user_by_username(username)
		if not row:
			return False

		salt = bytes.fromhex(row["salt"])
		return _hash_password(password,salt) == row["password_hash"]

	# 分页获取用户列表
	@staticmethod
	def get_users_list(page: int, limit: int):
		offset = (page - 1) * limit
		with get_connection() as conn:
			# 使用 LEFT JOIN 关联 user_roles 和 roles 获取角色信息
			sql = """
				SELECT u.id, u.username, u.create_at, 
					   r.id as role_id, r.name as role_name 
				FROM users u 
				LEFT JOIN user_roles ur ON u.id = ur.user_id 
				LEFT JOIN roles r ON ur.role_id = r.id 
				ORDER BY u.id DESC 
				LIMIT ? OFFSET ?
			"""
			rows = conn.execute(sql, (limit, offset)).fetchall()
			total = conn.execute("SELECT COUNT(1) as cnt FROM users").fetchone()["cnt"]
		return [dict(row) for row in rows], total

	# 删除单用户
	@staticmethod
	def delete_user(user_id: int) -> bool:
		with get_connection() as conn:
			user = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
			if user and user['username'] == 'admin':
				return False # admin cannot be deleted
			conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
			conn.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
		return True

	# 批量删除用户
	@staticmethod
	def delete_users(user_ids: list) -> bool:
		if not user_ids: 
			return False
		with get_connection() as conn:
			admin_user = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
			if admin_user and admin_user['id'] in user_ids:
				user_ids.remove(admin_user['id']) # filter out admin
			if not user_ids:
				return False
				
			placeholders = ",".join("?" * len(user_ids))
			conn.execute(f"DELETE FROM users WHERE id IN ({placeholders})", user_ids)
			conn.execute(f"DELETE FROM user_roles WHERE user_id IN ({placeholders})", user_ids)
		# 删除后压缩自增序号
		compact_sequence('users')
		return True

	# 修改用户
	@staticmethod
	def update_user(user_id: int, username: str, password: str = None, role_id: int = None) -> bool:
		try:
			with get_connection() as conn:
				user = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
				if user and user['username'] == 'admin' and username != 'admin':
					return False # Cannot change admin's username
					
				if password:
					salt = secrets.token_bytes(16)
					password_hash = _hash_password(password, salt)
					conn.execute("UPDATE users SET username=?, password_hash=?, salt=? WHERE id=?", 
								 (username, password_hash, salt.hex(), user_id))
				else:
					conn.execute("UPDATE users SET username=? WHERE id=?", (username, user_id))
					
				# admin 角色固定，不能被修改
				if user and user['username'] == 'admin':
					pass 
				elif role_id:
					conn.execute("DELETE FROM user_roles WHERE user_id=?", (user_id,))
					conn.execute("INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)", (user_id, role_id))
			return True
		except sqlite3.IntegrityError:
			return False
