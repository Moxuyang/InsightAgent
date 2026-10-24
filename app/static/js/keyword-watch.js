(function () {
  'use strict';
  const root=document.getElementById('keywordWatch');
  if(!root)return;
  const $=id=>document.getElementById(id);
  let keywords=[],levels=Object.create(null),today="",version=0,lastQuery=null;
  function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;}
  async function api(action,body){
    const response=await fetch('/api/sentiment'+(body?'':'?action='+action),body?{method:'POST',headers:{'Content-Type':'application/json','X-XSRFToken':root.dataset.xsrf},body:JSON.stringify({action,...body})}:{});
    let result;try{result=await response.json();}catch(_){throw new Error('会话失效或服务暂不可用，请刷新后重试。');}
    if(!response.ok||result.code!==0)throw new Error(result.msg||'请求失败，请重试。');
    return result.data;
  }
  function notice(message){$('kwStatus').textContent=message;}
  function empty(title,description){const area=$('kwResults');area.replaceChildren();const box=el('div','kw-empty');box.append(el('span','kw-empty-symbol','⌕'),el('h3','',title),el('p','',description));area.append(box);}
  function invalidate(){version++;lastQuery=null;$('kwPrev').disabled=true;$('kwNext').disabled=true;$('kwCount').textContent='等待查询';$('kwRange').textContent='';$('kwOverview').hidden=true;$('kwAnalyze').hidden=true;empty('查询条件已更新','点击“保存并匹配”，查看新的匹配结果。');notice('关键词或日期已修改，尚未查询');}
  function drawKeywords(){
    $('kwChips').replaceChildren();
    keywords.forEach(word=>{const chip=el('span','kw-chip');chip.append(el('span','',word));const category=el('select','kw-chip-category');category.setAttribute('aria-label',word+'的词类型');['关注词','风险词','问题词'].forEach(name=>{const option=el('option','',name);option.value=name;category.append(option);});category.value=levels[word]||'关注词';category.onchange=()=>{levels[word]=category.value;invalidate();};chip.append(category);const remove=el('button','','×');remove.type='button';remove.setAttribute('aria-label','移除关键词 '+word);remove.onclick=()=>{keywords=keywords.filter(x=>x!==word);delete levels[word];drawKeywords();invalidate();};chip.append(remove);$('kwChips').append(chip);});
    $('kwLibraryCount').textContent=keywords.length+' / 100';
    $('kwChips').hidden=!keywords.length;
  }
  function addKeywords(){
    const words=$('kwInput').value.split(/[,，、;；\n\r]+/).map(x=>x.trim()).filter(Boolean);
    if(words.some(x=>x.length>40)){notice('每个关键词最多 40 个字');return false;}
    const next=[...keywords],seen=new Set(keywords.map(x=>x.toLowerCase()));
    words.forEach(word=>{if(!seen.has(word.toLowerCase())){seen.add(word.toLowerCase());next.push(word);}});
    if(next.length>100){notice('最多添加 100 个关键词');return false;}
    if(words.length){keywords=next;$('kwInput').value='';drawKeywords();invalidate();}
    return true;
  }
  function highlighted(text,words){
    const node=el('span');
    const expression=new RegExp(words.map(w=>w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).sort((a,b)=>b.length-a.length).join('|'),'gi');
    let offset=0,match;
    while((match=expression.exec(text))!==null){node.append(document.createTextNode(text.slice(offset,match.index)),el('mark','',match[0]));offset=match.index+match[0].length;}
    node.append(document.createTextNode(text.slice(offset)));return node;
  }
  function render(data){
    const area=$('kwResults');area.replaceChildren();
    $('kwCount').textContent='命中 '+data.count+' 条 / 阶段内采集 '+data.scanned_count+' 条';
    $('kwRange').textContent=data.start_date+' 至 '+data.end_date+' · 北京时间 · '+(data.mode==='all'?'同时包含全部词':'包含任意一个词');
    renderOverview(data);
    const task='请分析'+data.start_date+'至'+data.end_date+'我的舆情关注词监测结果，说明风险词、问题词分别命中了哪些新闻，引用来源，区分词语命中与已核实风险。';
    $('kwAnalyze').href='/user_dashboard?'+new URLSearchParams({question:task});$('kwAnalyze').hidden=false;
    $('kwPage').textContent=data.page+' / '+Math.max(1,Math.ceil(data.count/data.limit));
    $('kwPrev').disabled=data.page<=1;$('kwNext').disabled=data.page*data.limit>=data.count;
    if(!data.items.length){empty(data.scanned_count?'所选阶段没有匹配的新闻':'所选阶段没有采集新闻',data.scanned_count?'调整关键词或匹配方式后再查询。':'可以切换日期，或先前往瞭望采集获取新闻。');return;}
    const categories=new Map((data.keyword_stats||[]).map(stat=>[stat.keyword,stat.category]));
    data.items.forEach(item=>{
      const card=el('article','kw-news');
      const meta=el('div','kw-news-meta');meta.append(el('span','kw-source',item.source_name),el('span','',item.content_kind),el('time','',item.collected_at));
      const title=el('h3');title.append(highlighted(item.title||'未命名新闻',item.matched_keywords));
      const hits=el('div','kw-hits');hits.append(el('small','','命中关键词'));item.matched_keywords.forEach(word=>{const category=categories.get(word)||'关注词';const tag=el('span','',word+' · '+category);tag.dataset.category=category;hits.append(tag);});
      card.append(meta,title,hits);
      item.passages.filter(p=>p.field!=='标题').slice(0,6).forEach(p=>{const quote=el('p','kw-passage');quote.append(el('small','',p.field+'片段'),highlighted(p.text,item.matched_keywords));card.append(quote);});
      const footer=el('footer');footer.append(el('span','','关键词命中线索'));
      try{const url=new URL(item.url);if(['https:','http:'].includes(url.protocol)){const link=el('a','','查看原文 ↗');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';footer.append(link);}}catch(_){}
      card.append(footer);area.append(card);
    });
  }
  async function run(page=1,save=true){
    if(save&&!addKeywords())return;
    if(!keywords.length){notice('请先添加至少一个关键词');$('kwInput').focus();return;}
    if(!$('kwStartDate').value||!$('kwEndDate').value){notice('请选择起止日期');return;}
    if($('kwStartDate').value>$('kwEndDate').value){notice('结束日期不能早于开始日期');return;}
    const query=save?{keywords:[...keywords],start_date:$('kwStartDate').value,end_date:$('kwEndDate').value,levels:{...levels},mode:$('kwMode').value}:lastQuery||{keywords:[...keywords],start_date:$('kwStartDate').value,end_date:$('kwEndDate').value,levels:{...levels},mode:$('kwMode').value};
    const token=++version;
    $('kwRun').disabled=true;$('kwPrev').disabled=true;$('kwNext').disabled=true;
    $('kwResults').setAttribute('aria-busy','true');notice('正在匹配新闻标题、摘要与正文…');
    try{
      if(save)await api('save_watchlist',{keywords:query.keywords,levels:query.levels});
      if(token!==version)return;
      const data=await api('match_news',{...query,page,limit:12});
      if(token!==version)return;
      lastQuery=query;lastQuery.page=page;render(data);notice('匹配完成'+(save?' · 关键词库已保存':''));
    }catch(error){if(token===version){notice(error.message);empty('本次查询未完成',error.message);}}
    finally{$('kwRun').disabled=false;$('kwResults').removeAttribute('aria-busy');}
  }
  function renderOverview(data){
    $('kwOverview').hidden=false;
    $('kwMetricNews').textContent=data.count;
    const stats=data.keyword_stats||[];
    $('kwMetricRisk').textContent=stats.filter(s=>s.category==='风险词'&&s.news_count>0).length;
    $('kwMetricProblem').textContent=stats.filter(s=>s.category==='问题词'&&s.news_count>0).length;
    const list=$('kwWordStats');list.replaceChildren();
    stats.forEach(stat=>{const row=el('div','kw-word-stat');row.dataset.category=stat.category;const head=el('div');head.append(el('strong','',stat.keyword),el('span','kw-word-category',stat.category),el('small','',stat.news_count+' 篇新闻'));const bar=el('div','kw-word-track'),fill=el('span');fill.style.width=(data.count?Math.min(100,stat.news_count/data.count*100):0)+'%';bar.append(fill);row.append(head,bar);list.append(row);});
  }
  function quickRange(kind){
    if(!today)return;
    let start=today;
    if(kind==='week'){const day=new Date(today+'T00:00:00Z');day.setUTCDate(day.getUTCDate()-6);start=day.toISOString().slice(0,10);}
    if(kind==='month')start=today.slice(0,8)+'01';
    $('kwStartDate').value=start;$('kwEndDate').value=today;invalidate();
  }
  document.querySelectorAll('[data-watch-range]').forEach(button=>button.onclick=()=>quickRange(button.dataset.watchRange));
  $('kwAdd').onclick=addKeywords;
  $('kwSave').onclick=async()=>{
    if(!addKeywords())return;
    $('kwSave').disabled=true;
    try{await api('save_watchlist',{keywords:[...keywords],levels:{...levels}});notice(keywords.length?'关键词库已保存':'关键词库已清空');}
    catch(error){notice(error.message);}
    finally{$('kwSave').disabled=false;}
  };
  $('kwInput').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();addKeywords();}});
  $('kwForm').onsubmit=event=>{event.preventDefault();run();};
  $('kwStartDate').onchange=invalidate;$('kwEndDate').onchange=invalidate;$('kwMode').onchange=invalidate;
  $('kwPrev').onclick=()=>run(Math.max(1,lastQuery.page-1),false);$('kwNext').onclick=()=>run(lastQuery.page+1,false);
  empty('从你关心的关键词开始','添加企业名称、事件或敏感词，查看指定日期采集新闻中的匹配线索。');
  api('watchlist').then(data=>{keywords=data.keywords;levels=Object.assign(Object.create(null),data.levels||{});today=data.date;$('kwStartDate').value=data.date;$('kwEndDate').value=data.date;drawKeywords();notice('关键词库已加载');if(keywords.length)run(1,false);}).catch(error=>notice(error.message));
})();
