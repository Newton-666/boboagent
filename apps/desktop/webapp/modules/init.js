/on* 事件/iframe 等一律清除）
      out = window.DOMPurify.sanitize(out, { USE_PROFILES: { html: true } });
    } else {
      // vendor 未就绪（理论不发生：本地引入）：回退既有简渲染
      out = md(s);
    }
    // TICKET-GUI-F16：数学公式还原（KaTeX 渲染；降级/失败原样文本，绝不 throw）
    out = restoreMath(out, mathPack.placeholders);
    if (handoffCard) { out = out.replace(/%%HANDOFF_CARD%%/g, handoffCard.card); }
    if (worktreeCard) { out = out.replace(/%%WORKTREE_CARD%%/g, worktreeCard.card); }
    return out;
  } catch (e) {
    // 兜底：任何异常不回退页面 —— 先试既有管线，再退纯文本转义
    try { return md(s); } catch (e2) { return esc(s); }
  }
}
