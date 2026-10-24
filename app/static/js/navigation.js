/* Navigation structure, visual vocabulary and personal ordering. */
(function(){
'use strict';
const shell=document.getElementById('appShell'), frame=document.getElementById('content_iframe'), nav=document.querySelector('.layui-nav-tree');
const storageKey='insight.navigation.v3', collapseKey='insight.navigation.collapsed.v3';
const definitions=[
 {id:'data',label:'采集与资料',icon:'fa-database',routes:['/spy','/data_warehouse/list','/spy_source/list','/deep_collect/list','/user_file/list'],open:true},
 {id:'insights',label:'分析与看板',icon:'fa-chart-line',routes:['/sentiment','/data_screen','/data_analysis'],open:false},
 {id:'team',label:'团队与智能体',icon:'fa-users',routes:['/collaboration/list','/digital_employee/list','/skill/list'],open:true},
 {id:'history',label:'历史记录',icon:'fa-history',routes:['/chat_session/list','/user_query/list'],open:false},
 {id:'platform',label:'平台配置',icon:'fa-sliders-h',routes:['/model_engine/list','/api_config/list','/system_config/list'],open:false},
 {id:'access',label:'组织与权限',icon:'fa-shield-alt',routes:['/user/list','/role/list','/permission/list','/menu/list'],open:false},
 {id:'other',label:'其他功能',icon:'fa-th-large',routes:[],open:false}
];
const metadata={
 '/spy':['瞭望采集','fa-satellite-dish'], '/data_warehouse/list':['资料库','fa-book-open'], '/spy_source/list':['数据源','fa-rss'], '/deep_collect/list':['深度采集','fa-layer-group'], '/user_file/list':['文件空间','fa-folder-open'],
 '/sentiment':['舆情洞察','fa-chart-line'], '/data_screen':['数智大屏','fa-chart-pie'], '/data_analysis':['数据分析','fa-chart-bar'],
 '/collaboration/list':['协作消息','fa-comments'], '/digital_employee/list':['数字员工','fa-robot'], '/skill/list':['技能库','fa-puzzle-piece'], '/chat_session/list':['会话记录','fa-history'], '/user_query/list':['问答记录','fa-comment-dots'],
 '/model_engine/list':['模型引擎','fa-microchip'], '/api_config/list':['接口连接','fa-plug'], '/system_config/list':['系统设置','fa-cog'], '/user/list':['成员管理','fa-user-friends'], '/role/list':['角色管理','fa-user-tag'], '/permission/list':['访问权限','fa-shield-alt'], '/menu/list':['功能菜单','fa-sitemap'], '/user_dashboard':['AI 问数','fa-magic']
};
function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;}
function icon(name){const i=el('i','fas '+name);i.setAttribute('aria-hidden','true');return i;}
function readStorage(key,fallback){try{return JSON.parse(localStorage.getItem(key))||fallback;}catch(e){return fallback;}}
let saved=readStorage(storageKey,{}),collapsed=readStorage(collapseKey,{}),items=[],activePath='/dashboard',draft=[];
if(!saved||typeof saved!=='object')saved={};if(!collapsed||typeof collapsed!=='object')collapsed={};
const links=Array.from(nav.querySelectorAll('a[target="content_iframe"]')), seen=new Set();
links.forEach(a=>{const route=a.getAttribute('href');if(!route||seen.has(route))return;seen.add(route);const meta=metadata[route]||[a.textContent.trim(),'fa-th-large'];
 if(route==='/user_dashboard'){document.getElementById('sidebarAsk').hidden=false;document.getElementById('mobileAsk').hidden=false;return;}
 const group=definitions.find(d=>d.routes.includes(route));items.push({route,label:meta[0],icon:meta[1],group:group?group.id:'other'});
});
function defaultItems(){const order=definitions.flatMap(d=>d.routes);return items.map(i=>({...i})).sort((a,b)=>{const ai=order.indexOf(a.route),bi=order.indexOf(b.route);return (ai<0?1000:ai)-(bi<0?1000:bi);});}
function currentItems(){let result=defaultItems();const positions=Array.isArray(saved.order)?saved.order:[];const groups=saved.groups&&typeof saved.groups==='object'?saved.groups:{};result.forEach(i=>{if(definitions.some(d=>d.id===groups[i.route]))i.group=groups[i.route];});if(positions.length)result.sort((a,b)=>{const ai=positions.indexOf(a.route),bi=positions.indexOf(b.route);return (ai<0?1000:ai)-(bi<0?1000:bi);});return result;}
function render(){
 nav.replaceChildren();const current=currentItems();
 definitions.forEach(d=>{const children=current.filter(i=>i.group===d.id);if(!children.length)return;const section=el('li','navigation-section');section.dataset.group=d.id;const heading=el('button','navigation-section-toggle');heading.type='button';const open=Object.hasOwn(collapsed,d.id)?!collapsed[d.id]:d.open;const selected=children.some(i=>i.route===activePath);const expanded=open||selected;heading.setAttribute('aria-expanded',String(expanded));const id='navigation-group-'+d.id;heading.setAttribute('aria-controls',id);heading.append(icon(d.icon),el('span','',d.label),icon('fa-chevron-down'));const list=el('ul','navigation-section-items');list.id=id;list.hidden=!expanded;
 heading.onclick=()=>{const state=heading.getAttribute('aria-expanded')!=='true';heading.setAttribute('aria-expanded',String(state));list.hidden=!state;collapsed[d.id]=!state;try{localStorage.setItem(collapseKey,JSON.stringify(collapsed));}catch(e){}};
 children.forEach(item=>{const li=el('li','layui-nav-item'),a=el('a','navigation-link');a.href=item.route;a.target='content_iframe';a.append(icon(item.icon),el('span','',item.label));a.onclick=()=>{if(innerWidth<=768)setCollapsed(true);};li.append(a);list.append(li);});section.append(heading,list);nav.append(section);
 });syncLinks();
}
function setCollapsed(value){shell.classList.toggle('nav-collapsed',value);const button=document.getElementById('sidebarToggle');button.setAttribute('aria-expanded',String(!value));button.setAttribute('aria-label',value?'展开导航':'收起导航');}
function syncLinks(){document.querySelectorAll('a[target="content_iframe"]').forEach(a=>{const match=a.getAttribute('href')===activePath;a.classList.toggle('is-current',match);if(match)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});}
function syncNavigation(){try{const path=frame.contentWindow.location.pathname;if(path==='about:blank')return;activePath=path;const meta=metadata[path];document.getElementById('currentPageName').textContent=path==='/dashboard'?'工作台':meta?meta[0]:(frame.contentDocument.title||'工作空间');syncLinks();const active=nav.querySelector('a[aria-current="page"]');if(active){const list=active.closest('.navigation-section-items');list.hidden=false;list.previousElementSibling.setAttribute('aria-expanded','true');}}catch(e){}}
window.navTo=url=>{frame.src=url;};frame.addEventListener('load',syncNavigation);document.getElementById('sidebarToggle').onclick=()=>setCollapsed(!shell.classList.contains('nav-collapsed'));if(innerWidth<=768)setCollapsed(true);
document.querySelectorAll('.workspace-home,.sidebar-ask,.mobile-ask-link').forEach(a=>a.onclick=()=>{if(innerWidth<=768)setCollapsed(true);});
render();if(frame.contentDocument&&frame.contentDocument.readyState==='complete')syncNavigation();
const dialog=document.getElementById('navigationDialog');
function renderEditor(){const editor=document.getElementById('navigationEditor');editor.replaceChildren();definitions.forEach(d=>{const children=draft.filter(i=>i.group===d.id);if(!children.length)return;editor.append(el('h3','navigation-editor-heading',d.label));children.forEach(item=>{const row=el('div','navigation-editor-row');row.append(icon(item.icon),el('strong','',item.label));const select=el('select','form-select');select.setAttribute('aria-label',item.label+'的分组');definitions.forEach(g=>{const option=el('option','',g.label);option.value=g.id;option.selected=g.id===item.group;select.append(option);});select.onchange=()=>{item.group=select.value;renderEditor();};row.append(select);['up','down'].forEach((direction,index)=>{const button=el('button','sidebar-order-button',index?'↓':'↑');button.type='button';button.setAttribute('aria-label',(index?'下移':'上移')+item.label);const peer=children[children.indexOf(item)+(index?1:-1)];button.disabled=!peer;button.onclick=()=>{const a=draft.indexOf(item),b=draft.indexOf(peer);[draft[a],draft[b]]=[draft[b],draft[a]];renderEditor();};row.append(button);});editor.append(row);});});}
document.getElementById('customizeNavigation').onclick=()=>{draft=currentItems().map(i=>({...i}));document.getElementById('navigationSaveError').textContent='';renderEditor();dialog.showModal();};
document.getElementById('closeNavigationDialog').onclick=()=>dialog.close();document.getElementById('resetNavigation').onclick=()=>{draft=defaultItems();renderEditor();};
if(window.layui)layui.use(['element'],function(){layui.element.render('nav');});
document.getElementById('saveNavigation').onclick=()=>{const next={order:draft.map(i=>i.route),groups:Object.fromEntries(draft.map(i=>[i.route,i.group]))};try{localStorage.setItem(storageKey,JSON.stringify(next));saved=next;render();dialog.close();}catch(e){document.getElementById('navigationSaveError').textContent='浏览器无法保存设置，请允许本地存储后重试。';}};
})();
