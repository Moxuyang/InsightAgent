"""
controllers包：控制层（tornado RequestHandler）
约定：
- 一个业务模块一个文件，如auth.py、home.py
- Handler 负责接受请求，校验参数，调用Model,渲染View
"""