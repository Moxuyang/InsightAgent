"""配置真实新闻数据源"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
from app.models.db import get_connection

REAL_SOURCES = [
    {
        "name": "百度新闻",
        "entry_url": "https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word={关键字}&pn={分页步进}",
        "headers": (
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8\n"
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.3\n"
            "Cache-Control: max-age=0\n"
            "Connection: keep-alive\n"
            "Host: www.baidu.com\n"
            "Referer: https://www.baidu.com/\n"
            "Upgrade-Insecure-Requests: 1\n"
            "Sec-Fetch-Dest: document\n"
            "Sec-Fetch-Mode: navigate\n"
            "Sec-Fetch-Site: same-origin\n"
            "Sec-Fetch-User: ?1\n"
            "dnt: 1\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "active": 1
    },
    {
        "name": "头条搜索",
        "entry_url": "https://so.toutiao.com/search?dvpf=pc&pd=information&keyword={关键字}&page_num={页码}",
        "headers": (
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8\n"
            "Accept-Language: zh-CN,zh;q=0.9\n"
            "Connection: keep-alive\n"
            "Host: so.toutiao.com\n"
            "Referer: https://www.toutiao.com/\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "active": 1
    },
    {
        "name": "360资讯",
        "entry_url": "https://news.so.com/ns?q={关键字}&pn={分页步进}&src=news_search",
        "headers": (
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8\n"
            "Accept-Language: zh-CN,zh;q=0.9\n"
            "Connection: keep-alive\n"
            "Host: news.so.com\n"
            "Referer: https://news.so.com/\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "active": 1
    },
    {
        "name": "搜狗微信",
        "entry_url": "https://weixin.sogou.com/weixin?type=2&query={关键字}&page={页码}",
        "headers": (
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8\n"
            "Accept-Language: zh-CN,zh;q=0.9\n"
            "Connection: keep-alive\n"
            "Host: weixin.sogou.com\n"
            "Referer: https://weixin.sogou.com/\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "active": 1
    },
]

with get_connection() as conn:
    for src in REAL_SOURCES:
        # 检查是否已存在
        exist = conn.execute(
            "SELECT id FROM spy_sources WHERE name=? OR entry_url=?",
            (src['name'], src['entry_url'])
        ).fetchone()
        if exist:
            # 更新
            conn.execute(
                "UPDATE spy_sources SET entry_url=?, request_headers=?, is_active=? WHERE id=?",
                (src['entry_url'], src['headers'], src['active'], exist['id'])
            )
            print(f"[UPDATE] {src['name']} (id={exist['id']})")
        else:
            conn.execute(
                "INSERT INTO spy_sources (name, entry_url, request_headers, is_active) VALUES (?,?,?,?)",
                (src['name'], src['entry_url'], src['headers'], src['active'])
            )
            print(f"[INSERT] {src['name']}")

    # 列出所有数据源
    rows = conn.execute("SELECT id,name,entry_url,is_active FROM spy_sources ORDER BY id").fetchall()
    print("\n当前数据源配置：")
    print("-" * 80)
    for r in rows:
        status = "✓" if r['is_active'] else "✗"
        print(f"  [{status}] id={r['id']}  {r['name']}")
        print(f"         {r['entry_url']}")
    print("-" * 80)

print("\n数据源配置完成！")
