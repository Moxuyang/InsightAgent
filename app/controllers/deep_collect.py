import tornado.web
import json
import os
import re
import uuid
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from app.controllers.base import BaseHandler
from app.models.deep_collect import DeepCollectRepository
from app.models.deep_collect_result import DeepCollectResultRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.models.db import get_connection

# 获取项目根目录
def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

UPLOAD_DIR = os.path.join(_project_root(), "uploads", "deep_collect")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class DeepCollectPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("deep_collect/list.html", title="深度采集")


class DeepCollectApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        keyword = self.get_argument("keyword", "").strip()
        rows, total = DeepCollectRepository.get_list(page, limit, keyword)
        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "add":
            name = self.get_argument("name", "").strip()
            target_url = self.get_argument("target_url", "").strip()
            collect_type = self.get_argument("collect_type", "webpage")
            cron_expression = self.get_argument("cron_expression", "")
            is_active = int(self.get_argument("is_active", 1))
            if not name or not target_url:
                return self.write({"code": 1, "msg": "名称和目标URL不能为空"})
            DeepCollectRepository.create(name, target_url, collect_type, cron_expression, is_active)
            self.write({"code": 0, "msg": "添加成功"})
        elif action == "edit":
            collect_id = int(self.get_argument("id", 0))
            name = self.get_argument("name", "").strip()
            target_url = self.get_argument("target_url", "").strip()
            collect_type = self.get_argument("collect_type", "webpage")
            cron_expression = self.get_argument("cron_expression", "")
            is_active = int(self.get_argument("is_active", 1))
            if not collect_id or not name:
                return self.write({"code": 1, "msg": "参数错误"})
            DeepCollectRepository.update(collect_id, name, target_url, collect_type, cron_expression, is_active)
            self.write({"code": 0, "msg": "修改成功"})
        elif action == "delete":
            collect_id = int(self.get_argument("id", 0))
            DeepCollectRepository.delete(collect_id)
            self.write({"code": 0, "msg": "删除成功"})
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if DeepCollectRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})
        else:
            self.write({"code": 1, "msg": "未知操作"})


# ========================== 数据仓库 API（供深度采集页面使用） ==========================
class DeepCollectDataApiHandler(BaseHandler):
    """返回 spy_data 数据仓库列表，供深度采集选择"""
    @tornado.web.authenticated
    def get(self):
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        keyword = self.get_argument("keyword", "")
        source_id = self.get_argument("source_id", "").strip() or None
        rows, total = DataWarehouseRepository.get_data_list(page, limit, keyword, source_id)
        self.write({"code": 0, "msg": "", "count": total, "data": rows})


# ========================== 深度采集执行 API ==========================
class DeepCollectRunApiHandler(BaseHandler):
    """执行深度采集：从数据仓库选中的条目，爬取原文正文+图片"""

    @tornado.web.authenticated
    async def get(self):
        spy_data_id = int(self.get_argument("spy_data_id", 0))
        if not spy_data_id:
            self.write({"code": 1, "msg": "缺少 spy_data_id 参数"})
            return

        # 查询 spy_data
        with get_connection() as conn:
            spy_row = conn.execute(
                "SELECT * FROM spy_data WHERE id=?", (spy_data_id,)
            ).fetchone()

        if not spy_row:
            self.write({"code": 1, "msg": "数据仓库中未找到该记录"})
            return

        spy_data = dict(spy_row)
        url = spy_data.get("url", "")
        title = spy_data.get("title", "")

        if not url:
            self.write({"code": 1, "msg": "该记录没有有效的URL"})
            return

        # 预处理URL：解析头条等搜索的跳转链接，提取真实目标URL
        # 处理相对路径（百度加密跳转链接 /link?url=...）
        url = _normalize_url(url)

        # 检查是否已成功采集过
        existing = DeepCollectResultRepository.get_by_spy_data_id(spy_data_id)
        if existing and existing.get("crawl_status") == "success":
            self.write({"code": 0, "msg": "已采集", "data": existing})
            return

        # 创建采集记录（状态：pending）
        result_id = DeepCollectResultRepository.create(spy_data_id, title, url)
        if result_id is None:
            # 已有成功记录
            self.write({"code": 0, "msg": "已采集过，直接返回已有结果", "data": existing})
            return

        # 异步执行爬取（自动降级：requests → Playwright）
        import tornado.ioloop
        crawl_result = await tornado.ioloop.IOLoop.current().run_in_executor(
            None, _deep_crawl_article_auto, url, title, result_id
        )

        # 更新结果
        DeepCollectResultRepository.update_result(
            result_id,
            crawl_result.get("full_content", ""),
            crawl_result.get("content_html", ""),
            json.dumps(crawl_result.get("images", []), ensure_ascii=False),
            crawl_result.get("status", "failed"),
            crawl_result.get("error")
        )

        result_data = DeepCollectResultRepository.get_by_id(result_id)
        self.write({
            "code": 0 if crawl_result["status"] == "success" else 1,
            "msg": "采集成功" if crawl_result["status"] == "success" else f"采集失败: {crawl_result.get('error', '')}",
            "data": result_data
        })


