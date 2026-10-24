"""项目数据分析引擎 —— 查询项目数据库并生成分析报告"""

from app.models.db import get_connection


def get_business_metrics(category: str = None) -> dict:
    """获取业务指标数据
    
    Args:
        category: 可选筛选类别 (user_metrics/sales/product/customer/system)
    
    Returns:
        {"success": True, "data": [...], "summary": "..."}
    """
    try:
        with get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM business_data WHERE category=? ORDER BY metric_date DESC, id DESC",
                    (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM business_data ORDER BY metric_date DESC, id DESC"
                ).fetchall()
        
        data = [dict(r) for r in rows]
        
        # 生成摘要
        categories = list(set(r['category'] for r in data))
        date_range = f"{data[-1]['metric_date']} ~ {data[0]['metric_date']}" if len(data) > 1 else (data[0]['metric_date'] if data else 'N/A')
        
        summary = f"共 {len(data)} 条业务数据，涵盖 {len(categories)} 个类别（{', '.join(categories)}），时间范围：{date_range}"
        
        return {"success": True, "data": data, "summary": summary}
        
    except Exception as e:
        return {"success": False, "error": f"数据查询失败: {str(e)}"}


def get_trend_analysis(category: str, item_name: str) -> dict:
    """对指定指标做趋势分析
    
    Args:
        category: 数据类别
        item_name: 指标名称
    
    Returns:
        {"success": True, "trend": [...], "stats": {...}, "analysis": "..."}
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM business_data 
                   WHERE category=? AND item_name=? 
                   ORDER BY metric_date ASC""",
                (category, item_name)
            ).fetchall()
        
        if not rows:
            return {"success": False, "error": f"未找到 {category}/{item_name} 的数据"}
        
        data = [dict(r) for r in rows]
        values = [r['metric_value'] for r in data]
        
        # 计算统计指标
        import math
        n = len(values)
        avg = sum(values) / n
        variance = sum((v - avg) ** 2 for v in values) / n
        std_dev = math.sqrt(variance)
        max_val = max(values)
        min_val = min(values)
        max_idx = values.index(max_val)
        min_idx = values.index(min_val)
        
        # 计算环比变化
        changes = []
        for i in range(1, n):
            prev = values[i-1]
            curr = values[i]
            if prev != 0:
                pct = round((curr - prev) / prev * 100, 1)
            else:
                pct = 0
            changes.append({
                "period": f"{data[i-1]['metric_date']} → {data[i]['metric_date']}",
                "from": prev,
                "to": curr,
                "change_pct": pct
            })
        
        # 判断趋势
        if n >= 2:
            if all(changes[i]['change_pct'] > 0 for i in range(len(changes))):
                trend_desc = "稳定上升"
            elif all(changes[i]['change_pct'] < 0 for i in range(len(changes))):
                trend_desc = "持续下降"
            elif changes[-1]['change_pct'] > 0:
                trend_desc = "近期呈上升趋势"
            elif changes[-1]['change_pct'] < 0:
                trend_desc = "近期呈下降趋势"
            else:
                trend_desc = "波动变化"
        else:
            trend_desc = "数据量不足，无法判断趋势"
        
        stats = {
            "总数": n,
            "平均值": round(avg, 2),
            "标准差": round(std_dev, 2),
            "最大值": max_val,
            "最大值时期": data[max_idx]['metric_date'],
            "最小值": min_val,
            "最小值时期": data[min_idx]['metric_date'],
            "最新值": values[-1],
            "最新时期": data[-1]['metric_date'],
            "趋势": trend_desc
        }
        
        analysis_lines = [
            f"📊 {item_name} 趋势分析报告",
            f"",
            f"【数据概况】",
            f"统计周期：{data[0]['metric_date']} ~ {data[-1]['metric_date']}（共{n}期）",
            f"均值：{avg:.2f} | 最大值：{max_val}（{data[max_idx]['metric_date']}）| 最小值：{min_val}（{data[min_idx]['metric_date']}）",
            f"标准差：{std_dev:.2f}（数据波动{'较大' if std_dev/avg > 0.15 else '正常' if std_dev/avg > 0.05 else '较小'}）",
            f"",
            f"【逐期变化】",
        ]
        
        for ch in changes:
            arrow = "↑" if ch['change_pct'] > 0 else "↓" if ch['change_pct'] < 0 else "→"
            analysis_lines.append(f"  {ch['period']}: {ch['from']} → {ch['to']} ({arrow}{abs(ch['change_pct'])}%)")
        
        analysis_lines.append(f"")
        analysis_lines.append(f"【趋势判断】{trend_desc}")
        
        analysis = "\n".join(analysis_lines)
        
        return {
            "success": True,
            "trend": [{"date": r['metric_date'], "value": r['metric_value'], "remark": r.get('remark', '')} for r in data],
            "stats": stats,
            "changes": changes,
            "analysis": analysis
        }
        
    except Exception as e:
        return {"success": False, "error": f"趋势分析失败: {str(e)}"}


