"""
真实新闻批量采集 - 多源扒取真实新闻并入库 spy_data

使用方法：python _scrape_real_news.py

特点：
- 主力：百度新闻（最稳定，10条/页）
- 辅助：360资讯、搜狗微信
- 18个真实关键词 -> 预计入库 100+ 条真实新闻
- 自动去重，支持断点续采
"""
import sys, io, time, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from app.models.db import get_connection
from app.models.spy_source import SpySourceRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.controllers.spy import batch_scrape_single_page

# 关键词（真实热点，覆盖多领域）
KEYWORDS = [
    "人工智能 大模型 2026",
    "芯片 半导体 国产",
    "新能源汽车 自动驾驶",
    "数字经济 数字化转型",
    "量子计算 技术突破",
    "网络安全 数据安全",
    "光伏 风电 新能源",
    "央行 货币政策 2026",
    "低空经济 无人机",
    "教育 AI 融合",
    "医疗 医保 改革",
    "5G 6G 通信技术",
    "碳中和 碳达峰",
    "电商 直播 2026",
    "养老服务 人口",
    "云计算 数据中心",
    "智能制造 工业互联网",
    "A股 股市 2026",
]

DELAY_PER_PAGE = (1.5, 3.0)
DELAY_PER_KW = (3.0, 6.0)
MAX_PAGES_PER_KW = 2


def main():
    print("=" * 70)
    print("  InsightAgent · 真实新闻批量采集")
    print("=" * 70)

    sources = SpySourceRepository.get_active_sources()
    if not sources:
        print("[ERROR] 没有活跃数据源！")
        return

    # 优先百度 -> 360 -> 搜狗
    primary = [s for s in sources if s['id'] in [3]]  # 百度新闻
    secondary = [s for s in sources if s['id'] in [5, 6]]  # 360资讯, 搜狗微信
    all_srcs = primary + secondary
    
    print(f'数据源: {len(all_srcs)} 个')
    for s in all_srcs:
        print(f'  [{s["id"]}] {s["name"]}')

    with get_connection() as conn:
        before = conn.execute("SELECT COUNT(1) as cnt FROM spy_data").fetchone()["cnt"]
    print(f'\n当前 spy_data: {before} 条')

    random.shuffle(KEYWORDS)
    total_scraped = 0
    total_new = 0
    
    for idx, kw in enumerate(KEYWORDS):
        # 每个关键词随机选数据源（百度概率更高）
        if random.random() < 0.5:
            src = primary[0]  # 百度 50%概率
        else:
            src = random.choice(all_srcs)
        
        pages = random.randint(1, MAX_PAGES_PER_KW)
        print(f'\n[{idx+1}/{len(KEYWORDS)}] "{kw}" -> {src["name"]} x{pages}')
        
        kw_items = 0
        for pg in range(pages):
            items, hl, err = batch_scrape_single_page(src, kw, page_num=pg)
            if err:
                print(f'  第{pg+1}页 失败: {err}')
                if '验证' in err:
                    break
                continue
            
            if items:
                result = DataWarehouseRepository.upsert_batch(items)
                kw_items += len(items)
                total_scraped += len(items)
                inserted = result.get('inserted', 0)
                total_new += inserted
                print(f'  第{pg+1}页 HTML={hl} | 提取{len(items)}条 | 新增{inserted}条')
                for it in items[:2]:
                    print(f'    -> {it["title"][:65]}')
            else:
                print(f'  第{pg+1}页 HTML={hl} | 未提取到链接')
            
            time.sleep(random.uniform(*DELAY_PER_PAGE))
        
        time.sleep(random.uniform(*DELAY_PER_KW))

    with get_connection() as conn:
        after = conn.execute("SELECT COUNT(1) as cnt FROM spy_data").fetchone()["cnt"]

    print("\n" + "=" * 70)
    print(f"  采集完成!")
    print(f"  爬取总数: {total_scraped} 条 | 新增入库: {total_new} 条")
    print(f"  spy_data: {before} -> {after} 条 (净增 {after-before})")
    print("=" * 70)


if __name__ == "__main__":
    main()
