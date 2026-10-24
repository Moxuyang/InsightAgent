# Controller 公共基础类（BaseHandler）
"""
在tornado中
- 每一个Url对应一个RequestHandler 可以理解为Controller
- RequestHandler 提供 post / get 等方法来处理http请求

本程序可以提供一个统一的基础类，用于处理一些公共业务，如登录态的处理或获得逻辑，供其他Handler继承使用
"""
import tornado.web
from app.models.user import UserRepository

class BaseHandler(tornado.web.RequestHandler):
	# 公共类的用户态认证机制：
	# - 框架会通过 xxxx() 的返回值来判断是否"已经登录"
	# - 如果返回None 则 @tornado.web.authenticated 触发跳转到指定的路由URL：login_url
	def get_current_user(self):
		# 返回当前登录用户的字典对象 或 None
		username = self.get_secure_cookie("username")
		if not username:
			return None
		username_str = username.decode('utf-8')
		
		# 查询完整的用户信息（包含角色ID等）并缓存到当前请求
		if not hasattr(self, "_current_user_dict"):
			self._current_user_dict = UserRepository.get_user_by_username(username_str)
			
		return self._current_user_dict