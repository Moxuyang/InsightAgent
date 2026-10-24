/* Incremental SSE decoding shared by the news QA page and protocol tests. */
(function (root) {
  'use strict';
  const pendingText = new WeakMap();
  let markdownReady;
  function ensureMarkdown() {
    if (root.marked && root.DOMPurify) return Promise.resolve();
    if (!markdownReady) {
      const load = (path) => new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/static/vendor/' + path;
        script.onload = resolve;
        script.onerror = () => reject(new Error('回答排版组件加载失败，请刷新页面重试。'));
        document.head.appendChild(script);
      });
      markdownReady = Promise.resolve()
        .then(() => root.marked ? null : load('marked.umd.js'))
        .then(() => root.DOMPurify ? null : load('purify.min.js'))
        .catch(error => { markdownReady = null; throw error; });
    }
    return markdownReady;
  }
  function renderMarkdown(element, text) {
    if (!element) return;
    text = String(text || '');
    pendingText.set(element, text);
    element.classList.add('qa-markdown');
    if (!root.marked || !root.DOMPurify) {
      element.textContent = '正在排版回答…';
      ensureMarkdown().then(() => {
        if (pendingText.get(element) === text) renderMarkdown(element, text);
      }).catch(error => {
        if (pendingText.get(element) === text) element.textContent = error.message;
      });
      return;
    }
    const html = root.marked.parse(String(text || ''), {gfm:true, breaks:true, async:false});
    element.innerHTML = root.DOMPurify.sanitize(html, {
      ALLOWED_TAGS:['p','br','strong','em','del','h1','h2','h3','h4','h5','h6','ul','ol','li','blockquote','pre','code','hr','table','thead','tbody','tr','th','td','a'],
      ALLOWED_ATTR:['href','title','start','colspan','rowspan'],
      ALLOW_DATA_ATTR:false
    });
    element.querySelectorAll('a').forEach(link => {
      try {
        const url = new URL(link.getAttribute('href'));
        if (!['http:','https:','mailto:'].includes(url.protocol)) throw new Error('Unsupported URL');
        link.setAttribute('target','_blank'); link.setAttribute('rel','noopener noreferrer');
      } catch (_) { link.removeAttribute('href'); }
    });
  }
  function createParser(onEvent) {
    let buffer = '';
    function parse(frame) {
      const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
      if (!data || data === '[DONE]') return;
      onEvent(JSON.parse(data));
    }
    return {
      push(text) {
        buffer += text;
        // Normalize CRLF after combining chunks, including split CR/LF boundaries.
        buffer = buffer.replace(/\r\n/g, '\n');
        let at;
        while ((at = buffer.indexOf('\n\n')) >= 0) {
          const frame = buffer.slice(0, at); buffer = buffer.slice(at + 2); parse(frame);
        }
      },
      finish() { if (buffer.trim()) parse(buffer); buffer = ''; }
    };
  }
  async function stream(body, xsrf, onEvent) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000);
    let reader;
    try {
      const response = await fetch('/api/news_qa', {
        method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded','X-XSRFToken':xsrf},
        body:new URLSearchParams({...body, _xsrf:xsrf}), signal:controller.signal
      });
      if (!response.ok) {
        let error;
        try { error = (await response.json()).error; } catch (_) {}
        throw new Error(error || '请求失败（' + response.status + '）');
      }
      if (!response.body || !response.headers.get('Content-Type')?.includes('text/event-stream')) throw new Error('会话已失效或服务返回异常，请刷新后重试。');
      let complete = false;
      const parser = createParser(event => {
        if (event.error) throw new Error(event.error);
        if (event.type === 'done') complete = true;
        onEvent(event);
      });
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        parser.push(decoder.decode(result.value, {stream:true}));
      }
      parser.push(decoder.decode()); parser.finish();
      if (!complete) throw new Error('连接中断，回答尚未保存，请重试。');
    } finally {
      clearTimeout(timeout);
      if (reader) { try { await reader.cancel(); } catch (_) {} reader.releaseLock(); }
    }
  }
  function plainText(text) {
    const element = document.createElement('div');
    renderMarkdown(element, text);
    return element.textContent;
  }
  root.NewsQa = {createParser, stream, renderMarkdown, ensureMarkdown, plainText};
  if (typeof module !== 'undefined') module.exports = root.NewsQa;
})(typeof window === 'undefined' ? globalThis : window);