# ========================== 深度采集结果 API ==========================
class DeepCollectResultApiHandler(BaseHandler):
    """管理深度采集结果列表"""
    @tornado.web.authenticated
    def get(self):
        page = int(self.get_argument("page", 1))
        limit = int(self.get_argument("limit", 20))
        keyword = self.get_argument("keyword", "")
        rows, total = DeepCollectResultRepository.get_list(page, limit, keyword)
        self.write({"code": 0, "msg": "", "count": total, "data": rows})

    @tornado.web.authenticated
    def post(self):
        action = self.get_argument("action", "")
        if action == "delete":
            result_id = int(self.get_argument("id", 0))
            DeepCollectResultRepository.delete(result_id)
            self.write({"code": 0, "msg": "删除成功"})
        elif action == "batch_delete":
            ids_str = self.get_argument("ids", "")
            ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
            if DeepCollectResultRepository.delete_batch(ids):
                self.write({"code": 0, "msg": "批量删除成功"})
            else:
                self.write({"code": 1, "msg": "没有可删除的记录"})
        else:
            self.write({"code": 1, "msg": "未知操作"})


# ========================== 深度采集结果详情 API ==========================
class DeepCollectResultDetailHandler(BaseHandler):
    """查看单条深度采集结果的完整内容"""
    @tornado.web.authenticated
    def get(self):
        result_id = int(self.get_argument("id", 0))
        if not result_id:
            self.write({"code": 1, "msg": "缺少 id 参数"})
            return
        data = DeepCollectResultRepository.get_by_id(result_id)
        if not data:
            self.write({"code": 1, "msg": "未找到结果"})
            return
        self.write({"code": 0, "msg": "", "data": data})


# ========================== URL 预处理 ==========================
def _normalize_url(url, max_depth=5):
    """统一处理各种搜索跳转URL和相对路径URL，返回可爬取的绝对URL。
    
    场景：
    1. 头条跳转(支持多层嵌套): sou.toutiao.com/search/jump?url=... → 递归提取真实文章链接
    2. 加密跳转(相对): /link?url=... → 补全域名（百度/搜狗微信）
    3. 百度加密跳转(绝对): https://www.baidu.com/link?url=... → 原样保留，后续 follow redirect
    4. 普通绝对URL → 原样返回
    """
    if not url:
        return url

    from urllib.parse import urlparse, parse_qs, unquote

    # 场景2: 相对路径（百度加密跳转，搜狗微信已在上游补全为绝对URL）
    if url.startswith('/link?') or url.startswith('/sf?'):
        return f"https://www.baidu.com{url}"

    # 场景1: 头条搜索跳转（递归解码，处理双层嵌套）
    if max_depth > 0:
        parsed = urlparse(url)
        if 'toutiao.com' in (parsed.netloc or '') and '/search/jump' in parsed.path:
            qs = parse_qs(parsed.query)
            target = qs.get('url', [None])[0]
            if target:
                decoded = unquote(target)
                # 递归：目标 URL 可能又是 jump 链接
                return _normalize_url(decoded, max_depth - 1)

    # 场景3+4: 百度绝对跳转或普通URL，原样返回
    return url


