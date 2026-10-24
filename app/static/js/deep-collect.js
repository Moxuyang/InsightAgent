(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const root = $('deepCollection');
  const endpoints = { warehouse: '/api/deep_collect/data', results: '/api/deep_collect/results', tasks: '/api/deep_collect' };
  const tabs = Array.from(root.querySelectorAll('[data-view]'));
  const states = Object.fromEntries(Object.keys(endpoints).map(key => [key, { page: 1, keyword: '', source: '' }]));
  const limit = 10;
  let view = 'warehouse', rows = [], total = 0, loading = false, listRequest = null;
  let selected = new Set(), current = null, detailVersion = 0, busy = false, stopQueue = false, taskId = null, toastTimer;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function button(text, className, action) {
    const node = el('button', className, text); node.type = 'button'; node.addEventListener('click', action); return node;
  }
  function url(value, depth = 0) {
    if (!value || depth > 4) return null;
    try {
      if (value.startsWith('/link?') || value.startsWith('/sf?')) value = 'https://www.baidu.com' + value;
      const parsed = new URL(value, location.origin);
      if (!/^https?:$/.test(parsed.protocol)) return null;
      if (/(^|\.)toutiao\.com$/.test(parsed.hostname) && parsed.pathname.includes('/search/jump') && parsed.searchParams.get('url')) {
        return url(parsed.searchParams.get('url'), depth + 1);
      }
      return parsed.href;
    } catch (_) { return null; }
  }
  async function get(endpoint, params = {}, signal) {
    const response = await fetch(endpoint + '?' + new URLSearchParams(params), { signal });
    if (!response.ok) throw Error('请求未完成，请稍后重试');
    return response.json();
  }
  async function post(endpoint, data) {
    const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ ...data, _xsrf: root.dataset.xsrf }) });
    if (!response.ok) throw Error('操作未完成，请稍后重试');
    const result = await response.json();
    if (result.code !== 0) throw Error(result.msg || '操作失败');
    return result;
  }
  function toast(message) {
    clearTimeout(toastTimer); $('dcToast').textContent = message; $('dcToast').hidden = false;
    toastTimer = setTimeout(() => { $('dcToast').hidden = true; }, 5000);
  }
  function empty(title, description, retry) {
    const node = el('div', 'dc-empty-list');
    node.append(el('div', 'dc-empty-symbol', retry ? '↻' : '≡'), el('h2', '', title), el('p', '', description));
    if (retry) node.append(button('重新加载', 'dc-button dc-button-secondary', load));
    $('dcList').replaceChildren(node);
  }
  function selection() {
    $('dcSelectPage').checked = rows.length > 0 && rows.every(item => selected.has(item.id));
    $('dcSelectPage').indeterminate = selected.size > 0 && !$('dcSelectPage').checked;
    $('dcSelectPage').disabled = loading || !rows.length;
    $('dcSelection').hidden = !selected.size;
    $('dcSelectedCount').textContent = '已选择 ' + selected.size + ' 条' + (view === 'tasks' ? '任务' : '资料');
    $('dcBatchAction').textContent = view === 'warehouse' ? '采集所选' : '删除所选';
    $('dcBatchAction').disabled = busy || loading;
    root.querySelectorAll('[data-select]').forEach(input => { input.checked = selected.has(Number(input.dataset.select)); });
    requestAnimationFrame(sizeReader);
  }
  function markActive() {
    root.querySelectorAll('.dc-story').forEach(card => {
      card.classList.toggle('is-active', Boolean(current && current.view === view && String(current.item.id) === card.dataset.id));
    });
  }
  function render() {
    const list = $('dcList'); list.replaceChildren();
    rows.forEach(item => {
      const card = el('article', 'dc-story'); card.dataset.id = item.id;
      const check = el('input'); check.type = 'checkbox'; check.dataset.select = item.id;
      check.setAttribute('aria-label', '选择 ' + (item.title || item.name || '未命名内容'));
      check.addEventListener('change', () => { if (check.checked) selected.add(item.id); else selected.delete(item.id); selection(); });
      const main = el('div', 'dc-story-main'), meta = el('div', 'dc-story-meta');
      meta.append(el('span', 'dc-source-dot'), el('span', 'dc-story-source', view === 'tasks' ? ({ webpage: '网页正文', api: 'API 数据', rss: 'RSS 订阅' }[item.collect_type] || item.collect_type) : item.source_name || '未知来源'));
      const keyword = item.keyword || item.spy_keyword;
      if (keyword) meta.append(el('span', 'dc-story-topic', ' / ' + keyword));
      if (view === 'results') meta.append(el('span', 'dc-result-state ' + (['success', 'failed'].includes(item.crawl_status) ? item.crawl_status : ''), { success: '已采集', failed: '采集失败', pending: '待完成' }[item.crawl_status] || '待完成'));
      if (view === 'tasks') meta.append(el('span', 'dc-task-state ' + (Number(item.is_active) ? 'enabled' : ''), Number(item.is_active) ? '已启用' : '已停用'));
      const title = button(item.title || item.name || '未命名内容', 'dc-story-title', () => view === 'tasks' ? editTask(item) : preview(item));
      const summary = String(view === 'tasks' ? item.target_url || '' : item.summary || item.full_content || item.error_msg || (view === 'results' ? '打开查看采集正文与图片。' : '暂未保存摘要，打开预览或提取原文继续阅读。')).replace(/\s+/g, ' ').slice(0, 240);
      const footer = el('div', 'dc-story-footer');
      footer.append(el('time', 'dc-story-time', (view === 'results' ? item.crawl_at : item.create_at) || ''));
      const actions = el('div', 'dc-story-actions');
      if (view === 'tasks') {
        actions.append(button('编辑任务', 'dc-preview-button', () => editTask(item)), button('删除', 'dc-text-button', () => remove([item.id])));
      } else {
        actions.append(button(view === 'results' ? '阅读全文 →' : '预览内容 →', 'dc-preview-button', () => preview(item)));
      }
      footer.append(actions); main.append(meta, title, el('p', 'dc-story-summary', summary), footer); card.append(check, main); list.append(card);
    });
    if (!rows.length) {
      const filtered = states[view].keyword || states[view].source;
      empty(filtered ? '没有找到匹配内容' : { warehouse: '从第一条资料开始', results: '正文将在这里沉淀', tasks: '让采集任务井井有条' }[view], filtered ? '试试更短的关键词，或切换其他来源。' : { warehouse: '先去发现新内容，再回来预览和提取正文。', results: '在待采集资料中选择文章，提取后即可在这里阅读。', tasks: '新建任务，保存你的采集来源与执行配置。' }[view]);
    }
    const page = states[view].page;
    $('dcListCount').textContent = '共 ' + total + ' 条' + (view === 'tasks' ? '任务' : '资料');
    $('dcRange').textContent = total ? '显示 ' + ((page - 1) * limit + 1) + '–' + Math.min(page * limit, total) + ' 条' : '暂无内容';
    $('dcPage').textContent = page + ' / ' + Math.max(1, Math.ceil(total / limit));
    $('dcPrev').disabled = page <= 1; $('dcNext').disabled = page * limit >= total;
    selection(); markActive();
  }
  async function load() {
    if (listRequest) listRequest.abort();
    const controller = new AbortController(); listRequest = controller;
    const activeView = view, state = { ...states[view] };
    loading = true; selected.clear(); selection();
    $('dcList').setAttribute('aria-busy', 'true'); $('dcListCount').textContent = '正在加载…';
    $('dcPrev').disabled = true; $('dcNext').disabled = true;
    $('dcList').replaceChildren(el('div', 'dc-skeleton'), el('div', 'dc-skeleton'), el('div', 'dc-skeleton'));
    try {
      const result = await get(endpoints[activeView], { page: state.page, limit, keyword: state.keyword, source_id: state.source }, controller.signal);
      if (controller.signal.aborted) return;
      if (result.code !== 0) throw Error(result.msg || '内容加载失败');
      rows = result.data || []; total = Number(result.count) || 0;
      if (!rows.length && state.page > 1) { states[view].page--; return load(); }
      loading = false; render();
      if (!state.keyword && !state.source) updateCount(activeView, total);
    } catch (error) {
      if (controller.signal.aborted) return;
      rows = []; total = 0; loading = false; selection();
      $('dcRange').textContent = ''; $('dcPage').textContent = '—'; $('dcListCount').textContent = '加载失败';
      empty('内容暂时未能加载', error.message, true);
    } finally {
      if (listRequest === controller) $('dcList').setAttribute('aria-busy', 'false');
    }
  }
  function updateCount(key, count) { $('dcCount' + key.charAt(0).toUpperCase() + key.slice(1)).textContent = count; }
  async function counts() {
    await Promise.all(Object.entries(endpoints).map(async ([key, endpoint]) => {
      try { const result = await get(endpoint, { limit: 1 }); if (result.code === 0) updateCount(key, result.count); } catch (_) { /* The list provides a retry if the service is unavailable. */ }
    }));
  }
  function closeReader(restoreFocus = true) {
    const previous = current; current = null; ++detailVersion;
    $('dcReader').hidden = true; $('dcContent').classList.remove('has-reader'); markActive();
    if (restoreFocus && previous && previous.view === view) {
      const card = Array.from(root.querySelectorAll('.dc-story')).find(node => node.dataset.id === String(previous.item.id));
      if (card) card.querySelector('.dc-story-title').focus({ preventScroll: true });
    }
  }
  function openReader(item, kind) {
    $('dcReader').hidden = false; $('dcContent').classList.add('has-reader');
    $('dcReaderKind').textContent = kind; $('dcReaderTitle').textContent = item.title || '未命名资料';
    $('dcReaderMeta').textContent = [item.source_name || '未知来源', item.keyword || item.spy_keyword, item.crawl_at || item.create_at].filter(Boolean).join(' · ');
    const original = url(item.spy_url || item.url);
    $('dcOriginal').hidden = !original;
    if (original) $('dcOriginal').href = original; else $('dcOriginal').removeAttribute('href');
    $('dcReaderCopy').replaceChildren(); $('dcReaderScroll').scrollTop = 0;
    $('dcReaderTitle').focus({ preventScroll: true }); markActive();
    requestAnimationFrame(sizeReader);
  }
  function sizeReader() {
    if ($('dcReader').hidden) return;
    const top = Math.max(16, $('dcReader').getBoundingClientRect().top);
    $('dcReader').style.setProperty('--dc-reader-top', top + 'px');
  }
  function preview(item) {
    current = { view, item }; ++detailVersion;
    openReader(item, view === 'warehouse' ? '资料预览' : '正文阅读');
    if (view === 'results') { detail(item.id); return; }
    $('dcReaderStatus').textContent = '当前展示采集时保存的摘要，提取后可阅读完整正文。';
    $('dcReaderCopy').append(el('h3', '', '内容摘要'), el('p', '', item.summary || '这条资料暂时没有摘要，你可以打开原文或提取完整正文。'));
    $('dcCrawlArticle').hidden = false; $('dcCrawlArticle').disabled = busy || !url(item.url);
    $('dcCrawlArticle').textContent = busy ? '正在采集中…' : '提取完整正文';
  }
  async function detail(id) {
    const version = ++detailVersion;
    $('dcReaderStatus').textContent = '正在载入正文…'; $('dcCrawlArticle').hidden = true;
    try {
      const result = await get('/api/deep_collect/result_detail', { id });
      if (version !== detailVersion || !current) return;
      if (result.code !== 0 || !result.data) throw Error(result.msg || '正文未找到');
      const item = result.data;
      openReader(item, '正文阅读');
      current.result = item;
      $('dcReaderStatus').textContent = item.crawl_status === 'failed' ? '采集未完成：' + (item.error_msg || '请稍后重试，或直接打开原文。') : item.crawl_status === 'success' ? '正文已保存，可随时阅读。' : '采集尚未完成，可稍后刷新查看。';
      let content = item.full_content || '';
      if (!content && item.content_html) {
        const doc = new DOMParser().parseFromString(item.content_html, 'text/html');
        doc.querySelectorAll('script,style,noscript').forEach(node => node.remove());
        content = doc.body.textContent || '';
      }
      content.split(/\n+/).filter(line => line.trim()).forEach(line => $('dcReaderCopy').append(el('p', '', line.trim())));
      if (!content.trim()) $('dcReaderCopy').append(el('p', '', '暂未提取到正文，可打开原文继续阅读。'));
      let images = []; try { images = JSON.parse(item.images_json || '[]'); } catch (_) { /* Text is still readable. */ }
      if (Array.isArray(images)) images.forEach(image => {
        if (!image || typeof image !== 'object') return;
        const src = url(image.local || image.original); if (!src) return;
        const img = el('img'); img.src = src; img.alt = image.alt || '文章配图'; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
        img.addEventListener('error', () => img.remove()); $('dcReaderCopy').append(img);
      });
      $('dcCrawlArticle').hidden = !item.spy_data_id;
      $('dcCrawlArticle').disabled = busy;
      $('dcCrawlArticle').textContent = item.crawl_status === 'success' ? '已提取正文' : '重新提取正文';
      if (item.crawl_status === 'success') $('dcCrawlArticle').disabled = true;
    } catch (error) {
      if (version !== detailVersion) return;
      $('dcReaderStatus').textContent = error.message;
      $('dcReaderCopy').append(button('重新加载正文', 'dc-button dc-button-secondary', () => detail(id)));
    }
  }
  function switchView(key) {
    if (key === view) return;
    closeReader(false); view = key;
    tabs.forEach(tab => { const active = tab.dataset.view === key; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; });
    $('dcContent').setAttribute('aria-labelledby', tabs.find(tab => tab.dataset.view === key).id);
    $('dcSource').hidden = key !== 'warehouse'; $('dcAddTask').hidden = key !== 'tasks'; $('dcTopNote').hidden = key === 'tasks';
    $('dcKeyword').value = states[key].keyword; $('dcSource').value = states[key].source;
    $('dcKeyword').placeholder = key === 'tasks' ? '搜索任务名称或目标地址' : key === 'results' ? '搜索采集结果标题或关键词' : '搜索标题、摘要或关键词';
    $('dcKeyword').setAttribute('aria-label', $('dcKeyword').placeholder); load();
  }
  async function crawl(ids) {
    if (busy || !ids.length) return;
    busy = true; stopQueue = false; selection();
    $('dcCrawlArticle').disabled = true; $('dcProgress').hidden = false; $('dcStop').disabled = false;
    $('dcStop').textContent = '停止后续采集';
    $('dcProgressBar').max = ids.length; $('dcProgressBar').value = 0;
    let success = 0, failed = 0, completed = 0;
    for (const id of ids) {
      if (stopQueue) break;
      $('dcProgressTitle').textContent = '正在提取 ' + (completed + 1) + ' / ' + ids.length;
      $('dcProgressText').textContent = '已完成 ' + completed + ' 条，请稍候。';
      try {
        const result = await get('/api/deep_collect/run', { spy_data_id: id, _xsrf: root.dataset.xsrf });
        if (result.code === 0) success++; else failed++;
        if (current && ((current.view === 'warehouse' && Number(current.item.id) === Number(id)) || (current.result && Number(current.result.spy_data_id) === Number(id)))) {
          if (result.data && result.data.id) await detail(result.data.id);
          else $('dcReaderStatus').textContent = result.msg || '采集失败，请稍后重试。';
        }
      } catch (error) { failed++; }
      completed++; $('dcProgressBar').value = completed;
    }
    busy = false; selected.clear(); selection();
    $('dcStop').disabled = false; $('dcStop').textContent = '收起进度';
    $('dcProgressTitle').textContent = stopQueue ? '已停止后续采集' : '本轮采集完成';
    $('dcProgressText').textContent = '成功 ' + success + ' 条 · 失败 ' + failed + ' 条' + (completed < ids.length ? ' · 未执行 ' + (ids.length - completed) + ' 条' : '');
    toast($('dcProgressText').textContent);
    if (current && current.result) {
      $('dcCrawlArticle').disabled = current.result.crawl_status === 'success';
    } else if (current && current.view === 'warehouse') $('dcCrawlArticle').disabled = !url(current.item.url);
    counts(); if (view === 'results') load();
  }
  async function remove(ids) {
    const targetView = view;
    if (!ids.length || targetView === 'warehouse' || busy) return;
    if (!confirm('确定删除这 ' + ids.length + ' 条' + (targetView === 'tasks' ? '任务配置' : '采集结果') + '？')) return;
    try {
      await post(endpoints[targetView], { action: 'batch_delete', ids: ids.join(',') });
      if (current && current.view === targetView && ids.includes(current.item.id)) closeReader(false);
      toast('已删除 ' + ids.length + ' 条记录'); counts(); if (view === targetView) load();
    } catch (error) { toast(error.message); }
  }
  function editTask(item) {
    taskId = item && item.id || null;
    $('dcTaskForm').reset(); $('dcTaskError').hidden = true;
    $('dcTaskForm').querySelector('.dc-task-advanced').open = Boolean(item && item.cron_expression);
    $('dcTaskTitle').textContent = taskId ? '编辑任务' : '新建任务';
    if (item) ['name', 'target_url', 'collect_type', 'is_active', 'cron_expression'].forEach(name => { $('dcTaskForm').elements[name].value = item[name] == null ? '' : item[name]; });
    $('dcTaskDialog').showModal();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0; if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); switchView(tabs[next].dataset.view); tabs[next].focus(); }
    });
  });
  $('dcSearchForm').addEventListener('submit', event => { event.preventDefault(); states[view].keyword = $('dcKeyword').value.trim(); states[view].page = 1; closeReader(false); load(); });
  $('dcSource').addEventListener('change', () => { states[view].source = $('dcSource').value; states[view].page = 1; closeReader(false); load(); });
  $('dcRefresh').addEventListener('click', () => { load(); counts(); });
  $('dcPrev').addEventListener('click', () => { states[view].page--; load(); });
  $('dcNext').addEventListener('click', () => { states[view].page++; load(); });
  $('dcSelectPage').addEventListener('change', event => { selected = event.target.checked ? new Set(rows.map(item => item.id)) : new Set(); selection(); });
  $('dcClearSelection').addEventListener('click', () => { selected.clear(); selection(); });
  $('dcBatchAction').addEventListener('click', () => view === 'warehouse' ? crawl(Array.from(selected)) : remove(Array.from(selected)));
  $('dcStop').addEventListener('click', () => {
    if (!busy) { $('dcProgress').hidden = true; requestAnimationFrame(sizeReader); return; }
    stopQueue = true; $('dcStop').disabled = true; $('dcProgressText').textContent = '当前文章完成后停止，不再开始下一条。';
  });
  $('dcCrawlArticle').addEventListener('click', () => { if (current) crawl([current.result ? current.result.spy_data_id : current.item.id]); });
  $('dcCloseReader').addEventListener('click', () => closeReader());
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('dcTaskDialog').open && current) closeReader(); });
  let resizeFrame = null;
  function scheduleReaderSize() {
    if (resizeFrame !== null) return;
    resizeFrame = requestAnimationFrame(() => { resizeFrame = null; sizeReader(); });
  }
  window.addEventListener('scroll', scheduleReaderSize, { passive: true });
  window.addEventListener('resize', scheduleReaderSize);
  $('dcAddTask').addEventListener('click', () => editTask(null));
  ['dcCancelTask', 'dcCloseTask'].forEach(id => $(id).addEventListener('click', () => $('dcTaskDialog').close()));
  $('dcTaskForm').addEventListener('submit', async event => {
    event.preventDefault(); const data = Object.fromEntries(new FormData(event.target));
    data.name = data.name.trim(); data.target_url = data.target_url.trim();
    if (!data.name || !data.target_url || !/^https?:\/\//i.test(data.target_url)) {
      $('dcTaskError').textContent = '请填写任务名称及有效的 HTTP 或 HTTPS 地址。'; $('dcTaskError').hidden = false; return;
    }
    $('dcSaveTask').disabled = true; $('dcSaveTask').textContent = '正在保存…'; $('dcTaskError').hidden = true;
    try {
      await post(endpoints.tasks, { ...data, action: taskId ? 'edit' : 'add', id: taskId || '' });
      $('dcTaskDialog').close(); toast('任务已保存'); counts(); if (view === 'tasks') load();
    } catch (error) { $('dcTaskError').textContent = error.message; $('dcTaskError').hidden = false; }
    finally { $('dcSaveTask').disabled = false; $('dcSaveTask').textContent = '保存任务'; }
  });
  get('/api/spy_source', { limit: 1000 }).then(result => {
    if (result.code !== 0) return;
    (result.data || []).forEach(source => { const option = el('option', '', source.name); option.value = source.id; $('dcSource').append(option); });
  }).catch(() => {});
  load(); counts();
})();
