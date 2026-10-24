"""数据分析 API —— 供技能系统调用，查询项目业务数据"""

import tornado.web
from app.controllers.base import BaseHandler
from app.services.data_analyzer import get_trend_analysis, get_category_summary, compare_periods, list_available_metrics


ROUTE_MAP = {
    # (关键词1, 关键词2) -> (action, params)
    ("用户", "趋势"): ("trend", {"category": "user_metrics", "item_name": "月活跃用户数"}),
    ("活跃", "趋势"): ("trend", {"category": "user_metrics", "item_name": "月活跃用户数"}),
    ("用户", "增长"): ("trend", {"category": "user_metrics", "item_name": "月活跃用户数"}),
    ("销售", "趋势"): ("trend", {"category": "sales", "item_name": "月度销售额(万元)"}),
    ("销售额", "趋势"): ("trend", {"category": "sales", "item_name": "月度销售额(万元)"}),
    ("销售", "增长"): ("trend", {"category": "sales", "item_name": "月度销售额(万元)"}),
    ("销售", "区域"): ("overview", {}),
    ("产品", "销量"): ("trend", {"category": "product", "item_name": "智能硬件"}),
    ("产品", "分类"): ("overview", {}),
    ("客户", "满意度"): ("trend", {"category": "customer", "item_name": "客户满意度"}),
    ("满意度", "趋势"): ("trend", {"category": "customer", "item_name": "客户满意度"}),
    ("系统", "运行"): ("trend", {"category": "system", "item_name": "AI调用次数"}),
    ("AI", "调用"): ("trend", {"category": "system", "item_name": "AI调用次数"}),
    ("概览",): ("overview", {}),
    ("全貌",): ("overview", {}),
    ("指标",): ("metrics", {}),
    ("有哪些",): ("metrics", {}),
    ("区域",): ("overview", {}),
}


def _auto_route(query: str) -> dict:
    """根据自然语言查询自动路由到对应的分析操作
    
    Args:
        query: 用户输入的自然语言问题
    
    Returns:
        {"action": "xxx", "params": {...}}
    """
    # 简易关键词匹配
    best_match = None
    best_score = 0
    
    for keywords, (action, params) in ROUTE_MAP.items():
        score = sum(1 for kw in keywords if kw in query)
        if score > best_score:
            best_score = score
            best_match = (action, params)
    
    if best_match and best_score >= 1:
        action, params = best_match
        return {"action": action, "params": params}
    
    # 默认：返回概览
    return {"action": "overview", "params": {}}


class DataAnalysisApiHandler(BaseHandler):
    """数据分析 API 接口（内部数据只读，安全性可控）
    
    支持的 action：
    - auto: 智能路由，根据自然语言自动选择分析
    - metrics: 列出所有可分析指标
    - overview: 获取最新一期全类别概览
    - trend: 趋势分析（需 category + item_name）
    - compare: 两期对比（需 category + item_name + date1 + date2）
    """
    
    check_xsrf = False  # API 调用不需要 xsrf

    def get(self):
        action = self.get_argument("action", "overview")
        query = self.get_argument("q", None) or self.get_argument("query", None)
        
        # auto 模式：根据自然语言智能路由
        if action == "auto":
            if not query:
                result = {"success": False, "error": "请提供查询问题（q参数）"}
            else:
                route = _auto_route(query)
                action = route["action"]
                # 合并参数
                params = dict(route["params"])
                if action == "trend":
                    result = get_trend_analysis(
                        params.get("category", ""),
                        params.get("item_name", "")
                    )
                elif action == "metrics":
                    result = list_available_metrics()
                elif action == "overview":
                    result = get_category_summary()
                else:
                    result = get_category_summary()
            
            self.set_header("Content-Type", "application/json")
            self.write(result)
            return
        
        category = self.get_argument("category", None)
        item_name = self.get_argument("item_name", None)
        date1 = self.get_argument("date1", None)
        date2 = self.get_argument("date2", None)
        
        if action == "metrics":
            result = list_available_metrics()
        elif action == "overview":
            date = self.get_argument("date", None)
            result = get_category_summary(date)
        elif action == "trend":
            if not category or not item_name:
                result = {"success": False, "error": "缺少 category 或 item_name 参数"}
            else:
                result = get_trend_analysis(category, item_name)
        elif action == "compare":
            if not category or not item_name or not date1 or not date2:
                result = {"success": False, "error": "缺少对比参数"}
            else:
                result = compare_periods(category, item_name, date1, date2)
        else:
            result = {"success": False, "error": f"未知操作: {action}"}
        
        self.set_header("Content-Type", "application/json")
        self.write(result)


class DataAnalysisPageHandler(BaseHandler):
    """数据分析页面"""
    
    @tornado.web.authenticated
    def get(self):
        self.render("data_analysis/view.html", title="数据分析")
