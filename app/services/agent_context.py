"""Read-only business tools shared by agents; personal watchlists stay in private QA."""
import re
from datetime import datetime,timedelta


def wants_watch_analysis(question):
    return bool(re.search(r'舆情|关注词|风险词|问题词|敏感词|词库|监测|关键词.*命中|命中.*关键词',question))


def is_business_question(question):
    return wants_watch_analysis(question) or bool(re.search(r'新闻|采集|资料库|数据源|正文',question))


def retrieval_question(question,user_id=None):
    if re.search(r'系统总览|大屏|系统数据',question) or (wants_watch_analysis(question) and not user_id):
        dates=re.findall(r'20\d{2}[-年/]\d{1,2}[-月/]\d{1,2}日?|最近\d+天|最新|最近|近期|今天|今日|昨天|本周',question)
        return '至'.join(dates)+'新闻'
    return question


def watch_context(question,user_id,retrieval):
    from app.services.keyword_watch import saved_watchlist,match_news
    from app.services.news_qa import current_time
    if not user_id:
        return {'available':False,'reason':'群聊不读取任何人的个人词库。个人关键词监测请在 AI 问数中进行。'},None
    bank=saved_watchlist(user_id)
    if not bank['keywords']:
        return {'available':False,'reason':'当前用户尚未设置关注词库，请先在舆情洞察中添加关键词。'},[]
    start=retrieval.get('start',current_time().isoformat())[:10]
    end=(datetime.fromisoformat(retrieval['end_exclusive'])-timedelta(days=1)).strftime('%Y-%m-%d') if retrieval.get('end_exclusive') else start
    result=match_news(bank['keywords'],start_date=start,end_date=end,limit=6,levels=bank['levels'])
    priority=[word for word in bank['keywords'] if bank['levels'].get(word) in ('风险词','问题词')]
    items=result['items']
    if priority:
        focused=match_news(priority,start_date=start,end_date=end,limit=6,levels=bank['levels'])
        unique={item['id']:item for item in focused['items']}
        for item in items:
            if item['id'] not in unique:unique[item['id']]=item
        items=list(unique.values())[:6]
    sources=[]
    for i,item in enumerate(items):
        sources.append({'number':i+1,'id':item['id'],'title':item['title'],'url':item['url'],'source_name':item['source_name'],'collected_at':item['collected_at'],'content_kind':item['content_kind'],'excerpt':'\n'.join(p['field']+'：'+p['text'] for p in item['passages'])[:1800]})
    data={'available':True,'start_date':start,'end_date':end,'keywords':bank['keywords'],'keyword_stats':result['keyword_stats'],'matched_count':result['count'],'scanned_count':result['scanned_count'],'shown_count':len(sources),'rule':'词类型由用户设置；词语命中是核查线索，不等于已确认风险。'}
    return data,sources
