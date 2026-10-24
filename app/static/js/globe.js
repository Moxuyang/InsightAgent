/* Local earth texture; a flat map remains usable without WebGL. */
(function () {
  'use strict';
  function Globe(host, options) {
    this.host = host;
    this.options = options;
    this.points = [];
    this.flat = false;
    this.chart = null;
    this.version = 0;
    this.observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(function () {
      if (this.chart) this.chart.resize();
    }.bind(this)) : null;
    if (this.observer) this.observer.observe(host);
  }
  Globe.prototype.clear = function () {
    if (this.chart) { this.chart.dispose(); this.chart = null; }
    this.host.replaceChildren();
  };
  Globe.prototype.render = function (points) {
    this.points = (Array.isArray(points) ? points : []).filter(function (p) {
      return p && Array.isArray(p.value) && p.value[0] != null && p.value[1] != null &&
        Number.isFinite(Number(p.value[0])) && Number.isFinite(Number(p.value[1])) &&
        Math.abs(Number(p.value[0])) <= 180 && Math.abs(Number(p.value[1])) <= 90 && Number(p.count) > 0;
    });
    var self = this;
    this.options.info.replaceChildren();
    this.points.forEach(function (p) {
      var button = document.createElement('button');
      button.type = 'button'; button.className = 'gib-tag';
      button.textContent = String(p.name || '未命名地区') + ' · ' + Number(p.count) + '条';
      button.addEventListener('click', function () { self.focus(p, button); });
      self.options.info.appendChild(button);
    });
    if (!this.points.length) this.options.info.textContent = '暂无可定位的新闻，采集后将在这里展示热点';
    this.draw();
  };
  Globe.prototype.draw = function () {
    this.clear();
    this.syncMode();
    var self = this, version = ++this.version;
    this.options.status.textContent = '地图加载中…';
    var texture = new Image();
    texture.onload = function () {
      if (version !== self.version) return;
      if (self.flat) { self.drawFlat(); return; }
      try {
        var canvas = document.createElement('canvas');
        var gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
        if (!gl) throw new Error('WebGL unavailable');
        var lose = gl.getExtension('WEBGL_lose_context');
        if (lose) lose.loseContext();
        self.chart = echarts.init(self.host);
        self.chart.setOption({
          backgroundColor: '#0d1c35',
          tooltip: { formatter: function (p) {
            return echarts.format.encodeHTML(p.name) + '：' + p.data.count + ' 条新闻';
          } },
          globe: {
            baseTexture: self.options.texture, shading: 'lambert', environment: '#0d1c35',
            globeRadius: 100, globeOuterRadius: 100.5,
            light: { main: { intensity: 1.3, alpha: 35, beta: 120 }, ambient: { intensity: 0.65 } },
            viewControl: { targetCoord: [104, 35], distance: 180, minDistance: 120, maxDistance: 260,
              autoRotate: false, panSensitivity: 0, zoomSensitivity: 0.7 },
            postEffect: { enable: false }
          },
          series: [{ type: 'scatter3D', coordinateSystem: 'globe',
            symbolSize: function (value) { return Math.min(22, 5 + Math.sqrt(value[3]) * 2); },
            itemStyle: { color: '#ffca66', opacity: 0.95 },
            data: self.points.map(function (p) { return {
              name: String(p.name || '未命名地区'), count: Number(p.count),
              value: [Number(p.value[0]), Number(p.value[1]), 0, Number(p.count)]
            }; }) }]
        });
        var glCanvas = self.host.querySelector('canvas');
        if (glCanvas) glCanvas.addEventListener('webglcontextlost', function (event) {
          event.preventDefault(); self.flat = true; self.drawFlat('立体视图暂不可用，已切换到平面地图');
        }, { once: true });
        self.options.status.textContent = '拖动旋转 · 滚轮缩放 · 点击地区定位';
      } catch (error) {
        self.flat = true;
        self.drawFlat('当前设备使用平面地图显示热点');
      }
    };
    texture.onerror = function () {
      if (version !== self.version) return;
      self.options.status.textContent = '地图底图加载失败，请刷新页面重试；下方仍可查看各地区新闻数量';
    };
    texture.src = this.options.texture;
  };
  Globe.prototype.drawFlat = function (message) {
    this.clear();
    this.syncMode();
    var map = document.createElement('div'); map.className = 'earth-flat';
    var image = document.createElement('img'); image.src = this.options.texture; image.alt = '世界地理底图';
    map.appendChild(image);
    var self = this;
    this.points.forEach(function (p, index) {
      var marker = document.createElement('button');
      marker.type = 'button'; marker.className = 'earth-marker';
      marker.dataset.point = index;
      marker.style.left = ((Number(p.value[0]) + 180) / 360 * 100) + '%';
      marker.style.top = ((90 - Number(p.value[1])) / 180 * 100) + '%';
      marker.title = String(p.name) + '：' + Number(p.count) + ' 条新闻';
      marker.setAttribute('aria-label', marker.title);
      marker.addEventListener('click', function () {
        self.focus(p, self.options.info.children[index]);
        self.options.status.textContent = marker.title;
      });
      map.appendChild(marker);
    });
    this.host.appendChild(map);
    this.options.status.textContent = message || '平面视图 · 点击热点或下方地区查看';
  };
  Globe.prototype.focus = function (point, button) {
    Array.from(this.options.info.children).forEach(function (el) {
      el.classList.toggle('active', el === button); el.setAttribute('aria-pressed', String(el === button));
    });
    if (this.chart) this.chart.setOption({ globe: { viewControl: {
      targetCoord: [Number(point.value[0]), Number(point.value[1])], distance: 150, autoRotate: false
    } } });
    var index = this.points.indexOf(point);
    this.host.querySelectorAll('.earth-marker').forEach(function (el) {
      el.classList.toggle('active', Number(el.dataset.point) === index);
    });
    this.options.status.textContent = String(point.name) + '：' + Number(point.count) + ' 条新闻';
  };
  Globe.prototype.syncMode = function () {
    if (!this.options.mode) return;
    this.options.mode.textContent = this.flat ? '立体视图' : '平面视图';
    this.options.mode.setAttribute('aria-pressed', String(this.flat));
  };
  Globe.prototype.toggle = function () { this.flat = !this.flat; this.draw(); };
  Globe.prototype.reset = function () {
    Array.from(this.options.info.children).forEach(function (el) {
      el.classList.remove('active'); el.setAttribute('aria-pressed', 'false');
    });
    this.draw();
  };
  Globe.prototype.dispose = function () {
    ++this.version; this.clear(); if (this.observer) this.observer.disconnect();
  };
  window.InsightGlobe = Globe;
})();
