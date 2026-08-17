/**
 * contrast.ts — TICKET-VSC-2A WCAG 对比度计算（纯函数，可单测）。
 *
 * 相对亮度公式（WCAG 2.x）：
 *   L = 0.2126·R + 0.7152·G + 0.0722·B，其中 R/G/B 为 sRGB 线性化值。
 * 对比度 = (L1+0.05)/(L2+0.05)。
 *
 * 面板内容文字硬性要求：对所在背景 ≥ 4.5:1（WCAG AA）。
 * 色值变更必须在此登记（票禁止项：新色值逐个对照票基准）：
 *   --text         #2d2d2d（不变，主内容文字 13:1）
 *   --text2        #777 → #5c5c5c（次级内容：.who/状态栏/选区头/explain/代码注释）
 *   --text-muted   #999 → #6f6f6f（仅占位符/装饰，退出内容文字）
 *   关键词橙       #e8913a → #a34e1a（hljs-keyword/built_in，4.66:1 vs --bg3）
 *   字符串绿       #50a14f → #2f6b2e（hljs-string/regexp/addition，5.23:1 vs --bg3）
 *   数字黄褐       #8a6d3b → #7a5f32（hljs-number/literal，4.86:1 vs --bg3）
 *   diff 增色      #7ec87b → #2f6b2e（.diff-add，与字符串绿同值）
 *   diff 删色      #f48771 → #b3402a（.diff-del/.hljs-deletion，4.64:1 vs --bg3）
 */

export function hexToRgb(hex: string): [number, number, number] {
  const c = hex.replace('#', '');
  if (c.length !== 6) throw new Error(`hexToRgb: 需要 6 位 hex，收到 "${hex}"`);
  return [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16)) as [number, number, number];
}

/** sRGB 线性化（0..1）。 */
function linearize(v: number): number {
  const s = v / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

/** WCAG 相对亮度 0..1。 */
export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

/** 两色对比度（≥1）。 */
export function contrastRatio(fg: string, bg: string): number {
  const [l1, l2] = [relativeLuminance(fg), relativeLuminance(bg)].sort((a, b) => b - a);
  return (l1 + 0.05) / (l2 + 0.05);
}

/** 面板色板（与 chatPanel.ts 的 :root 一一对应，测试据此断言）。 */
export const PALETTE = {
  bg: '#faf9f2',
  bg2: '#f2f1e8',
  bg3: '#eae8dc',
  text: '#2d2d2d',
  text2: '#5c5c5c',
  textMuted: '#6f6f6f',
  accentOrange: '#a34e1a', // 关键词橙（hljs-keyword/built_in/strong）
  stringGreen: '#2f6b2e',  // 字符串绿（hljs-string/regexp/addition/diff-add）
  numberBrown: '#7a5f32',  // 数字黄褐（hljs-number/literal）
  diffDel: '#b3402a',      // diff 删色（diff-del/hljs-deletion）
} as const;

/** 断言某前景色在给定背景上的对比度 ≥ min（默认 4.5）。测试与治理共用。 */
export function assertContrast(fg: string, bg: string, min = 4.5): number {
  const r = contrastRatio(fg, bg);
  if (r < min) {
    throw new Error(`对比度不足: ${fg} vs ${bg} = ${r.toFixed(2)} < ${min}`);
  }
  return r;
}
