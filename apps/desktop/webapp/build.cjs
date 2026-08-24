#!/usr/bin/env node
/* 砌墙+分家：webapp/ 源码（index.html 占位 + styles.css + modules/*.js + vendor）
   → dist/index.html（占位符 split/join + 模块按序拼接，输出逐字节一致）。
   不用 String.replace（会解释 $ 特殊模式，破坏 $$ 数学公式）。 */
const fs = require('fs');
const path = require('path');

const SRC = __dirname;
const DIST = path.join(__dirname, '..', 'dist');
const MODULES = ['init.js', 'render_core.js', 'panels.js', 'sessions.js',
                 'input_mode.js', 'settings.js', 'telescope_render.js'];

function main() {
  let html = fs.readFileSync(path.join(SRC, 'index.html'), 'utf-8');
  const style = fs.readFileSync(path.join(SRC, 'styles.css'), 'utf-8');
  const app = MODULES.map((m) =>
    fs.readFileSync(path.join(SRC, 'modules', m), 'utf-8') + '\n'
  ).join('');
  html = html.split('/*__STYLES__*/').join(style);
  html = html.split('/*__APPJS__*/').join(app);
  fs.mkdirSync(DIST, { recursive: true });
  fs.writeFileSync(path.join(DIST, 'index.html'), html, 'utf-8');
  fs.cpSync(path.join(SRC, 'vendor'), path.join(DIST, 'vendor'), { recursive: true });
  console.log('dist/index.html 已生成（模块化源码 → 逐字节一致产物）');
}
main();
