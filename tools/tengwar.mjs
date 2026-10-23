// 昆雅拉丁转写 → Tengwar（精灵文字母），基于 Glǽmscribe 1.3.1（AGPL-3.0 © Benjamin Babut）
// 用法: node tengwar.mjs "Elen síla lúmenn' omentielvo" [--charset tengwar_telcontar] [--mode quenya-tengwar-classical] [--names]
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const LIB = path.join(ROOT, 'node_modules', 'glaemscribe', 'js');

function evalFile(file) {
  vm.runInThisContext(fs.readFileSync(file, 'utf8'), { filename: file });
}

evalFile(path.join(LIB, 'glaemscribe.js'));
for (const f of fs.readdirSync(path.join(LIB, 'charsets'))) evalFile(path.join(LIB, 'charsets', f));
for (const f of fs.readdirSync(path.join(LIB, 'modes'))) evalFile(path.join(LIB, 'modes', f));

const G = globalThis.Glaemscribe;
// 注册是便宜的（只是把文本存进 raw_*）；解析按需做，避免启动时把所有模式都编一遍

function usage() {
  console.log('用法: node tengwar.mjs "<昆雅拉丁转写>" [--charset NAME] [--mode NAME] [--names] [--json]');
  console.log('可用 charset:', Object.keys(G.resource_manager.raw_charsets).filter(n => /tengwar|eldamar/.test(n)).join(', '));
  console.log('可用 mode   :', Object.keys(G.resource_manager.raw_modes).filter(n => /quenya|sindarin|raw/.test(n)).join(', '));
}

function charNames(charsetName) {
  // charset 的原文（glaeml）里每行形如: \char e02e TELCO [别名...]
  const raw = G.resource_manager.raw_charsets[charsetName] || '';
  const inv = new Map();
  for (const m of raw.matchAll(/^\\char\s+([0-9a-fA-F]+)\s+([A-Z0-9_]+)/gm)) {
    const ch = String.fromCodePoint(parseInt(m[1], 16));
    if (!inv.has(ch)) inv.set(ch, m[2]);
  }
  return inv;
}

const args = process.argv.slice(2);
if (!args.length || args.includes('--help') || args.includes('-h')) { usage(); process.exit(0); }

let text = null, charsetName = 'tengwar_telcontar', modeName = 'quenya-tengwar-classical';
let showNames = false, asJson = false, htmlOut = null;
const opts = {};
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === '--charset') charsetName = args[++i];
  else if (a === '--mode') modeName = args[++i];
  else if (a === '--opt') {            // --opt NAME=VALUE  例: --opt long_vowels_format=LONG_VOWELS_USE_DOUBLE_TEHTAR
    const kv = (args[++i] || '').split('=');
    if (kv.length === 2) opts[kv[0].trim()] = kv[1].trim();
  }
  else if (a === '--names') showNames = true;
  else if (a === '--json') asJson = true;
  else if (a === '--html') htmlOut = args[++i];
  else if (text === null) text = a;
}

G.resource_manager.load_charsets([charsetName]);
G.resource_manager.load_modes([modeName, 'raw-tengwar']);

const charset = G.resource_manager.loaded_charsets[charsetName];
const mode = G.resource_manager.loaded_modes[modeName];
if (!charset) { console.error('没有这个 charset: ' + charsetName); usage(); process.exit(2); }
if (!mode) { console.error('没有这个 mode: ' + modeName); usage(); process.exit(2); }

// 模式选项（长元音写法、a 的形状等）必须在 transcribe 之前 finalize
if (Object.keys(opts).length) {
  if (typeof mode.finalize === 'function') {
    mode.finalize(opts);
  } else {
    console.error('这个模式不支持选项');
  }
}

const [ok, out] = mode.transcribe(text, charset);
if (!ok) { console.error('转写失败: ' + out); process.exit(1); }

const cps = Array.from(out).map(c => 'U+' + c.codePointAt(0).toString(16).toUpperCase().padStart(4, '0'));

if (asJson) {
  console.log(JSON.stringify({ input: text, mode: modeName, charset: charsetName, tengwar: out, codepoints: cps }, null, 2));
  process.exit(0);
}

console.log('输入    : ' + text);
console.log('模式    : ' + modeName + '  字符集: ' + charsetName);
console.log('Tengwar : ' + out);
console.log('码位    : ' + cps.join(' '));

if (showNames) {
  const inv = charNames(charsetName);
  const names = Array.from(out).map(c => inv.get(c) || '?');
  console.log('字符名  : ' + names.join(' '));
}

if (htmlOut) {
  // 自带字体（base64 内嵌）的 HTML：浏览器用 HarfBuzz 排版，tehta 才会叠在 tengwa 上方。
  // PIL/ImageDraw 直接画是不行的——它不会做 GPOS 定位，元音符号会全部掉到字右边。
  const FONT = path.join(ROOT, 'assets', 'tengwar-font', 'FreeMonoTengwar.2013-07-21', 'FreeMonoTengwar.ttf');
  let fontCss = '';
  if (fs.existsSync(FONT)) {
    fontCss = `@font-face{font-family:'TengwarEmb';src:url(data:font/ttf;base64,${fs.readFileSync(FONT).toString('base64')}) format('truetype');}`;
  }
  const esc = (s) => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const html = `<!doctype html>
<html lang="zh"><meta charset="utf-8">
<title>Tengwar · ${esc(text)}</title>
<style>
${fontCss}
body{margin:0;background:#f7f5f0;color:#1c1a17;font-family:Georgia,'Songti SC',serif}
.wrap{max-width:1000px;margin:0 auto;padding:56px 40px 64px}
.label{font:600 12px/1 ui-sans-serif,system-ui;letter-spacing:.14em;text-transform:uppercase;color:#8a8377}
.latin{margin:10px 0 2px;font-size:30px;line-height:1.5}
.meta{color:#6d675d;font-size:14px;margin-top:4px}
.tengwar{font-family:'TengwarEmb',serif;font-size:72px;line-height:1.5;margin:44px 0 8px;word-break:break-word}
.cps{font:12px/1.7 ui-monospace,Menlo,Consolas,monospace;color:#9a9285;word-break:break-all}
hr{border:0;border-top:1px solid #dcd6ca;margin:40px 0}
</style>
<div class="wrap">
  <div class="label">昆雅 · Tengwar</div>
  <div class="latin">${esc(text)}</div>
  <div class="meta">模式 ${esc(modeName)} · 字符集 ${esc(charsetName)}</div>
  <div class="tengwar" id="tw">${esc(out)}</div>
  <hr>
  <div class="cps">${cps.join(' ')}</div>
</div>
</html>`;
  fs.writeFileSync(htmlOut, html, 'utf8');
  console.log('HTML    : ' + htmlOut + (fontCss ? '（字体已内嵌）' : '（警告：没找到 FreeMonoTengwar.ttf，字体未内嵌）'));
}
