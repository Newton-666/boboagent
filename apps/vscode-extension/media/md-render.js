/**
 * md-render.js — TICKET-VSC-1C markdown 渲染管线（复刻桌面端 mdReply）。
 *
 * 复刻基准：apps/desktop/dist/index.html:1315-1360（mdReply）+ :390-420（元素样式）
 *   管线：marked.parse（gfm + 自定义 code renderer：hljs 高亮）→ DOMPurify.sanitize
 *   流式半截语法（表格/代码块未闭合）由 marked 容错 + DOMPurify 兜底，绝不 throw。
 *
 * 双环境：
 *   - 浏览器：vendor 脚本先加载（window.marked / window.DOMPurify / window.hljs），
 *     挂 window.mdRender（CSP nonce 下以外部脚本引入）。
 *   - Node（单测）：require 本模块自动加载 media/vendor/*.min.js。
 *     DOMPurify 在 Node 无 DOM 时是工厂函数（无 .sanitize）→ 用 lightSanitize
 *     字符串级净化兜底（仅测试路径；生产浏览器端始终走完整 DOMPurify）。
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(
      require('./vendor/marked.min.js'),
      require('./vendor/purify.min.js'),
      require('./vendor/highlight.min.js'),
    );
  } else {
    root.mdRender = factory(root.marked, root.DOMPurify, root.hljs);
  }
})(typeof self !== 'undefined' ? self : this, function (marked, purify, hljs) {
  'use strict';

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /**
   * 轻量净化（Node 测试路径兜底；生产浏览器端用 DOMPurify.sanitize）：
   * 字符串级剥离脚本/事件/危险标签，保留 marked 输出结构（pre/code/table/strong…）。
   */
  function lightSanitize(html) {
    return String(html)
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<iframe[\s\S]*?<\/iframe>/gi, '')
      .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
      .replace(/\shref\s*=\s*["']?\s*javascript:[^"'\s>]*/gi, '')
      .replace(/\ssrc\s*=\s*["']?\s*javascript:[^"'\s>]*/gi, '');
  }

  // 归一化 DOMPurify：浏览器 window.DOMPurify 是实例（有 .sanitize）；
  // Node require 得到工厂函数（无 .sanitize）→ 轻量净化兜底
  var sanitizer = (purify && typeof purify.sanitize === 'function')
    ? purify
    : { sanitize: lightSanitize };

  var inited = false;

  /**
   * 渲染 markdown → 净化后的 HTML。vendor 未就绪回退纯文本转义（正文不丢）。
   * @param {string|null|undefined} s
   * @returns {string}
   */
  function mdRender(s) {
    s = (s == null) ? '' : String(s);
    try {
      if (marked && sanitizer) {
        if (!inited) {
          inited = true;
          marked.setOptions({
            gfm: true,
            breaks: false,
            renderer: (function () {
              var r = new marked.Renderer();
              // VSC-2D：裸 HTML 文本化（对齐桌面端 esc 行为）——marked GFM 默认把
              // inline HTML 当真渲染成 DOM（DOMPurify 又允许 div），bobo 回复里的
              // <div class="card"> 等代码片段会变成真实元素（字灰/被盖住/整段不可读）。
              // 只转义 < >（不碰 &，防已转义实体如 &quot; 被双转义成 &amp;quot;），
              // 转义后由 DOMPurify 当纯文本输出；代码块走 r.code（不受影响）。
              // v12 签名：renderer.html(text, block)——第一参数即 HTML 字符串。
              r.html = function (html) {
                return String(html).replace(/</g, '&lt;').replace(/>/g, '&gt;');
              };
              // 代码块高亮：highlight.js 本地 vendor，只对已注册语言着色，未知语言原样转义
              r.code = function (code, lang) {
                var l = (lang || '').trim().toLowerCase();
                var html;
                if (hljs && l && hljs.getLanguage(l)) {
                  try { html = hljs.highlight(code, { language: l, ignoreIllegals: true }).value; }
                  catch (e) { html = esc(code); }
                } else { html = esc(code); }
                return '<pre><code' + (l ? ' class="language-' + esc(l) + '"' : '') + '>' + html + '</code></pre>';
              };
              return r;
            })()
          });
        }
        var out = marked.parse(s);
        return sanitizer.sanitize(out, { USE_PROFILES: { html: true } });
      }
      return esc(s);
    } catch (e) {
      try { return esc(s); } catch (e2) { return ''; }
    }
  }

  return { mdRender: mdRender, esc: esc };
});
