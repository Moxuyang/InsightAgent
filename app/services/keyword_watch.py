"""User-owned literal keyword watchlists and date-scoped news matching."""
import json
import re
from datetime import datetime, timedelta, timezone

from app.models.db import get_connection
from app.models.system_config import SystemConfigRepository
from app.services.news_qa import CHINA, current_time


def normalize_keywords(value):
    if isinstance(value,str):
        value = re.split(r'[,，、;；\n\r]+',value)
    if not isinstance(value,list):
        raise ValueError('关键词必须为列表或用逗号、换行分隔的文本')
    result, seen = [], set()
    for keyword in value:
        if not isinstance(keyword,str):
            raise ValueError('每个关键词必须是文本')
        keyword = keyword.strip()
        if not keyword:
            continue
        if len(keyword)>40:
            raise ValueError('每个关键词最多 40 个字')
        key = keyword.lower()
        if key not in seen:
            seen.add(key)
            result.append(keyword)
    if len(result)>100:
        raise ValueError('最多保存 100 个关键词')
    return result


def saved_watchlist(user_id):
    row = SystemConfigRepository.get_by_key(f'sentiment_watchlist_{int(user_id)}')
    value = json.loads(row['config_value']) if row else []
    words = normalize_keywords(value.get('keywords',[]) if isinstance(value,dict) else value)
    levels = value.get('levels',{}) if isinstance(value,dict) else {}
    return {'keywords':words,'levels':{w:levels.get(w,'关注词') for w in words}}


def saved_keywords(user_id):
    return saved_watchlist(user_id)['keywords']


def save_keywords(user_id,keywords,levels=None):
    words = normalize_keywords(keywords)
    levels = levels if levels is not None else saved_watchlist(user_id)['levels']
    if not isinstance(levels,dict) or any(v not in ('关注词','风险词','问题词') for v in levels.values()):
        raise ValueError('关键词标签必须为关注词、风险词或问题词')
    value={'keywords':words,'levels':{w:levels.get(w,'关注词') for w in words}}
    SystemConfigRepository.set_config(f'sentiment_watchlist_{int(user_id)}',json.dumps(value,ensure_ascii=False),'用户舆情关注关键词')
    return words


def match_news(keywords, day=None, mode='any', page=1, limit=12, start_date=None, end_date=None, levels=None):
    words = normalize_keywords(keywords)
    if not words:
        raise ValueError('请先添加至少一个关注关键词')
    if mode not in ('any','all'):
        raise ValueError('匹配方式必须为 any 或 all')
    if not isinstance(page,int) or not isinstance(limit,int) or page<1 or not 1<=limit<=50:
        raise ValueError('分页参数无效')
    day = start_date or day or current_time().strftime('%Y-%m-%d')
    last_day = end_date or day
    try:
        start = datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=CHINA)
        last = datetime.strptime(last_day,'%Y-%m-%d').replace(tzinfo=CHINA)
    except (ValueError,TypeError):
        raise ValueError('请选择有效日期，格式为 YYYY-MM-DD')
    if last < start:
        raise ValueError('结束日期不能早于开始日期')
    end = last+timedelta(days=1)
    base = ''' FROM spy_data d LEFT JOIN spy_sources s ON s.id=d.source_id
        LEFT JOIN deep_collect_results r ON r.id=(SELECT MAX(x.id) FROM deep_collect_results x
            WHERE x.spy_data_id=d.id AND x.crawl_status='success') '''
    discovery = 'COALESCE(d.update_at,d.create_at)'
    full = 'COALESCE(r.crawl_at,r.create_at,d.create_at)'
    timestamp = f'CASE WHEN {discovery}>{full} THEN {discovery} ELSE {full} END'
    with get_connection() as conn:
        tz = timezone.utc
        if getattr(conn,'db_type','sqlite') == 'mysql':
            seconds = conn.execute('SELECT TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(),NOW()) AS offset_seconds').fetchone()['offset_seconds']
            tz = timezone(timedelta(seconds=int(seconds)))
            timestamp = f'CAST(({timestamp}) AS DATETIME)'
        else:
            timestamp = f'datetime({timestamp})'
        bounds = [start.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S'),end.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S')]
        dated = f' WHERE {timestamp}>=? AND {timestamp}<?'
        scanned = conn.execute('SELECT COUNT(*) AS count'+base+dated,bounds).fetchone()['count']
        predicates, parameters = [], []
        for word in words:
            # Literal matching: percent/underscore are not SQL wildcard operators.
            literal = '%'+word.lower().replace('!','!!').replace('%','!%').replace('_','!_')+'%'
            predicates.append("(LOWER(d.title) LIKE ? ESCAPE '!' OR LOWER(d.summary) LIKE ? ESCAPE '!' OR LOWER(r.full_content) LIKE ? ESCAPE '!')")
            parameters.extend([literal]*3)
        where = dated+' AND ('+(' OR ' if mode=='any' else ' AND ').join(predicates)+')'
        count = conn.execute('SELECT COUNT(*) AS count'+base+where,bounds+parameters).fetchone()['count']
        # Aggregate all matches in SQL, independently of the visible result page.
        counters = ','.join('SUM(CASE WHEN '+p+f' THEN 1 ELSE 0 END) AS k{i}' for i,p in enumerate(predicates))
        totals = conn.execute('SELECT '+counters+base+where,parameters+bounds+parameters).fetchone()
        levels = levels if isinstance(levels,dict) else {}
        keyword_stats = [{'keyword':w,'category':levels.get(w,'关注词') if levels.get(w,'关注词') in ('关注词','风险词','问题词') else '关注词','news_count':int(totals[f'k{i}'] or 0)} for i,w in enumerate(words)]
        keyword_stats.sort(key=lambda x:x['news_count'],reverse=True)
        rows = conn.execute('SELECT d.id,d.title,d.url,d.summary,s.name AS source_name,r.full_content,'+timestamp+' AS collected_at'+base+where+' ORDER BY collected_at DESC,d.id DESC LIMIT ? OFFSET ?',bounds+parameters+[limit,(page-1)*limit]).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        fields = [('标题',item.get('title') or ''),('摘要',item.get('summary') or ''),('正文',item.get('full_content') or '')]
        hits = [w for w in words if any(w.lower() in text.lower() for _,text in fields)]
        passages = []
        for label,text in fields:
            positions = [(text.lower().find(w.lower()),w) for w in hits if w.lower() in text.lower()]
            if not positions:
                continue
            # Show a passage for each keyword, merging nearby matching spans.
            windows = []
            for pos,w in sorted(positions):
                left,right = max(0,pos-60), min(len(text),pos+len(w)+100)
                if windows and left<=windows[-1][1]:
                    windows[-1] = (windows[-1][0],max(right,windows[-1][1]))
                else:
                    windows.append((left,right))
            for left,right in windows[:3]:
                passages.append({'field':label,'text':('…' if left else '')+text[left:right]+('…' if right<len(text) else '')})
        stamp = datetime.fromisoformat(str(item['collected_at'])).replace(tzinfo=tz).astimezone(CHINA)
        items.append({'id':item['id'],'title':item['title'],'url':item['url'],'source_name':item['source_name'] or '未知来源','collected_at':stamp.strftime('%Y-%m-%d %H:%M:%S'),'matched_keywords':hits,'passages':passages,'content_kind':'正文' if item.get('full_content') else '摘要'})
    return {'items':items,'count':count,'scanned_count':scanned,'page':page,'limit':limit,'date':day,'start_date':day,'end_date':last_day,'timezone':'Asia/Shanghai','keywords':words,'keyword_stats':keyword_stats,'mode':mode}
