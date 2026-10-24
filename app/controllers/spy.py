import tornado.web
import json
import urllib.parse
import asyncio
import re
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from app.controllers.base import BaseHandler
from app.models.spy_source import SpySourceRepository
from app.models.data_warehouse import DataWarehouseRepository

# ===== 多源英文名 → 中文名映射 =====
_SOURCE_DISPLAY_NAMES = {
    "baidu": "百度新闻",
    "toutiao": "头条搜索",
    "360": "360资讯",
    "sogou": "搜狗微信",
}

class SpyPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("spy/spy.html", title="瞭望采集")


class SpyRunApiHandler(BaseHandler):
    @tornado.web.authenticated
    async def get(self):
        source_id = int(self.get_argument("source_id", 0))
        keyword = self.get_argument("keyword", "")
        max_pages = int(self.get_argument("max_pages", 1))
        page_step = int(self.get_argument("page_step", 10))

        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Cache-Control', 'no-cache')
        self.set_header('Connection', 'keep-alive')

        source_info = SpySourceRepository.get_source_by_id(source_id)
        if not source_info or not keyword:
            self.write(f"data: {json.dumps({'type':'error', 'msg':'参数错误或未找到数据源'})}\n\n")
            await self.flush()
            return

        source_type = _detect_source_type(source_info['entry_url'], source_info['name'])

        headers_dict = {}
        try:
            for line in source_info['request_headers'].split('\n'):
                if ':' in line and not line.startswith(('GET', 'POST', 'Host')):
                    k, v = line.split(':', 1)
                    key = k.strip()
                    if key.lower() in ("accept-encoding",):
                        continue
                    headers_dict[key] = v.strip()
        except Exception:
            pass

        _UA_POOL = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        ]

        def _ensure(h, k, v):
            for kk in list(h.keys()):
                if kk.lower() == k.lower():
                    return
            h[k] = v

        _ensure(headers_dict, "User-Agent", random.choice(_UA_POOL))
        _ensure(headers_dict, "Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
        _ensure(headers_dict, "Accept-Language", "zh-CN,zh;q=0.9,en;q=0.5")
        _ensure(headers_dict, "Connection", "keep-alive")
        _ensure(headers_dict, "Cache-Control", "max-age=0")
        _ensure(headers_dict, "Upgrade-Insecure-Requests", "1")
        _ensure(headers_dict, "Sec-Fetch-Dest", "document")
        _ensure(headers_dict, "Sec-Fetch-Mode", "navigate")
        _ensure(headers_dict, "Sec-Fetch-Site", "none")
        _ensure(headers_dict, "Sec-Fetch-User", "?1")
        _ensure(headers_dict, "dnt", "1")
        # 头条搜索带 Referer 会返回纯 JS 渲染页面（无内容），必须去掉
        if source_type == "toutiao":
            headers_dict = {k: v for k, v in headers_dict.items() if k.lower() != "referer"}
        # 其他源不覆盖数据库里已有的 Referer
        elif not any(k.lower() == "referer" for k in headers_dict):
            _ensure(headers_dict, "Referer", "https://www.baidu.com/")

        import tornado.ioloop
        total_items = 0
        seen_key = set()

        for page in range(max_pages):
            pn = page * page_step
            target_url = source_info['entry_url']
            target_url = target_url.replace('{关键字}', urllib.parse.quote(keyword))
            target_url = re.sub(r'\{分页步进[^}]*\}', str(pn), target_url)
            target_url = re.sub(r'\{页码[^}]*\}', str(page), target_url)

            self.write(f"data: {json.dumps({'type':'log','level':'info','msg':f'正在请求第 {page+1} 页（{_SOURCE_DISPLAY_NAMES.get(source_type, source_type)}）pn={pn}'}, ensure_ascii=False)}\n\n")
            await self.flush()

            def fetch():
                try:
                    s = requests.Session()
                    retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=0.8,
                                  status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET"]))
                    a = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
                    s.mount("https://", a); s.mount("http://", a)
                    res = s.get(target_url, headers=headers_dict, timeout=(10, 30))
                    try: res.encoding = res.apparent_encoding or "utf-8"
                    except: res.encoding = "utf-8"
                    return {"ok": res.status_code == 200, "status": res.status_code, "text": res.text or ""}
                except Exception as e:
                    return {"ok": False, "status": None, "text": "", "error": str(e)}

            fr = await tornado.ioloop.IOLoop.current().run_in_executor(None, fetch)
            html = fr.get("text", "")

            if not fr.get("ok") or not html:
                err_status = fr.get("status")
                err_msg = fr.get("error", "")
                msg = f"第{page+1}页请求失败 status={err_status} err={err_msg}"
                self.write(f"data: {json.dumps({'type':'log','level':'error','msg':msg})}\n\n")
                await self.flush()
                continue

            # 反爬检测（更精确的匹配）
            html_lower = html.lower()
            antispam = [
                "百度安全验证" in html and len(html) < 3000,
                "请输入验证码" in html and len(html) < 5000,
                "cf-browser-verification" in html_lower,
                ("访问验证" in html and "异常" in html and len(html) < 2000),
                "您的访问出错了" in html and len(html) < 2000,
                "校验失败" in html and "安全" in html and len(html) < 3000,
            ]
            if any(antispam):
                self.write(f"data: {json.dumps({'type':'error','msg':'触发反爬验证拦截，请稍后重试或降低采集频率'})}\n\n")
                await self.flush()
                return

            def parse():
                return _parse_by_source_type(html, source_id, keyword, source_type)

            items, extracted = await tornado.ioloop.IOLoop.current().run_in_executor(None, parse)
            pushed = 0
            for it in items:
                key = (it.get("source_id"), it.get("url"))
                if key in seen_key: continue
                seen_key.add(key)
                self.write(f"data: {json.dumps({'type':'item','data':it}, ensure_ascii=False)}\n\n")
                pushed += 1

            total_items += pushed
            self.write(f"data: {json.dumps({'type':'log','level':'info','msg':f'第{page+1}页：HTML={len(html)} | 链接={extracted} | 新增={pushed}'})}\n\n")
            self.write(f"data: {json.dumps({'type':'log','level':'success','msg':f'第{page+1}页完成，累计{total_items}条'})}\n\n")
            await self.flush()
            await asyncio.sleep(random.uniform(2.0, 4.0))

        self.write(f"data: {json.dumps({'type':'done','count':total_items})}\n\n")
        await self.flush()


class SpyCommitApiHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        try:
            items_json = self.get_argument("items", "[]")
            items = json.loads(items_json) if items_json else []
            if not isinstance(items, list):
                return self.write({"code": 1, "msg": "参数 items 格式错误"})
            result = DataWarehouseRepository.upsert_batch(items)
            self.write({"code": 0, "msg": "入库成功", "data": result})
        except Exception as e:
            self.write({"code": 1, "msg": f"入库失败: {str(e)}"})


# ================================================================
# 多源 HTML 解析器
# ================================================================

def _detect_source_type(entry_url, name):
    u, n = entry_url.lower(), (name or "").lower()
    if "toutiao.com" in u or "头条" in n: return "toutiao"
    if "so.com" in u or "360" in n: return "360"
    if "sogou.com" in u or "weixin" in u or "搜狗" in n: return "sogou"
    return "baidu"


def _parse_by_source_type(html, source_id, keyword, source_type):
    if source_type == "toutiao":
        return _parse_toutiao(html, source_id, keyword)
    elif source_type == "360":
        return _parse_360(html, source_id, keyword)
    elif source_type == "sogou":
        return _parse_sogou(html, source_id, keyword)
    else:
        return _parse_baidu(html, source_id, keyword)


# ---------- 百度新闻 ----------
def _parse_baidu(html, source_id, keyword):
    soup = BeautifulSoup(html, 'html.parser')
    seen = set()
    links = []

    # 策略1: h3 a（百度资讯搜索常见）
    for a in soup.select('h3 a'):
        href = (a.get('href') or '').strip()
        title = a.get_text(" ", strip=True)
        if href and title and href not in seen:
            seen.add(href); links.append(a)

    # 策略2: div.result h3 a
    if not links:
        for a in soup.select('div.result h3 a, div.result-op h3 a, div.c-container h3 a'):
            href = (a.get('href') or '').strip()
            title = a.get_text(" ", strip=True)
            if href and title and href not in seen:
                seen.add(href); links.append(a)

    items = []
    for a in links:
        title = a.get_text(" ", strip=True)
        url = (a.get('href') or '').strip()
        if not url or not title: continue

        container = a.find_parent('div', class_=re.compile(r'(result|c-container|result-op)', re.I)) or a.find_parent('div')
        summary = ""
        if container:
            sn = (container.select_one('span.c-font-normal')
                  or container.select_one('div.c-summary')
                  or container.select_one('div.c-abstract')
                  or container.select_one('div.content')
                  or container.select_one('span.content-right_8Zs40'))
            if sn:
                summary = sn.get_text(" ", strip=True)
            else:
                summary = container.get_text(" ", strip=True).replace(title, "").strip()
        if len(summary) > 500: summary = summary[:500]

        items.append({"source_id": source_id, "keyword": keyword, "title": title, "url": url, "summary": summary})
    return items, len(items)


# ---------- 头条搜索 ----------
def _parse_toutiao(html, source_id, keyword):
    soup = BeautifulSoup(html, 'html.parser')
    seen = set()
    items = []

    # 头条搜索结果：a.text-ellipsis.text-underline-hover 是新闻链接
    for a in soup.select('a.text-ellipsis, a[class*="text-ellipsis"]'):
        href = (a.get('href') or '').strip()
        title = a.get_text(" ", strip=True)
        if not href or not title: continue
        if len(title) < 6: continue  # 过滤导航类短文本
        if href in seen: continue
        seen.add(href)

        # 找父级容器获取摘要
        summary = ""
        parent = a.find_parent(['li', 'div'], class_=re.compile(r'(result|item|s-result|cs-result)', re.I))
        if parent:
            desc = (parent.select_one('span.abstract') or parent.select_one('div.abstract')
                    or parent.select_one('p.content') or parent.select_one('div[class*="desc"]')
                    or parent.select_one('div[class*="info"]'))
            if desc:
                summary = desc.get_text(" ", strip=True)
        if len(summary) > 500: summary = summary[:500]

        items.append({"source_id": source_id, "keyword": keyword, "title": title, "url": href, "summary": summary})

    return items, len(items)


# ---------- 360资讯 ----------
def _parse_360(html, source_id, keyword):
    soup = BeautifulSoup(html, 'html.parser')
    seen = set()
    items = []

    # 360资讯结果在 li.res-list / div.res-list 内
    containers = soup.select('li.res-list, li[class*="res"], div.res-list, div.result')
    if containers:
        for c in containers:
            a_tag = c.select_one('h3 a') or c.select_one('a[class*="title"]') or c.select_one('a')
            if not a_tag: continue
            href = (a_tag.get('href') or '').strip()
            title = a_tag.get_text(" ", strip=True)
            if not href or not title or len(title) < 8: continue
            if href in seen: continue
            seen.add(href)

            summary = ""
            desc = (c.select_one('div.res-desc') or c.select_one('p.res-desc')
                    or c.select_one('div.abstract') or c.select_one('div.summary'))
            if desc:
                summary = desc.get_text(" ", strip=True)
            if len(summary) > 500: summary = summary[:500]

            items.append({"source_id": source_id, "keyword": keyword, "title": title, "url": href, "summary": summary})
    else:
        # 回退：从主内容区提取所有长文本链接
        main = soup.select_one('div#main, div.main, div.result-container, div#results')
        if not main:
            main = soup
        for a in main.select('a[href]'):
            href = (a.get('href') or '').strip()
            title = a.get_text(" ", strip=True)
            if not href or not title or len(title) < 15: continue
            if '360.cn' in href or href.startswith('#') or href.startswith('javascript:'): continue
            if href in seen: continue
            seen.add(href)
            items.append({"source_id": source_id, "keyword": keyword, "title": title[:200], "url": href, "summary": ""})

    return items, len(items)


# ---------- 搜狗微信 ----------
def _parse_sogou(html, source_id, keyword):
    soup = BeautifulSoup(html, 'html.parser')
    seen = set()
    items = []

    # 搜狗微信搜索结果通常在 div.news-box 或 ul.news-list 内
    containers = soup.select('li.news-item, div.news-item, div.news-box, ul.news-list li, div.results div.item')
    if not containers:
        containers = soup.select('div[class*="news"]')

    for c in containers:
        a_tag = c.select_one('h3 a') or c.select_one('a[class*="title"]') or c.select_one('a')
        if not a_tag: continue
        href = (a_tag.get('href') or '').strip()
        title = a_tag.get_text(" ", strip=True)
        if not href or not title: continue
        if href in seen: continue
        seen.add(href)

        summary = ""
        desc = (c.select_one('p.txt-info') or c.select_one('div.txt-info')
                or c.select_one('p.abstract') or c.select_one('div.abstract')
                or c.select_one('div.space-txt'))
        if desc:
            summary = desc.get_text(" ", strip=True)
        if len(summary) > 500: summary = summary[:500]

        # 搜狗微信的相对路径URL补全域名
        if href.startswith('/'):
            href = f"https://weixin.sogou.com{href}"
        items.append({"source_id": source_id, "keyword": keyword, "title": title, "url": href, "summary": summary})
    return items, len(items)


# ================================================================
# 离线批量采集入口（供脚本调用）
# ================================================================
def batch_scrape_single_page(source_info, keyword, page_num=0, page_step=10):
    """离线批量采集单页，返回 (items, html_length, error)"""
    source_type = _detect_source_type(source_info.get('entry_url', ''), source_info.get('name', ''))
    source_id = source_info['id']

    headers_dict = {}
    try:
        for line in (source_info.get('request_headers', '') or '').split('\n'):
            if ':' in line and not line.startswith(('GET', 'POST', 'Host')):
                k, v = line.split(':', 1)
                key = k.strip()
                if key.lower() in ("accept-encoding",): continue
                headers_dict[key] = v.strip()
    except: pass

    UA_POOL = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
    ]

    def _ensure(h, k, v):
        for kk in list(h.keys()):
            if kk.lower() == k.lower(): return
        h[k] = v

    _ensure(headers_dict, "User-Agent", random.choice(UA_POOL))
    _ensure(headers_dict, "Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
    _ensure(headers_dict, "Accept-Language", "zh-CN,zh;q=0.9,en;q=0.5")
    _ensure(headers_dict, "Connection", "keep-alive")
    _ensure(headers_dict, "Cache-Control", "max-age=0")
    _ensure(headers_dict, "Upgrade-Insecure-Requests", "1")
    _ensure(headers_dict, "Sec-Fetch-Dest", "document")
    _ensure(headers_dict, "Sec-Fetch-Mode", "navigate")
    _ensure(headers_dict, "Sec-Fetch-Site", "none")
    _ensure(headers_dict, "Sec-Fetch-User", "?1")
    _ensure(headers_dict, "dnt", "1")
    if not any(k.lower() == "referer" for k in headers_dict):
        _ensure(headers_dict, "Referer", "https://www.baidu.com/")

    pn = page_num * page_step
    target_url = source_info['entry_url']
    target_url = target_url.replace('{关键字}', urllib.parse.quote(keyword))
    target_url = re.sub(r'\{分页步进[^}]*\}', str(pn), target_url)
    target_url = re.sub(r'\{页码[^}]*\}', str(page_num), target_url)

    try:
        s = requests.Session()
        retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=0.8,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET"]))
        a = HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=5)
        s.mount("https://", a); s.mount("http://", a)
        res = s.get(target_url, headers=headers_dict, timeout=(10, 30))
        try: res.encoding = res.apparent_encoding or "utf-8"
        except: res.encoding = "utf-8"
        html = res.text or ""

        # 反爬检测
        html_lower = html.lower()
        antispam = [
            "百度安全验证" in html and len(html) < 3000,
            "请输入验证码" in html and len(html) < 5000,
            "cf-browser-verification" in html_lower,
            "您的访问出错了" in html and len(html) < 2000,
        ]
        if any(antispam):
            return [], len(html), "触发反爬验证"

        items, _ = _parse_by_source_type(html, source_id, keyword, source_type)
        return items, len(html), None
    except Exception as e:
        return [], 0, str(e)