def _short_error(e):
    """截短错误消息，只保留关键信息"""
    msg = str(e)
    import re
    m = re.search(r"Failed to resolve '([^']+)'", msg)
    if m:
        return f"域名无法解析: {m.group(1)}"
    if len(msg) > 200:
        return msg[:200] + "..."
    return msg


def _detect_sogou_captcha(html):
    """检测搜狗微信/搜狗搜索的验证码页面"""
    if not html:
        return False
    # 搜狗验证码特征
    markers = [
        'VerifyCode',           # 搜狗验证码字段
        'weixin.sogou.com',     # 搜狗微信域名 + 验证码
        '验证码',               # 中文验证码
        '请输入验证码',         # 验证码提示
    ]
    # 必须同时出现 2 个以上标记才判定为验证码页，避免误判
    count = sum(1 for m in markers if m in html)
    # 额外检测：页面很短（<2KB）且包含验证码关键词 → 很可能就是验证码页
    is_short_page = len(html) < 3000
    if count >= 2:
        return True
    if is_short_page and ('验证码' in html or 'VerifyCode' in html):
        return True
    return False


# ========================== 核心爬取函数 ==========================
# ================== 策略1：requests 快速爬取 ==================
def _deep_crawl_article(url, title, result_id):
    """深度爬取网页正文内容 + 图片（requests 版，适合服务端渲染页面）"""
    result = {
        "status": "failed",
        "full_content": "",
        "content_html": "",
        "images": [],
        "error": ""
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        sess = requests.Session()
        retry = Retry(total=2, connect=2, read=2, backoff_factor=0.5,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET"]))
        adapter = HTTPAdapter(max_retries=retry)
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)

        # 百度/搜狗加密链接需要合法的 Referer，否则可能返回空或触发反爬
        if 'baidu.com/link' in url or 'baidu.com/sf' in url:
            headers["Referer"] = "https://www.baidu.com/"
        elif 'weixin.sogou.com' in url:
            headers["Referer"] = "https://weixin.sogou.com/"

        resp = sess.get(url, headers=headers, timeout=(10, 30), allow_redirects=True)
        if resp.status_code != 200:
            status_msgs = {
                301: "页面已永久重定向",
                302: "页面已临时重定向",
                403: "网站拒绝访问（可能需要登录或IP被限制）",
                404: "页面不存在（文章可能已删除或链接过期）",
                410: "文章已永久删除",
                429: "请求太频繁，被限流",
                500: "目标网站服务器错误",
                502: "目标网站网关错误",
                503: "目标网站暂时不可用",
            }
            detail = status_msgs.get(resp.status_code, f"未知错误")
            result["error"] = f"HTTP {resp.status_code}：{detail}"
            return result

        try:
            resp.encoding = resp.apparent_encoding or "utf-8"
        except:
            resp.encoding = "utf-8"

        html = resp.text
        if not html or len(html) < 200:
            result["error"] = "页面内容为空"
            return result

        # 检测搜狗微信验证码页面
        if _detect_sogou_captcha(html):
            result["error"] = "搜狗微信触发了反爬验证码，深度采集无法自动绕过。建议：1)在浏览器中手动打开链接完成验证后再试；2)或只保留标题链接供人工查看"
            return result

        soup = BeautifulSoup(html, 'html.parser')

        # 移除无用标签
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'iframe', 'noscript']):
            tag.decompose()

        # 提取正文内容
        article_content = _extract_article_content(soup, url)

        if not article_content:
            result["error"] = "未能提取到正文内容"
            return result

        # 提取图片并下载
        images = _extract_and_download_images(article_content, url)

        # 获取纯文本
        full_text = article_content.get_text(separator="\n", strip=True)
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)  # 压缩多余空行

        # 内容质量校验：正文太短说明页面可能是动态加载或登录墙
        if len(full_text.strip()) < 80 and len(images) == 0:
            result["full_content"] = full_text[:100000]
            result["content_html"] = str(article_content)[:200000]
            result["images"] = images
            result["error"] = "页面为前端动态渲染（如Vue/React），常规爬虫无法提取正文，请点击下方原文链接查看"
            return result

        # 获取带图片的HTML
        content_html = str(article_content)

        result["status"] = "success"
        result["full_content"] = full_text[:100000]  # 限制10万字符
        result["content_html"] = content_html[:200000]  # 限制20万字符
        result["images"] = images

    except requests.exceptions.ConnectionError as e:
        result["error"] = f"网络连接失败，无法访问该网站: {_short_error(e)}"
    except requests.exceptions.Timeout:
        result["error"] = "请求超时，网站响应过慢"
    except requests.exceptions.TooManyRedirects:
        result["error"] = "重定向次数过多，URL可能为跳转链"
    except requests.exceptions.RequestException as e:
        result["error"] = f"请求异常: {_short_error(e)}"
    except Exception as e:
        result["error"] = f"解析失败: {_short_error(e)}"

    return result


