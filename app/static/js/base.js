/* Read the shared theme for canvas/chart libraries that cannot resolve CSS variables. */
window.InsightTheme = {
  accent: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),
  alpha: function(opacity) {
    var color = this.accent.replace('#', '');
    if (color.length !== 6) return this.accent;
    return 'rgba(' + parseInt(color.slice(0, 2), 16) + ',' + parseInt(color.slice(2, 4), 16) + ',' + parseInt(color.slice(4, 6), 16) + ',' + opacity + ')';
  }
};
/* Shared progressive enhancements; business requests remain in each page. */
(function () {
  'use strict';
  var nextFieldId = 0;
  var pending = false;

  function positionSelectMenus() {
    document.querySelectorAll('.layui-form-selected').forEach(function (select) {
      var menu = select.querySelector('dl');
      if (!menu) return;
      var scroller = select.closest('.admin-layer-content, .layui-layer-content');
      var bounds = scroller ? scroller.getBoundingClientRect() : {top: 0, bottom: window.innerHeight};
      var field = select.getBoundingClientRect();
      var below = Math.min(bounds.bottom, window.innerHeight) - field.bottom - 12;
      var above = field.top - Math.max(bounds.top, 0) - 12;
      var upwards = below < Math.min(menu.scrollHeight, 300) && above > below;
      select.classList.toggle('insight-select-up', upwards);
      menu.style.maxHeight = Math.max(40, Math.min(300, upwards ? above : below)) + 'px';
    });
  }

  function enhance() {
    pending = false;
    document.querySelectorAll('.admin-form-container').forEach(function (form) {
      if (form.querySelector('[required]') && !form.querySelector('.form-editor-note')) {
        var note = document.createElement('p');
        note.className = 'form-editor-note';
        note.textContent = '带 * 的项目为必填，其余可按需配置。';
        form.prepend(note);
      }
    });
    document.querySelectorAll('.layui-form-item').forEach(function (item) {
      var label = item.querySelector('.layui-form-label');
      var control = item.querySelector('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea, select');
      if (!label || !control) return;
      if (!control.id) control.id = 'insight-field-' + (++nextFieldId);
      if (label.tagName === 'LABEL') label.htmlFor = control.id;
      if (!control.hasAttribute('aria-label')) control.setAttribute('aria-label', label.textContent.trim());
      if (control.required) {
        label.classList.add('insight-required');
        control.setAttribute('aria-required', 'true');
        if (!control.hasAttribute('lay-verify')) control.setAttribute('lay-verify', 'required');
        if (!control.hasAttribute('lay-reqtext')) control.setAttribute('lay-reqtext', '请填写' + label.textContent.trim());
      }
      if (control.tagName === 'SELECT') {
        var rendered = control.nextElementSibling;
        var input = rendered && rendered.querySelector('.layui-input');
        if (input) input.setAttribute('aria-label', label.textContent.trim());
      }
    });
    document.querySelectorAll('a[lay-event]:not([href])').forEach(function (el) {
      el.setAttribute('role', 'button'); el.setAttribute('tabindex', '0');
    });
    document.querySelectorAll('button[title]:not([aria-label])').forEach(function (el) {
      el.setAttribute('aria-label', el.title);
    });
    document.querySelectorAll('.layui-table-view').forEach(function (view) {
      var main = view.querySelector('.layui-table-main');
      if (!main) return;
      var hint = view.previousElementSibling;
      if (!hint || !hint.classList.contains('table-scroll-hint')) {
        hint = document.createElement('p');
        hint.className = 'table-scroll-hint';
        hint.textContent = '表格可左右滚动，查看更多字段和操作';
        view.before(hint);
      }
      hint.hidden = main.scrollWidth <= main.clientWidth + 1;
      if (!hint.hidden) {
        main.setAttribute('tabindex', '0');
        main.setAttribute('role', 'region');
        main.setAttribute('aria-label', '数据表格，可左右滚动');
      } else {
        main.removeAttribute('tabindex');
      }
    });
  }
  function scheduleEnhance() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(enhance);
  }

  document.addEventListener('click', function (event) {
    if (event.target.closest('.layui-form-select')) requestAnimationFrame(positionSelectMenus);
  });
  document.addEventListener('keydown', function (event) {
    var action = event.target.closest('a[lay-event]:not([href])');
    if (action && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault(); action.click();
    }
  });

  if (window.layui) {
    layui.use(['layer'], function () {
      var layer = layui.layer;
      var originalOpen = layer.open;
      layer.open = function (options) {
        var settings = Object.assign({}, options);
        if (settings.type === 1) settings.scrollbar = false;
        var width = Math.max(240, document.documentElement.clientWidth - 32);
        var height = Math.max(160, window.innerHeight - 32);
        var area = settings.area;
        if (Array.isArray(area)) {
          area = area.slice();
          if (/^\d+(\.\d+)?px$/.test(area[0])) area[0] = Math.min(parseFloat(area[0]), width) + 'px';
          if (/^\d+(\.\d+)?px$/.test(area[1])) area[1] = Math.min(parseFloat(area[1]), height) + 'px';
          settings.area = area;
        }
        settings.maxWidth = Math.min(settings.maxWidth || width, width);
        var success = settings.success;
        var end = settings.end;
        var opener = document.activeElement;
        settings.success = function (element, index, that) {
          if (success) success.call(this, element, index, that);
          var dialog = element[0];
          if (dialog && settings.type === 1) {
            // Several editors insert selects without rendering Layui controls.
            if (dialog.querySelector('.layui-form')) {
              layui.use(['form'], function () { layui.form.render(); });
            }
            dialog.setAttribute('role', 'dialog');
            dialog.setAttribute('aria-modal', 'true');
            var title = dialog.querySelector('.layui-layer-title');
            if (title) { title.id = title.id || 'insight-dialog-title-' + index; dialog.setAttribute('aria-labelledby', title.id); }
            var close = dialog.querySelector('.layui-layer-close');
            if (close) { close.setAttribute('role', 'button'); close.setAttribute('aria-label', '关闭弹窗'); close.setAttribute('tabindex', '0'); }
            dialog.addEventListener('keydown', function (event) {
              if (event.key === 'Escape' && !dialog.querySelector('.layui-form-selected')) { event.preventDefault(); layer.close(index); }
              if (event.key === 'Enter' && event.target === close) { event.preventDefault(); layer.close(index); }
              if (event.key !== 'Tab') return;
              var fields = Array.from(dialog.querySelectorAll('a, button, input, textarea, select, [tabindex="0"]')).filter(function (el) { return !el.disabled && el.getClientRects().length && el.tabIndex >= 0; });
              if (!fields.length) return;
              var first = fields[0], last = fields[fields.length - 1];
              if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
              else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
            });
            requestAnimationFrame(function () {
              var firstInput = Array.from(dialog.querySelectorAll('input:not([type=hidden]), textarea, button, [tabindex="0"]')).find(function (el) { return !el.disabled && el.getClientRects().length; });
              if (firstInput) firstInput.focus({preventScroll:true});
            });
          }
          scheduleEnhance();
        };
        settings.end = function () {
          if (end) end.apply(this, arguments);
          if (opener && opener.isConnected) opener.focus({preventScroll:true});
        };
        return originalOpen.call(this, settings);
      };
    });
  }

  window.addEventListener('resize', function () {
    document.querySelectorAll('.layui-layer-page, .layui-layer-iframe').forEach(function (dialog) {
      var bounds = dialog.getBoundingClientRect();
      var width = Math.min(bounds.width, document.documentElement.clientWidth - 32);
      dialog.style.width = width + 'px';
      dialog.style.left = Math.max(16, Math.min(bounds.left, window.innerWidth - width - 16)) + 'px';
      dialog.style.top = Math.max(16, Math.min(bounds.top, window.innerHeight - Math.min(bounds.height, window.innerHeight - 32) - 16)) + 'px';
    });
    scheduleEnhance();
  });
  function startEnhancements() {
    new MutationObserver(scheduleEnhance).observe(document.body, {childList:true, subtree:true});
    scheduleEnhance();
  }
  if (document.body) startEnhancements();
  else document.addEventListener('DOMContentLoaded', startEnhancements, {once:true});
})();
