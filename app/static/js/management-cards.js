/* Card views use the existing management APIs and form event handlers. */
(function () {
  'use strict';
  const states = {}, handlers = {};
  const escape = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fileSize = value => { const n=Math.max(0,Number(value)||0); return n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB'; };
  const config = {
    user_file: ['文件空间','folder-open','file_name','username','file_type'],
    user_query: ['对话记录','comment-dots','query_text','username','tokens_used'],
    api_config: ['接口连接','plug','name','api_url','method'],
    user: ['团队成员','user','username','role_name','create_at'],
    role: ['角色空间','user-shield','name','code','is_system'],
    permission: ['访问权限','shield-alt','role_name','role_code','menu_names']
  };
  function emit(name, obj) { if (handlers[name]) handlers[name](obj); }
  function template(selector, data) { const el = document.querySelector(selector); return el ? layui.laytpl(el.innerHTML).render(data || {}) : ''; }
  function render(options) {
    const target = document.querySelector(options.elem), page = target.closest('[data-management]');
    const kind = page.dataset.management, id = target.id, cfg = config[kind];
    const host = document.createElement('section'); host.className = 'mc-space'; target.replaceWith(host);
    const state = states[id] = {options, host, kind, id, cfg, page:1, rows:[], selected:new Set(), keyword:'', type:'', active:null};
    host.innerHTML = '<div class="mc-overview"><div class="mc-symbol"><i class="fas fa-'+cfg[1]+'"></i></div><div><span>WORKSPACE / '+escape(cfg[0])+'</span><h2>'+escape(cfg[0])+'</h2></div><div class="mc-total"><strong>—</strong><span>条记录</span></div></div><div class="mc-toolbar"><div class="mc-actions">'+(options.toolbar ? template(options.toolbar) : '')+'</div><button type="button" class="mc-refresh">刷新</button></div><div class="mc-filters"><input type="search" aria-label="筛选本页内容" placeholder="搜索本页名称、内容或成员…"><select aria-label="筛选本页分类"><option value="">全部分类</option></select></div><div class="mc-selection"><label><input type="checkbox" class="mc-all"> 选择当前结果</label><span class="mc-selected" aria-live="polite">已选 0 项</span><span class="mc-scope">搜索与分类筛选当前页</span></div><div class="mc-grid" aria-live="polite"></div><nav class="mc-pager" aria-label="分页"><span></span><button type="button" class="mc-prev">上一页</button><button type="button" class="mc-next">下一页</button></nav>';
    host.querySelector('.mc-actions').addEventListener('click', e => { const b=e.target.closest('[lay-event]'); if(b) emit('toolbar('+id+')',{event:b.getAttribute('lay-event'),config:{id}}); });
    host.querySelector('input[type=search]').addEventListener('input', e=>{state.keyword=e.target.value.toLowerCase(); draw(state);});
    host.querySelector('select').addEventListener('change', e=>{state.type=e.target.value;draw(state);});
    host.querySelector('.mc-refresh').onclick=()=>load(state);
    host.querySelector('.mc-prev').onclick=()=>{state.page--;load(state);};
    host.querySelector('.mc-next').onclick=()=>{state.page++;load(state);};
    host.querySelector('.mc-all').onchange=e=>{visible(state).forEach(row=>e.target.checked?state.selected.add(row):state.selected.delete(row));draw(state);};
    host.querySelector('.mc-grid').addEventListener('change',e=>{if(e.target.matches('[data-select]')) { const row=state.rows[Number(e.target.dataset.select)];e.target.checked?state.selected.add(row):state.selected.delete(row);draw(state);}});
    host.querySelector('.mc-grid').addEventListener('click',e=>{const button=e.target.closest('[lay-event]');if(!button)return;const row=state.rows[Number(button.closest('[data-row]').dataset.row)];emit('tool('+id+')',{event:button.getAttribute('lay-event'),data:row,del:()=>load(state)});});
    if (!options.cols[0].some(c=>c.type==='checkbox')) host.querySelector('.mc-selection').hidden=true;
    upgrade(state);
    load(state);return {reload:()=>load(state)};
  }
  function category(s,r) { if(s.kind==='user')return r.username==='admin'?'超级管理员':String(r.role_name||'未分配角色');if(s.kind==='role')return r.is_system==1?'系统角色':'自定义角色';if(s.kind==='api_config')return r.is_active==1?'已启用':'已停用';if(s.kind==='user_query')return r.response_text?'已有回答':'暂无回答';return String(r[s.cfg[4]] || '未分类'); }
  function visible(s) {return s.rows.filter(r=>(!s.type||category(s,r)===s.type)&&(!s.keyword||[s.cfg[2],s.cfg[3],s.cfg[4]].some(k=>String(r[k]||'').toLowerCase().includes(s.keyword))));}
  function draw(s) {
    const list=visible(s), grid=s.host.querySelector('.mc-grid');
    grid.innerHTML=list.length?list.map(r=>{
      const index=s.rows.indexOf(r), title=r[s.cfg[2]]||'未命名', label=category(s,r);
      const check=s.options.cols[0].some(c=>c.type==='checkbox');
      const detail=s.kind==='user_file'?'<dl><dt>文件大小</dt><dd>'+fileSize(r.file_size)+'</dd><dt>存储位置</dt><dd>'+escape(r.file_path)+'</dd></dl>':s.kind==='permission'?'<p class="mc-description">'+escape(r.menu_names||'尚未分配访问权限')+'</p>':s.kind==='user_query'?'<p class="mc-description">'+escape(NewsQa.plainText(r.response_text||'暂无回答').slice(0,500))+'</p><span class="mc-muted">'+escape(r.tokens_used||0)+' Tokens</span>':'';
      if (s.kind!=='api_config') return item(s,r,index,check);
      return '<article class="mc-card '+(s.selected.has(r)?'is-selected':'')+'" data-row="'+index+'"><div class="mc-card-top"><span class="mc-icon"><i class="fas fa-'+s.cfg[1]+'"></i></span><span class="mc-tag">'+escape(label)+'</span>'+(check?'<input type="checkbox" data-select="'+index+'" aria-label="选择 '+escape(title)+'" '+(s.selected.has(r)?'checked':'')+'>':'')+'</div><h3 title="'+escape(title)+'">'+escape(title)+'</h3><p class="mc-owner">'+escape(r[s.cfg[3]]||'未分配')+'</p>'+detail+'<footer><time>'+escape(r.create_at||'')+'</time><div>'+template('#barDemo',r)+'</div></footer></article>';
    }).join(''):'<div class="mc-empty"><i class="fas fa-'+s.cfg[1]+'"></i><h3>'+(s.rows.length?'没有匹配的内容':'这里还没有记录')+'</h3><p>'+(s.rows.length?'调整搜索词或分类后再试试。':'新增内容后，将在这里以卡片展示。')+'</p></div>';
    if(s.kind!=='api_config') inspect(s,list);
    grid.querySelectorAll('a[lay-event]').forEach(a=>{a.tabIndex=0;a.setAttribute('role','button');a.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();a.click();}};});
    const selected=list.filter(r=>s.selected.has(r)).length, all=s.host.querySelector('.mc-all');
    all.checked=!!list.length&&selected===list.length;all.indeterminate=selected>0&&selected<list.length;
    s.host.querySelector('.mc-selected').textContent='已选 '+s.selected.size+' 项';
  }

  function upgrade(s) {
    if(s.kind==='api_config')return;
    s.host.classList.add('studio', 'studio-'+s.kind);
    const overview=s.host.querySelector('.mc-overview');
    overview.innerHTML='<span class="mc-kicker">'+({user_file:'文件与知识资产',user_query:'对话档案',user:'团队与协作',role:'角色与职责',permission:'权限与边界'}[s.kind])+'</span><div class="mc-total"><strong>—</strong><span>条记录</span></div>';
    const shell=document.createElement('div');shell.className='mc-shell';
    const rail=document.createElement('aside');rail.className='mc-rail';rail.setAttribute('aria-label','本页分类');
    const main=document.createElement('div');main.className='mc-main';
    const detail=document.createElement('aside');detail.className='mc-inspector';detail.setAttribute('aria-label','内容详情');
    [...s.host.children].filter(el=>el!==overview).forEach(el=>main.append(el));
    shell.append(rail,main,detail);s.host.append(shell);detail.addEventListener('click',e=>{const b=e.target.closest('[lay-event]');if(b&&s.active)emit('tool('+s.id+')',{event:b.getAttribute('lay-event'),data:s.active,del:()=>load(s)});});
    rail.innerHTML='<div class="mc-rail-title">'+escape(s.cfg[0])+'</div><div class="mc-categories"></div><p>分类数量为当前页记录<br>可使用下方分页浏览更多</p>';
    s.host.querySelector('.mc-grid').addEventListener('click',e=>{const b=e.target.closest('[data-open]');if(b){s.active=s.rows[Number(b.dataset.open)];if(s.kind==='user'||s.kind==='role'||s.kind==='permission'){const event=s.kind==='permission'?'assign':s.kind==='role'?'assign':'edit';emit('tool('+s.id+')',{event,data:s.active,del:()=>load(s)});}else draw(s);}});
    s.host.querySelector('select').addEventListener('change',()=>categoriesNav(s));
    rail.addEventListener('click',e=>{const b=e.target.closest('[data-category]');if(!b)return;s.type=b.dataset.category;s.host.querySelector('select').value=s.type;categoriesNav(s);draw(s);});
  }
  function categoriesNav(s) {
    if(s.kind==='api_config')return;
    const cats=[...new Set(s.rows.map(r=>category(s,r)))];
    s.host.querySelector('.mc-categories').innerHTML=['',...cats].map(c=>'<button type="button" data-category="'+escape(c)+'" aria-pressed="'+(s.type===c)+'"><i class="fas fa-'+(c?s.cfg[1]:'th-large')+'"></i><span>'+escape(c||'全部内容')+'</span><small>'+s.rows.filter(r=>!c||category(s,r)===c).length+'</small></button>').join('');
  }
  function item(s,r,index,check) {
    const title=escape(r[s.cfg[2]]||'未命名'), active=s.active===r;
    const select=check?'<input type="checkbox" data-select="'+index+'" aria-label="选择 '+title+'" '+(s.selected.has(r)?'checked':'')+'>':'';
    const open='<button type="button" class="mc-open" data-open="'+index+'">'+title+'</button>';
    const actions='<div class="mc-item-actions">'+template('#barDemo',r)+'</div>';
    const type=String(r.file_type||r.file_name?.split('.').pop()||'FILE').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,6)||'FILE';
    let body='';
    if(s.kind==='user_file')body='<div class="mc-file-top">'+select+'<span>'+escape(r.create_at||'').slice(0,10)+'</span></div><div class="mc-document type-'+(/PDF/.test(type)?'pdf':/XLS|CSV/.test(type)?'sheet':'doc')+'"><i class="fas fa-file-alt"></i><b>'+type+'</b></div>'+open+'<p class="mc-owner">'+escape(r.username||'未知用户')+' · '+fileSize(r.file_size)+'</p><footer><button class="mc-text" data-open="'+index+'">文件信息 ↗</button>'+actions+'</footer>';
    if(s.kind==='user_query')body='<div class="mc-message-icon"><i class="far fa-comment-alt"></i></div><div class="mc-record-body">'+open+'<p>'+escape(NewsQa.plainText(r.response_text||'暂无回答').slice(0,500))+'</p><span>'+escape(r.username)+' · '+escape(r.create_at)+'</span></div>'+select;
    if(s.kind==='user')body='<div class="mc-person-top">'+select+'<span class="mc-tag">'+escape(category(s,r))+'</span></div><div class="mc-avatar">'+escape(String(r.username||'?').slice(0,2).toUpperCase())+'</div>'+open+'<p class="mc-owner">'+escape(r.username==='admin'?'系统管理员':'团队成员')+'</p><footer><span class="mc-muted">加入于 '+escape(r.create_at||'').slice(0,10)+'</span>'+actions+'</footer>';
    if(s.kind==='role')body='<div class="mc-role-mark"><i class="fas fa-'+(r.is_system==1?'shield-alt':'user-tag')+'"></i><span>'+escape(category(s,r))+'</span></div>'+open+'<code>'+escape(r.code)+'</code><p class="mc-owner">'+(r.is_system==1?'系统预置的基础职责':'为团队定义独立的访问范围')+'</p><footer>'+actions+'</footer>';
    if(s.kind==='permission'){const names=String(r.menu_names||'').split(/[,，、]/).filter(Boolean);body='<div class="mc-permission-head"><span class="mc-icon"><i class="fas fa-fingerprint"></i></span><div>'+open+'<code>'+escape(r.role_code)+'</code></div>'+actions+'</div><div class="mc-permission-tags">'+(names.length?names.map(n=>'<span><i class="fas fa-check"></i> '+escape(n.trim())+'</span>').join(''):'<em>尚未分配访问权限</em>')+'</div>';}
    return '<article class="mc-item '+(active?'is-active ':'')+(s.selected.has(r)?'is-selected':'')+'" data-row="'+index+'">'+body+'</article>';
  }
  function inspect(s,list) {
    if(s.kind!=='user_file'&&s.kind!=='user_query'){s.host.querySelector('.mc-inspector').hidden=true;return;}
    if(!list.includes(s.active))s.active=list[0]||null;
    const r=s.active, box=s.host.querySelector('.mc-inspector');
    if(!r){box.innerHTML='<div class="mc-detail-empty"><i class="far fa-'+(s.kind==='user_file'?'file':'comment')+'"></i><p>选择一项，查看详细内容</p></div>';return;}
    s.host.querySelectorAll('.mc-item').forEach(el=>el.classList.toggle('is-active',s.rows[Number(el.dataset.row)]===r));
    const index=s.rows.indexOf(r);
    if(s.kind==='user_file')box.innerHTML='<div class="mc-detail-heading">文件详情</div><div class="mc-detail-file"><i class="far fa-file-alt"></i></div><h3>'+escape(r.file_name)+'</h3><span class="mc-detail-label">基本信息</span><dl><dt>上传者</dt><dd>'+escape(r.username)+'</dd><dt>文件类型</dt><dd>'+escape(r.file_type)+'</dd><dt>文件大小</dt><dd>'+fileSize(r.file_size)+'</dd><dt>上传时间</dt><dd>'+escape(r.create_at)+'</dd><dt>存储路径</dt><dd>'+escape(r.file_path)+'</dd></dl>';
    else box.innerHTML='<header class="mc-detail-heading"><span>对话详情</span><small>'+escape(r.tokens_used||0)+' Tokens</small></header><div class="mc-chat-meta">'+escape(r.username)+' · '+escape(r.create_at)+'</div><div class="mc-chat-label">用户提问</div><div class="mc-question">'+escape(r.query_text)+'</div><div class="mc-chat-label"><span class="mc-ai-dot">✦</span> AI 回答</div><div class="mc-answer">'+escape(r.response_text||'暂无回答')+'</div><div class="mc-item-actions mc-detail-actions">'+template('#barDemo',r)+'</div>';
    if(s.kind==='user_query') NewsQa.renderMarkdown(box.querySelector('.mc-answer'),r.response_text||'暂无回答');
  }
  async function load(s) {
    s.host.setAttribute('aria-busy','true');s.host.querySelector('.mc-grid').innerHTML='<p class="mc-empty">正在加载…</p>';
    s.host.querySelector('.mc-prev').disabled=true;s.host.querySelector('.mc-next').disabled=true;
    try {
      const url=new URL(s.options.url,location.origin);url.searchParams.set('page',s.page);url.searchParams.set('limit',20);
      const response=await fetch(url,{headers:{Accept:'application/json'}});if(!response.ok)throw Error('加载失败');const res=await response.json();if(res.code!==0)throw Error(res.msg||'加载失败');
      s.rows=res.data||[];s.selected.clear();const total=res.count==null?s.rows.length:res.count;
      if(s.page>1&&!s.rows.length){s.page--;return load(s);}
      s.host.querySelector('.mc-total strong').textContent=total;
      const select=s.host.querySelector('select'), categories=[...new Set(s.rows.map(r=>category(s,r)))];
      select.innerHTML='<option value="">全部分类</option>'+categories.map(c=>'<option value="'+escape(c)+'">'+escape(c)+'</option>').join('');if(!categories.includes(s.type))s.type='';select.value=s.type;
      s.host.querySelector('.mc-pager > span').textContent='第 '+s.page+' 页 · 共 '+total+' 条';s.host.querySelector('.mc-prev').disabled=s.page<=1;s.host.querySelector('.mc-next').disabled=!s.options.page||s.page*20>=total;
      categoriesNav(s);draw(s);
    } catch(error) { s.host.querySelector('.mc-grid').innerHTML='<div class="mc-empty"><h3>暂时无法加载</h3><p>'+escape(error.message)+'，请点击刷新重试。</p></div>'; }
    finally{s.host.removeAttribute('aria-busy');}
  }
  window.ManagementCards={render,escape,on:(name,fn)=>{handlers[name]=fn;},reload:id=>load(states[id]),checkStatus:id=>({data:[...states[id].selected]})};
})();
