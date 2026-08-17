/**
 * markdown.ts — minimal safe Markdown renderer for the chat webview.
 *
 * Security model (DOMPurify-style): every user/server-controlled string is
 * HTML-escaped FIRST; only known-safe structural tags are produced afterwards.
 * No raw HTML passthrough, ever. Pure logic — unit-testable.
 */

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Strip the thinking block (same regex as index.html splitThinking, F1-2). */
export function splitThinking(s: string): { body: string; thinking: string } {
  if (!s) return { body: '', thinking: '' };
  const m = s.match(/(?:^|\n)──\s*💭\s*思考过程\s*──\n([\s\S]*?)(?:──\s*思考结束\s*(?:──)?[^\n]*\n?)?$/);
  if (m) {
    return { body: s.slice(0, m.index).trim(), thinking: m[1].trim() };
  }
  return { body: s.trim(), thinking: '' };
}

/** Very small syntax highlighter for fenced code blocks. */
export function highlightCode(code: string, lang: string): string {
  const esc = escapeHtml(code);
  let kwRe: RegExp | null = null;
  if (lang === 'python') {
    kwRe = /\b(?:def|class|return|import|from|if|elif|else|for|while|try|except|finally|with|as|pass|lambda|not|and|or|None|True|False|async|await|raise|yield)\b/;
  } else if (lang === 'typescript' || lang === 'javascript' || lang === 'ts' || lang === 'js') {
    kwRe = /\b(?:const|let|var|function|return|if|else|for|while|try|catch|finally|new|class|extends|import|from|export|default|async|await|typeof|instanceof|this|null|undefined|true|false|switch|case|break|continue|throw|interface|type|enum)\b/;
  }
  let out = esc;
  if (kwRe) {
    out = out.replace(new RegExp('(' + kwRe.source + ')', 'g'), '<span class="tok-kw">$1</span>');
  }
  // strings
  out = out.replace(/(&quot;.*?&quot;|&#39;.*?&#39;)/g, '<span class="tok-str">$1</span>');
  // comments
  out = out.replace(/(#[^\n]*|\/\/.*|\/\*[\s\S]*?\*\/)/g, '<span class="tok-cmt">$1</span>');
  return out;
}

/** Render markdown text to safe HTML. */
export function renderMarkdown(src: string): string {
  const lines = src.split(/\r?\n/);
  const out: string[] = [];
  let i = 0;
  let inCode = false;
  let codeBuf: string[] = [];
  let codeLang = '';
  let inList = false;

  const closeList = () => { if (inList) { out.push('</ul>'); inList = false; } };

  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith('```')) {
      if (inCode) {
        out.push(`<pre><code>${highlightCode(codeBuf.join('\n'), codeLang)}</code></pre>`);
        codeBuf = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
        codeLang = line.trim().slice(3).trim();
      }
      i++;
      continue;
    }
    if (inCode) { codeBuf.push(line); i++; continue; }

    const t = line.trim();
    if (!t) { closeList(); i++; continue; }

    // headings
    const h = t.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      closeList();
      const lvl = h[1].length;
      out.push(`<h${lvl}>${renderInline(h[2])}</h${lvl}>`);
      i++;
      continue;
    }
    // blockquote
    if (t.startsWith('>')) {
      closeList();
      out.push(`<blockquote>${renderInline(t.slice(1).trim())}</blockquote>`);
      i++;
      continue;
    }
    // unordered list
    const ul = t.match(/^[-*]\s+(.*)$/);
    if (ul) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${renderInline(ul[1])}</li>`);
      i++;
      continue;
    }
    // ordered list
    const ol = t.match(/^\d+\.\s+(.*)$/);
    if (ol) {
      if (!inList) { out.push('<ul class="ol">'); inList = true; }
      out.push(`<li>${renderInline(ol[1])}</li>`);
      i++;
      continue;
    }
    closeList();
    // horizontal rule
    if (/^(-{3,}|\*{3,})$/.test(t)) { out.push('<hr>'); i++; continue; }
    // paragraph
    let para = t;
    while (i + 1 < lines.length && lines[i + 1].trim() && !lines[i + 1].trim().startsWith('```')) {
      para += ' ' + lines[i + 1].trim();
      i++;
    }
    out.push(`<p>${renderInline(para)}</p>`);
    i++;
  }
  closeList();
  if (inCode) out.push(`<pre><code>${highlightCode(codeBuf.join('\n'), codeLang)}</code></pre>`);
  return out.join('\n');
}

function renderInline(s: string): string {
  let t = escapeHtml(s);
  // inline code
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  // bold
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // links — only http(s), href is re-escaped (no javascript:)
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return t;
}