# ================== 策略2：Playwright 浏览器渲染 ==================
def _deep_crawl_article_with_browser(url, title, result_id):
    """使用 Playwright 无头浏览器渲染后爬取（适用于 JS 动态页面）"""
    result = {
        "status": "failed",
        "full_content": "",
        "content_html": "",
        "images": [],
        "error": ""
    }

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            page = context.new_page()

            try:
                # 导航到页面
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # 额外等待 JS 渲染完成
                page.wait_for_timeout(3000)

                # 获取渲染后的完整 HTML
                html = page.content()
            finally:
                page.close()
                context.close()
                browser.close()

        if not html or len(html) < 200:
            result["error"] = "浏览器渲染后页面仍为空"
            return result

        # 检测搜狗微信验证码（Playwright 也可能触发验证码）
        if _detect_sogou_captcha(html):
            result["error"] = "搜狗微信触发了反爬验证码，即使使用浏览器渲染也无法绕过。建议手动在浏览器中打开原文链接"
            return result

        # === 复用相同的 BeautifulSoup 提取逻辑 ===
        soup = BeautifulSoup(html, 'html.parser')

        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'iframe', 'noscript']):
            tag.decompose()

        article_content = _extract_article_content(soup, url)
        if not article_content:
            result["error"] = "浏览器渲染后仍未能提取正文"
            return result

        images = _extract_and_download_images(article_content, url)

        full_text = article_content.get_text(separator="\n", strip=True)
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)

        if len(full_text.strip()) < 80 and len(images) == 0:
            result["full_content"] = full_text[:100000]
            result["content_html"] = str(article_content)[:200000]
            result["images"] = images
            result["error"] = "浏览器渲染后正文仍不足，该页面可能需登录或有反爬机制"
            return result

        content_html = str(article_content)

        result["status"] = "success"
        result["full_content"] = full_text[:100000]
        result["content_html"] = content_html[:200000]
        result["images"] = images

    except Exception as e:
        result["error"] = f"浏览器渲染失败: {_short_error(e)}"

    return result


