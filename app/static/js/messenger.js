(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const root = $('messenger');
  const xsrf = root.dataset.xsrf;
  let groups = [], active = null, page = 1, total = 0, people = [], chosen = new Map(), mode = 'create', kind = 'user', createdId = null, pickerRequest = 0, peopleLoading = false;
  function element(tag, cls, value) { const e = document.createElement(tag); if (cls) e.className = cls; if (value !== undefined) e.textContent = value; return e; }
  async function api(query, body) {
    const response = await fetch('/api/collaboration' + (query ? '?' + query : ''), body ? {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:new URLSearchParams({...body, _xsrf:xsrf})} : {});
    if (!response.ok) throw new Error('请求失败，请稍后重试');
    const result = await response.json(); if (result.code !== 0) throw new Error(result.msg || '操作未完成'); return result;
  }
  function avatar(name, type) { return element('span', 'person-avatar ' + (type || ''), type === 'employee' ? 'AI' : (name || '群').slice(0,1)); }
  function renderGroups() {
    const list = $('conversationList'); list.replaceChildren(); const q = $('groupSearch').value.trim().toLowerCase();
    const visible = groups.filter(g => (g.name+' '+(g.description||'')).toLowerCase().includes(q));
    visible.forEach(g => {
      const button = element('button','conversation-item' + (active && g.id === active.id ? ' is-active' : ''));
      button.type = 'button'; button.setAttribute('aria-pressed', String(!!active && g.id === active.id)); button.append(avatar(g.name, 'group'));
      const info = element('span','conversation-item-info'); info.append(element('strong','',g.name),element('span','',g.description || '打开群聊，开始讨论'));
      button.append(info,element('small','',g.member_count+' 人')); button.onclick=()=>selectGroup(g); list.append(button);
    });
    if (!visible.length) list.append(element('p','messenger-status',q ? '没有找到匹配的群聊' : '还没有群聊，点击右上角 ＋ 创建一个'));
    $('groupCount').textContent = total; $('loadMoreGroups').hidden = groups.length >= total;
  }
  async function loadGroups(reset, selectedId) {
    const r = await api('page='+(reset ? 1 : page+1)+'&limit=40'); page=reset ? 1 : page+1; total=r.count; groups=reset ? r.data : groups.concat(r.data);
    if (selectedId) { const match=groups.find(g=>g.id===selectedId); if(match) selectGroup(match); }
    else if(active) { const fresh=groups.find(g=>g.id===active.id); if(fresh) { active=fresh; updateHeader(); } }
    renderGroups();
  }
  function updateHeader() { $('activeGroupName').textContent=active.name; $('activeGroupDesc').textContent=active.description || '在聊天中 @ 数字员工，让 AI 加入协作'; }
  function selectGroup(group) {
    const changed=!active || active.id!==group.id; active=group; updateHeader();
    $('conversationActions').hidden=false; $('conversationEmpty').hidden=true; $('groupChatFrame').hidden=false;
    if(changed) $('groupChatFrame').src='/collaboration/chat?group_id='+group.id+'&embedded=1';
    root.classList.add('has-conversation'); renderGroups();
  }
  async function openPeople(nextMode) {
    mode=nextMode; peopleLoading=true; chosen.clear(); kind='user'; createdId=null; people=[]; const request=++pickerRequest;
    $('peopleError').textContent=''; $('peopleSearch').value=''; $('newGroupName').value=''; $('newGroupDesc').value='';
    $('newGroupFields').hidden=mode!=='create'; $('newGroupName').required=mode==='create';
    $('peopleDialogTitle').textContent=mode==='create'?'发起群聊':'邀请加入「'+active.name+'」'; $('savePeople').textContent=mode==='create'?'创建群聊':'发送邀请';
    $('savePeople').disabled=false; $('peopleDialog').showModal(); renderPeople();
    try {
      const suffix=mode==='invite'?'&group_id='+active.id:'';
      const results=await Promise.all([api('action=available_users'+suffix),api('action=available_employees'+suffix)]);
      if(request!==pickerRequest) return;
      people=results.flatMap((r,i)=>r.data.map(p=>({...p,kind:i?'employee':'user',label:i?p.name:p.username,key:(i?'employee':'user')+':'+p.id})));
      peopleLoading=false;renderPeople();
    } catch(e) { peopleLoading=false;renderPeople();$('peopleError').textContent=e.message; }
  }
  function renderPeople() {
    document.querySelectorAll('[data-kind]').forEach(b=>b.classList.toggle('is-active',b.dataset.kind===kind));
    const list=$('peopleList'); list.replaceChildren(); const q=$('peopleSearch').value.trim().toLowerCase();
    people.filter(p=>p.kind===kind && (p.label+' '+(p.role_desc||'')).toLowerCase().includes(q)).forEach(p=>{
      const row=element('label','people-row'); const check=document.createElement('input');check.type='checkbox';check.checked=chosen.has(p.key);check.setAttribute('aria-label',p.label);
      check.onchange=()=>{if(check.checked)chosen.set(p.key,p);else chosen.delete(p.key);renderPeople();};
      const info=element('span','person-info');info.append(element('strong','',p.label),element('small','',p.role_desc || (p.kind==='employee'?'AI 伙伴':'团队联系人')));
      row.append(check,avatar(p.label,p.kind),info);list.append(row);
    });
    if(!list.childElementCount)list.append(element('p','messenger-status',peopleLoading?'正在加载联系人…':'暂无可选择的成员'));
    $('selectedPeopleCount').textContent=chosen.size; const selection=$('selectedPeople');selection.replaceChildren();
    chosen.forEach(p=>{const b=element('button','selected-person',p.label+' ×');b.type='button';b.setAttribute('aria-label','移除 '+p.label);b.onclick=()=>{chosen.delete(p.key);renderPeople();};selection.append(b);});
    if(!chosen.size)selection.append(element('p','messenger-status','从左侧选择要一起讨论的成员'));
  }
  $('peopleForm').onsubmit=async event=>{
    event.preventDefault(); const button=$('savePeople'); button.disabled=true; $('peopleError').textContent='';
    try {
      if(mode==='invite' && !chosen.size) throw new Error('请先选择要邀请的成员');
      if(mode==='create' && !createdId) { const r=await api('',{action:'add',name:$('newGroupName').value.trim(),description:$('newGroupDesc').value.trim()}); createdId=r.data.id; }
      const id=mode==='create'?createdId:active.id;
      if(chosen.size)await api('',{action:'invite_batch',group_id:id,user_ids:Array.from(chosen.values()).filter(p=>p.kind==='user').map(p=>p.id).join(','),employee_ids:Array.from(chosen.values()).filter(p=>p.kind==='employee').map(p=>p.id).join(',')});
      $('peopleDialog').close(); await loadGroups(true,id);
      if(mode==='invite') $('groupChatFrame').src='/collaboration/chat?group_id='+id+'&embedded=1';
    } catch(e){$('peopleError').textContent=(createdId?'群聊已创建，邀请尚未完成，可重试。':'')+e.message;} finally{button.disabled=false;}
  };
  $('groupSettings').onclick=()=>{ $('editGroupName').value=active.name;$('editGroupDesc').value=active.description||'';$('settingsError').textContent='';$('settingsDialog').showModal();};
  $('settingsForm').onsubmit=async e=>{e.preventDefault();$('saveSettings').disabled=true;try{await api('',{action:'edit',id:active.id,name:$('editGroupName').value.trim(),description:$('editGroupDesc').value.trim()});$('settingsDialog').close();await loadGroups(true);}catch(err){$('settingsError').textContent=err.message;}finally{$('saveSettings').disabled=false;}};
  $('deleteGroup').onclick=async()=>{
    if(!window.confirm('解散「'+active.name+'」？群聊和所有消息会被删除。'))return;
    $('deleteGroup').disabled=true;
    try{await api('',{action:'delete',id:active.id});active=null;$('groupChatFrame').removeAttribute('src');$('groupChatFrame').hidden=true;$('conversationActions').hidden=true;$('conversationEmpty').hidden=false;root.classList.remove('has-conversation');$('settingsDialog').close();await loadGroups(true);}catch(e){$('settingsError').textContent=e.message;}finally{$('deleteGroup').disabled=false;}
  };
  $('groupMembers').onclick=async()=>{
    $('groupMemberList').replaceChildren(element('p','messenger-status','正在加载…'));$('membersDialog').showModal();
    try { const r=await api('action=members&group_id='+active.id);$('groupMemberList').replaceChildren();r.data.forEach(p=>{const row=element('div','people-row');const name=p.display_name||p.member_name||'成员';const info=element('span','person-info');info.append(element('strong','',name),element('small','',p.role==='owner'?'群主':p.member_type==='employee'?'数字员工':'群成员'));row.append(avatar(name,p.member_type),info);$('groupMemberList').append(row);}); }catch(e){$('groupMemberList').textContent=e.message;}
  };
  document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
  document.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>{kind=b.dataset.kind;renderPeople();});
  $('peopleSearch').oninput=renderPeople; $('groupSearch').oninput=renderGroups;
  $('createGroup').onclick=$('emptyCreateGroup').onclick=()=>openPeople('create');
  $('inviteMembers').onclick=()=>openPeople('invite');
  $('backToConversations').onclick=()=>root.classList.remove('has-conversation');
  $('loadMoreGroups').onclick=async()=>{try{await loadGroups(false);}catch(e){$('conversationList').append(element('p','interaction-error',e.message));}};
  loadGroups(true).catch(e=>{$('conversationList').replaceChildren(element('p','interaction-error',e.message));const retry=element('button','btn btn-secondary','重新加载');retry.onclick=()=>location.reload();$('conversationList').append(retry);});
})();
