"""智能舆情分析 - 控制器层"""
import tornado.web
import asyncio
import json
from app.controllers.base import BaseHandler
from app.models.sentiment import SentimentRepository
from app.models.db import get_connection
from app.services.keyword_watch import saved_keywords, saved_watchlist, save_keywords, match_news
from app.services.news_qa import current_time


class SentimentPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        stats = SentimentRepository.get_stats()
        self.render("sentiment/list.html", title="智能舆情", stats=stats)


class SentimentApiHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        action = self.get_argument("action", "stats")
        if action == 'watchlist':
            self.write({'code':0,'data':{**saved_watchlist(self.current_user['id']),'date':current_time().strftime('%Y-%m-%d'),'timezone':'Asia/Shanghai'}})
        elif action == "stats":
            stats = SentimentRepository.get_stats()
            self.write({"code": 0, "data": stats})
        elif action == "reports":
            page = int(self.get_argument("page", 1))
            limit = int(self.get_argument("limit", 50))
            rows, total = SentimentRepository.get_all_reports(page, limit)
            self.write({"code": 0, "data": rows, "count": total})
        elif action == "distribution":
            dist = SentimentRepository.get_risk_distribution()
            self.write({"code": 0, "data": dist})
        elif action == "trend":
            trend = SentimentRepository.get_risk_trend()
            self.write({"code": 0, "data": trend})
        elif action == "source_dist":
            src = SentimentRepository.get_source_distribution()
            self.write({"code": 0, "data": src})
        elif action == "topic_risk":
            data = SentimentRepository.get_topic_risk_matrix()
            self.write({"code": 0, "data": data})
        else:
            self.write({"code": 1, "msg": "未知操作"})

    @tornado.web.authenticated
    async def post(self):
        payload = {}
        if self.request.headers.get('Content-Type','').startswith('application/json'):
            try:
                payload = json.loads(self.request.body)
                if not isinstance(payload,dict):
                    raise ValueError()
            except (ValueError,UnicodeDecodeError):
                self.set_status(400)
                self.write({'code':1,'msg':'请求内容必须为 JSON 对象'})
                return
        action = payload.get('action') or self.get_argument("action", "analyze")
        if action in ('save_watchlist','match_news'):
            try:
                value = lambda key,default=None: payload.get(key,self.get_argument(key,default))
                if action == 'save_watchlist':
                    words = await asyncio.to_thread(save_keywords,self.current_user['id'],value('keywords',[]),value('levels'))
                    self.write({'code':0,'msg':'关键词库已保存','data':{'keywords':words}})
                else:
                    words = value('keywords')
                    if words is None:
                        words = await asyncio.to_thread(saved_keywords,self.current_user['id'])
                    levels=value('levels')
                    if levels is None:
                        levels=(await asyncio.to_thread(saved_watchlist,self.current_user['id']))['levels']
                    result = await asyncio.to_thread(match_news,words,value('date'),value('mode','any'),int(value('page',1)),int(value('limit',12)),value('start_date'),value('end_date'),levels)
                    self.write({'code':0,'data':result})
            except (ValueError,TypeError) as exc:
                self.set_status(400)
                self.write({'code':1,'msg':str(exc)})
            return
        if action == "analyze":
            self._run_analysis()
        elif action == "clear":
            with get_connection() as conn:
                conn.execute("DELETE FROM sentiment_reports")
                conn.commit()
            self.write({"code": 0, "msg": "已清除所有分析结果"})
        else:
            self.write({"code": 1, "msg": "未知操作"})

    def _run_analysis(self):
        """基于规则的真实新闻舆情风险分析"""

        # ===== 扩展风险关键词库（覆盖真实新闻场景） =====
        risk_patterns = {
            "critical": [
                # 网络安全/攻击
                "数据泄露", "安全漏洞", "系统崩溃", "病毒攻击", "勒索",
                "严重故障", "数据丢失", "入侵", "黑客", "瘫痪",
                "重大事故", "宕机", "崩溃", "攻击", "勒索软件",
                "零日漏洞", "APT攻击", "供应链攻击", "深度伪造",
                # 社会/经济危机
                "经济危机", "金融危机", "股市崩盘", "大规模裁员",
                "破产", "倒闭", "债务违约", "信用危机",
                # 重大安全事件
                "特大安全事故", "矿难", "重大火灾", "爆炸事故",
                "放射性泄漏", "危险品泄漏",
            ],
            "high": [
                # 网络/技术风险
                "异常", "告警", "故障", "漏洞", "风险", "威胁",
                "违规", "处罚", "罚款", "投诉", "举报",
                "警告", "错误", "失败", "超时", "拒绝服务",
                "恶意软件", "钓鱼", "木马", "后门",
                # 政策/监管风险
                "监管", "调查", "审查", "制裁", "反垄断",
                "约谈", "整改", "下架", "停牌",
                # 市场/行业风险
                "下滑", "萎缩", "衰退", "通胀", "加息",
                "制裁", "脱钩", "贸易摩擦", "出口管制",
                # 技术/行业压力
                "召回", "停产", "供应链中断", "订单下降",
            ],
            "medium": [
                "问题", "延迟", "波动", "下降", "不稳定", "bug",
                "缺陷", "待优化", "需关注", "建议", "提醒",
                "异常波动", "偏离", "告警阈值",
                "调整", "转型", "挑战", "竞争", "压力",
                "放缓", "降温", "回落",
            ],
            "low": [
                "正常", "稳定", "良好", "优化", "提升",
                "增长", "改善", "完成", "成功", "达标",
                "突破", "创新", "领先", "上线", "发布",
                "合作", "签约", "投资", "融资", "上市",
                "利好", "回暖", "复苏", "新高",
            ]
        }

        # ===== 主题分类关键词 =====
        topic_patterns = {
            "网络安全": ["网络安全", "数据安全", "黑客", "漏洞", "攻击", "病毒", "勒索", "入侵", "泄露", "防火墙", "加密"],
            "AI技术": ["人工智能", "AI", "大模型", "机器学习", "深度学习", "GPT", "LLM", "神经网络", "算法", "智能体"],
            "芯片半导体": ["芯片", "半导体", "集成电路", "光刻", "晶圆", "CPU", "GPU", "EUV", "制程", "封装"],
            "新能源": ["新能源", "光伏", "风电", "储能", "锂电", "氢能", "碳中和", "碳排放", "绿色能源", "可再生能源"],
            "数字经济": ["数字经济", "数字化", "数智化", "产业互联网", "智能制造", "工业互联网", "新基建", "数字人民币"],
            "汽车产业": ["自动驾驶", "智能驾驶", "新能源车", "电动车", "动力电池", "充电桩", "车路协同", "智能座舱"],
            "政策法规": ["政策", "法规", "条例", "监管", "国务院", "发改委", "工信部", "央行", "政治局", "政府"],
            "社会民生": ["教育", "医疗", "养老", "住房", "就业", "社保", "医保", "双减", "人口", "生育"],
            "国际关系": ["中美", "制裁", "贸易", "关税", "地缘", "G7", "G20", "联合国", "一带一路", "出口管制"],
            "资本市场": ["股市", "A股", "IPO", "上市", "融资", "基金", "债券", "期货", "市值", "估值"],
        }

        results = []

        # 分析瞭望采集数据（使用真实扒取的新闻）
        spy_rows = SentimentRepository.get_all_spy_data(200)
        print(f"[舆情分析] 正在分析 {len(spy_rows)} 条瞭望数据...")
        for row in spy_rows:
            title = row.get("title", "")
            summary = (row.get("summary", "") or "")
            text = (title + " " + summary).lower()

            risk_level = self._detect_risk_level(text, risk_patterns)
            risk_keywords = self._extract_keywords(text, risk_patterns)

            # 识别主题
            topic = self._classify_topic(title + " " + summary, topic_patterns)

            # 构建有价值的分析摘要
            analysis = f"[{topic}] 风险等级: {risk_level}"
            if risk_keywords:
                analysis += f"，敏感词: {', '.join(risk_keywords[:5])}"
            if summary:
                analysis += f"，摘要: {summary[:100]}"

            results.append({
                "source_type": "spy_data",
                "source_id": row["id"],
                "content": title,
                "risk_level": risk_level,
                "keywords": ",".join(risk_keywords[:8] + [topic]),
                "summary": summary[:300],
                "analysis_result": analysis[:500],
                "analyzed_at": row.get("create_at", None),  # 使用原始数据时间戳
            })

        # 分析对话数据
        chat_rows = SentimentRepository.get_all_chat_messages(100)
        print(f"[舆情分析] 正在分析 {len(chat_rows)} 条对话数据...")
        for row in chat_rows:
            text = (row.get("content", "") or "").lower()
            risk_level = self._detect_risk_level(text, risk_patterns)
            keywords = self._extract_keywords(text, risk_patterns)
            topic = self._classify_topic(row.get("content", "") or "", topic_patterns)

            results.append({
                "source_type": "chat_data",
                "source_id": row["id"],
                "content": (row.get("content", "") or "")[:120],
                "risk_level": risk_level,
                "keywords": ",".join(keywords[:5] + [topic]),
                "summary": f"用户 {row.get('username', '未知')} 在会话中涉及",
                "analysis_result": f"[{topic}] 对话风险等级: {risk_level}",
                "analyzed_at": row.get("create_at", None),  # 使用原始数据时间戳
            })

        # 先清除旧分析结果，再批量写入新结果
        if results:
            with get_connection() as conn:
                conn.execute("DELETE FROM sentiment_reports")
                conn.commit()
            ids = SentimentRepository.store_batch(results)
            # 统计
            critical_cnt = sum(1 for r in results if r['risk_level'] == 'critical')
            high_cnt = sum(1 for r in results if r['risk_level'] == 'high')
            medium_cnt = sum(1 for r in results if r['risk_level'] == 'medium')
            low_cnt = sum(1 for r in results if r['risk_level'] == 'low')
            print(f"[舆情分析] 完成！严重={critical_cnt} 高={high_cnt} 中={medium_cnt} 低={low_cnt} 共{len(results)}条")
            self.write({
                "code": 0,
                "msg": f"分析完成！共处理 {len(results)} 条数据 | 严重:{critical_cnt} 高:{high_cnt} 中:{medium_cnt} 低:{low_cnt}",
                "data": {"total": len(results), "critical": critical_cnt, "high": high_cnt, "medium": medium_cnt, "low": low_cnt}
            })
        else:
            self.write({"code": 1, "msg": "当前没有可分析的数据，请先通过瞭望采集获取真实新闻"})

    @staticmethod
    def _detect_risk_level(text, patterns):
        for level in ["critical", "high", "medium"]:
            for kw in patterns[level]:
                if kw.lower() in text:
                    return level
        return "low"

    @staticmethod
    def _extract_keywords(text, patterns):
        found = []
        for level in ["critical", "high", "medium", "low"]:
            for kw in patterns[level]:
                if kw.lower() in text:
                    found.append(kw)
        return list(dict.fromkeys(found))  # 去重保序

    @staticmethod
    def _classify_topic(text, topic_patterns):
        """基于关键词匹配识别新闻主题分类"""
        text_lower = text.lower()
        scores = {}
        for topic, keywords in topic_patterns.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            if score > 0:
                scores[topic] = score
        if scores:
            # 返回得分最高的主题
            return max(scores, key=scores.get)
        return "综合"