# ================== 自动降级调度 ==================
def _deep_crawl_article_auto(url, title, result_id):
    """自动选择爬取策略：requests 快速抓取 → 内容不足时自动降级为 Playwright 渲染"""
    # 第一步：requests 快速爬取
    result = _deep_crawl_article(url, title, result_id)

    # 成功直接返回
    if result["status"] == "success":
        return result

    # 判断是否需要降级到 Playwright
    err = result.get("error") or ""
    should_fallback = (
        "动态渲染" in err or
        "内容不足" in err or
        "未能提取到正文" in err or
        "验证码" in err  # 搜狗等验证码页面，尝试浏览器渲染
    )

    if should_fallback:
        print(f"[深度采集] requests失败({err})，自动切换Playwright: {url}")
        browser_result = _deep_crawl_article_with_browser(url, title, result_id)
        # 如果 Playwright 也失败，保留更详细的错误信息
        if browser_result["status"] == "failed" and result.get("full_content"):
            browser_result["full_content"] = browser_result["full_content"] or result["full_content"]
            browser_result["content_html"] = browser_result["content_html"] or result["content_html"]
        return browser_result

    # 404/403 也可能因为跳转链（百度/搜狗加密链接等）在普通请求下无法正常工作
    # 对跳转型 URL 尝试 Playwright
    is_redirect_url = (
        "baidu.com/link" in url or
        "toutiao.com/search/jump" in url or
        "weixin.sogou.com/link" in url or
        url.startswith("https://www.baidu.com/link")
    )
    if ("404" in err or "403" in err) and is_redirect_url:
        print(f"[深度采集] 跳转型URL {err}，尝试Playwright: {url}")
        browser_result = _deep_crawl_article_with_browser(url, title, result_id)
        if browser_result["status"] == "success":
            return browser_result

    return result


def _extract_article_content(soup, base_url):
    """使用多种策略提取文章正文"""
    # 策略1: 查找 <article> 标签
    article = soup.find('article')
    if article:
        return article

    # 策略2: 常见内容容器 class/id
    content_selectors = [
        'div.article-content', 'div.article-body', 'div.article',
        'div.content-article', 'div#article', 'div#content',
        'div.post-content', 'div.post-body', 'div.entry-content',
        'div.news-content', 'div.detail-content', 'div.detail',
        'div.text-content', 'div.main-content', 'div.main_body',
        'div[class*="article"]', 'div[class*="content"]',
    ]

    for selector in content_selectors:
        try:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 200:
                return el
        except:
            continue

    # 策略3: 找包含最多文本段落的 div
    candidates = []
    for div in soup.find_all('div'):
        p_tags = div.find_all('p')
        if len(p_tags) >= 3:
            text_len = len(div.get_text(strip=True))
            if text_len > 300:
                candidates.append((text_len, div))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # 策略4: 直接取 body
    body = soup.find('body')
    return body if body else soup


def _extract_and_download_images(content_element, page_url):
    """提取并下载文章中的图片"""
    images = []
    img_tags = content_element.find_all('img') if content_element else []

    for img in img_tags:
        src = (img.get('src') or img.get('data-src') or img.get('data-original') or '').strip()
        if not src or src.startswith('data:'):
            continue

        # 解析完整URL
        if not src.startswith('http'):
            src = urljoin(page_url, src)

        # 过滤明显的小图标
        if any(x in src.lower() for x in ['icon', 'avatar', 'logo', 'emoji', '1x1', 'pixel']):
            continue

        local_path = None
        try:
            # 下载图片
            img_resp = requests.get(src, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36",
                "Referer": page_url
            }, timeout=(8, 15))

            if img_resp.status_code == 200 and len(img_resp.content) > 1024:
                content_type = img_resp.headers.get('Content-Type', '')
                ext = 'jpg'
                if 'png' in content_type: ext = 'png'
                elif 'gif' in content_type: ext = 'gif'
                elif 'webp' in content_type: ext = 'webp'

                filename = f"{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(UPLOAD_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(img_resp.content)

                local_path = f"/uploads/deep_collect/{filename}"
                # 替换 img 的 src 为本地路径
                img['src'] = local_path
                img['data-original'] = src  # 保留原始链接

        except Exception:
            local_path = src  # 下载失败保留原始URL

        images.append({
            "original": src,
            "local": local_path,
            "alt": (img.get('alt') or '').strip()
        })

    return images
