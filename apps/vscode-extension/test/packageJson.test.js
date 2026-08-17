// packageJson.test.js — TICKET-VSC-1B static assertions (side-bar registration)
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));

test('contributes.viewsContainers.activitybar 注册 bobo 容器（Bug 1 修复）', () => {
  const containers = pkg.contributes.viewsContainers.activitybar;
  assert.ok(Array.isArray(containers));
  const bobo = containers.find((c) => c.id === 'bobo');
  assert.ok(bobo, 'activitybar 容器缺失 id=bobo');
  assert.strictEqual(bobo.title, 'bobo');
  assert.ok(bobo.icon && bobo.icon.startsWith('media/'), '图标必须指向 media/ 下的 SVG');
});

test('contributes.views.bobo 注册 boboChat 视图（容器 id 是 views 的 key）', () => {
  assert.ok(pkg.contributes.views, 'contributes.views 缺失');
  const views = pkg.contributes.views.bobo;
  assert.ok(Array.isArray(views), 'views.bobo 必须存在（key = 容器 id）');
  const chat = views.find((v) => v.id === 'boboChat');
  assert.ok(chat, 'boboChat 视图缺失');
  assert.strictEqual(chat.name, 'Chat');
});

test('activationEvents 含 onView:boboChat', () => {
  assert.ok(pkg.activationEvents.includes('onView:boboChat'), 'activationEvents 缺 onView:boboChat');
});