def get_category_summary(date: str = None) -> dict:
    """获取某个时间点的全类别概览
    
    Args:
        date: 可选日期 (YYYY-MM-DD)，默认最新
    
    Returns:
        {"success": True, "overview": {...}, "analysis": "..."}
    """
    try:
        with get_connection() as conn:
            if date:
                rows = conn.execute(
                    "SELECT * FROM business_data WHERE metric_date=?", (date,)
                ).fetchall()
            else:
                # 获取最新日期
                latest = conn.execute(
                    "SELECT metric_date FROM business_data ORDER BY metric_date DESC LIMIT 1"
                ).fetchone()
                if not latest:
                    return {"success": False, "error": "暂无业务数据"}
                date = latest['metric_date']
                rows = conn.execute(
                    "SELECT * FROM business_data WHERE metric_date=?", (date,)
                ).fetchall()
        
        data = [dict(r) for r in rows]
        
        # 按类别分组
        categories = {}
        for r in data:
            cat = r['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r)
        
        analysis_lines = [
            f"📈 项目数据概览（{date}）",
            f"",
        ]
        
        cat_names = {
            'user_metrics': '👥 用户指标',
            'sales': '💰 销售数据',
            'product': '📦 产品销量',
            'customer': '😊 客户满意度',
            'system': '⚙️ 系统运行'
        }
        
        overview = {}
        for cat, items in categories.items():
            cat_items = {}
            for item in items:
                cat_items[item['item_name']] = {
                    "value": item['metric_value'],
                    "region": item['region'],
                    "remark": item.get('remark', '')
                }
            overview[cat] = cat_items
            
            name = cat_names.get(cat, cat)
            analysis_lines.append(f"{name}：")
            for item in items:
                region = f"({item['region']})" if item['region'] != '全国' else ""
                analysis_lines.append(f"  • {item['item_name']}{region}: {item['metric_value']}  {item.get('remark', '')}")
            analysis_lines.append("")
        
        analysis = "\n".join(analysis_lines)
        
        return {"success": True, "overview": overview, "analysis": analysis, "date": date}
        
    except Exception as e:
        return {"success": False, "error": f"概览查询失败: {str(e)}"}


def compare_periods(category: str, item_name: str, date1: str, date2: str) -> dict:
    """两期数据对比分析"""
    try:
        with get_connection() as conn:
            r1 = conn.execute(
                "SELECT * FROM business_data WHERE category=? AND item_name=? AND metric_date=?",
                (category, item_name, date1)
            ).fetchone()
            r2 = conn.execute(
                "SELECT * FROM business_data WHERE category=? AND item_name=? AND metric_date=?",
                (category, item_name, date2)
            ).fetchone()
        
        if not r1 or not r2:
            return {"success": False, "error": f"未找到 {date1} 或 {date2} 的数据"}
        
        d1 = dict(r1)
        d2 = dict(r2)
        v1 = d1['metric_value']
        v2 = d2['metric_value']
        
        change = v2 - v1
        change_pct = round(change / v1 * 100, 1) if v1 != 0 else 0
        arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
        
        analysis = f"""📊 {item_name} 对比分析：{date1} vs {date2}

• {date1}：{v1} {d1.get('remark', '')}
• {date2}：{v2} {d2.get('remark', '')}
• 变化：{arrow} {change:+.2f}（{change_pct:+.1f}%）

【解读】：{item_name}从 {date1} 的 {v1} {'增长' if change > 0 else '下降' if change < 0 else '持稳'} 到 {date2} 的 {v2}，幅度为 {abs(change_pct)}%。"""
        
        return {
            "success": True,
            "date1": {"date": date1, "value": v1, "remark": d1.get('remark', '')},
            "date2": {"date": date2, "value": v2, "remark": d2.get('remark', '')},
            "change": change,
            "change_pct": change_pct,
            "analysis": analysis
        }
        
    except Exception as e:
        return {"success": False, "error": f"对比分析失败: {str(e)}"}


def list_available_metrics() -> dict:
    """列出所有可分析的数据指标"""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category, item_name, COUNT(*) as cnt FROM business_data GROUP BY category, item_name ORDER BY category"
            ).fetchall()
        
        data = {}
        for r in rows:
            cat = r['category']
            if cat not in data:
                data[cat] = []
            data[cat].append({"name": r['item_name'], "records": r['cnt']})
        
        return {"success": True, "metrics": data}
        
    except Exception as e:
        return {"success": False, "error": f"查询失败: {str(e)}"}
