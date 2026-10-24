"""智能舆情分析 - 数据仓库层"""
from app.models.db import get_connection


class SentimentRepository:

    @staticmethod
    def get_all_spy_data(limit=200):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, source_id, keyword, title, url, summary, create_at FROM spy_data ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_all_chat_messages(limit=200):
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT cm.id, cm.session_id, cm.role, cm.content, cm.create_at,
                          cs.title as session_title, u.username
                   FROM chat_messages cm
                   LEFT JOIN chat_sessions cs ON cm.session_id = cs.id
                   LEFT JOIN users u ON cs.user_id = u.id
                   ORDER BY cm.id DESC LIMIT ?""",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def store_analysis_result(source_type, source_id, content, risk_level, keywords, summary, analysis_result, analyzed_at=None):
        with get_connection() as conn:
            if analyzed_at:
                c = conn.execute(
                    """INSERT INTO sentiment_reports
                       (source_type, source_id, content, risk_level, keywords, summary, analysis_result, analyzed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (source_type, source_id, content, risk_level, keywords, summary, analysis_result, analyzed_at)
                )
            else:
                c = conn.execute(
                    """INSERT INTO sentiment_reports
                       (source_type, source_id, content, risk_level, keywords, summary, analysis_result)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (source_type, source_id, content, risk_level, keywords, summary, analysis_result)
                )
            conn.commit()
            return c.lastrowid

    @staticmethod
    def store_batch(results):
        """批量存储分析结果，保留原始数据的时间戳用于风险趋势图表"""
        ids = []
        for r in results:
            ids.append(SentimentRepository.store_analysis_result(
                r.get('source_type', 'spy_data'),
                r.get('source_id', 0),
                r.get('content', ''),
                r.get('risk_level', 'low'),
                r.get('keywords', ''),
                r.get('summary', ''),
                r.get('analysis_result', ''),
                r.get('analyzed_at', None)
            ))
        return ids

    @staticmethod
    def get_all_reports(page=1, limit=50):
        offset = (page - 1) * limit
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sentiment_reports ORDER BY analyzed_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
            total = conn.execute("SELECT COUNT(1) as cnt FROM sentiment_reports").fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def get_risk_distribution():
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT risk_level, COUNT(1) as cnt FROM sentiment_reports
                   GROUP BY risk_level
                   ORDER BY CASE risk_level
                     WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                     WHEN 'medium' THEN 3 WHEN 'low' THEN 4 ELSE 5 END"""
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_risk_trend():
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT date(analyzed_at) as day, risk_level, COUNT(1) as cnt
                   FROM sentiment_reports GROUP BY date(analyzed_at), risk_level
                   ORDER BY day ASC"""
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_source_distribution():
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT source_type, risk_level, COUNT(1) as cnt
                   FROM sentiment_reports GROUP BY source_type, risk_level"""
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_topic_risk_matrix():
        """主题-风险交叉分析矩阵：按主题统计各级风险数量"""
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT keywords, risk_level, COUNT(1) as cnt
                   FROM sentiment_reports GROUP BY keywords, risk_level"""
            ).fetchall()
        # 从 keywords 中提取主题（主题是最后一个逗号后的内容）
        topic_risk = {}  # {topic: {critical, high, medium, low}}
        for r in rows:
            keywords = (r["keywords"] or "").split(",")
            topic = keywords[-1].strip() if keywords else "综合"
            if topic not in topic_risk:
                topic_risk[topic] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            topic_risk[topic][r["risk_level"]] = topic_risk[topic].get(r["risk_level"], 0) + int(r["cnt"])
        # 转为列表并排序（按风险总数降序）
        result = []
        for topic, risks in topic_risk.items():
            result.append({
                "topic": topic,
                "critical": risks["critical"],
                "high": risks["high"],
                "medium": risks["medium"],
                "low": risks["low"],
                "total": sum(risks.values()),
            })
        result.sort(key=lambda x: -x["total"])
        return result

    @staticmethod
    def get_stats():
        with get_connection() as conn:
            total = conn.execute("SELECT COUNT(1) as cnt FROM sentiment_reports").fetchone()["cnt"]
            critical = conn.execute(
                "SELECT COUNT(1) as cnt FROM sentiment_reports WHERE risk_level='critical'"
            ).fetchone()["cnt"]
            high = conn.execute(
                "SELECT COUNT(1) as cnt FROM sentiment_reports WHERE risk_level='high'"
            ).fetchone()["cnt"]
            spy_count = conn.execute("SELECT COUNT(1) as cnt FROM spy_data").fetchone()["cnt"]
            chat_count = conn.execute("SELECT COUNT(1) as cnt FROM chat_messages").fetchone()["cnt"]
        return {
            "total_reports": total,
            "critical": critical,
            "high": high,
            "spy_data_count": spy_count,
            "chat_data_count": chat_count,
        }
