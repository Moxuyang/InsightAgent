# 项目环境与启动

## 已检查的依赖

- Python 3.11：与项目现有的 Python 3.11 编译缓存一致。
- Tornado：Web 服务，入口为 `app.py`，端口为 `10086`。
- OpenAI SDK：调用兼容 OpenAI 协议的模型接口。
- requests、urllib3、Beautiful Soup：网页采集和解析。
- Playwright + Chromium：深度采集中的动态网页渲染。
- SQLite：Python 自带，默认数据文件为 `database/app.db`。
- PyMySQL（含 RSA 支持）：可选 MySQL 后端；切换到 MySQL 时需另行提供数据库服务。

项目没有 Node.js 构建配置，也未发现本地模型训练或 GPU/CUDA 依赖。

## 启动

在项目根目录打开 Anaconda Prompt：

```bat
conda activate insight_agent
python app.py
```

浏览器访问 http://localhost:10086 。AI 功能需要在系统的模型引擎中配置可用的接口地址、模型名称和 API Key。

## 重建环境

```bat
conda env create -f environment.yml
conda activate insight_agent
python -m playwright install chromium
```

`requirements.txt` 记录直接依赖范围；`requirements-lock.txt` 记录本次安装后验证过的完整 Python 包版本。

首次运行 `app.py` 会执行建表和默认角色、菜单初始化。环境验证通过导入入口、构建应用及请求登录页进行，不执行主入口中的数据库初始化逻辑。

