/* 昆雅 · 手机版（PWA）
   内核和桌面版共用一套内容：mobile/export.py 从同一条 course.py 管道导出，
   所以这里的 180 词 / 244 句和桌面上看到的一模一样。
   进度存在 localStorage，排期算法照搬 course.py 的简化 SM-2（LADDER）。 */

'use strict';

const LADDER = [1, 2, 4, 8, 16, 32, 64];
const LS_KEY = 'quenya.mobile.v1';
const SPEECH_CN = {
  n: '名', adj: '形', vb: '动', adv: '副', pron: '代', prep: '介', conj: '连',
  interj: '叹', particle: '助', cardinal: '数', ordinal: '序', phrase: '短语',
  suf: '后缀', pref: '前缀', root: '词根', article: '冠', 'proper-name': '专名',
  name: '名',
};

let DATA = null;
let WORDS = [];          // 课程里出现的 180 个词，兼作干扰项池
let BY_UID = {};         // uid -> 词
let TW = null;           // Tengwar 转写器
let state = null;
let session = null;
let stack = [{ name: 'learn' }];
const twCache = new Map();

const app = () => document.getElementById('app');

/* ---------------------------------------------------------------- 小工具 */

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function formKey(s) {
  if (!s) return '';
  return s.replace(/[\u2019\u2018\u02bc]/g, "'").replace(/[\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079]/g, '')
    .trim().toLowerCase();
}

function formFold(s) {
  return formKey(s).replace(/'/g, '').normalize('NFD').replace(/\p{Mn}/gu, '');
}

function displayForm(f) {
  return String(f || '').replace(/\s*\([^)]*\)/g, '').replace(/[\u00b9\u00b2\u00b3\u2074-\u2079]/g, '').trim();
}

function shortGloss(g, n) {
  n = n || 46;
  const s = String(g || '').split(';')[0].split(',')[0].trim();
  return s.length <= n ? s : s.slice(0, n) + '…';
}

function pad2(n) { return n < 10 ? '0' + n : String(n); }
function today() {
  const d = new Date();
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
}
function addDays(iso, n) {
  const d = new Date(iso + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
}

function shuffle(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const t = a[i]; a[i] = a[j]; a[j] = t;
  }
  return a;
}

function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('on');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove('on'), 1800);
}

/* ---------------------------------------------------------------- Tengwar */

function tw(text) {
  if (!TW || !text) return '';
  if (twCache.has(text)) return twCache.get(text);
  let out = '';
  try {
    const r = TW.md.transcribe(text, TW.cs);
    if (r && r[0]) out = r[1];
  } catch (e) {
    out = '';
  }
  twCache.set(text, out);
  return out;
}

function initTW() {
  try {
    const G = window.Glaemscribe;
    if (!G) return null;
    G.resource_manager.load_charsets(['tengwar_telcontar']);
    G.resource_manager.load_modes(['quenya-tengwar-classical', 'raw-tengwar']);
    const cs = G.resource_manager.loaded_charsets['tengwar_telcontar'];
    const md = G.resource_manager.loaded_modes['quenya-tengwar-classical'];
    if (!cs || !md) return null;
    const probe = md.transcribe('Elen síla', cs);
    if (!probe || !probe[0]) return null;
    return { cs: cs, md: md };
  } catch (e) {
    console.warn('Tengwar 转写不可用', e);
    return null;
  }
}

/* ---------------------------------------------------------------- 进度 */

function loadState() {
  let s = null;
  try { s = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) { s = null; }
  s = s || {};
  s.cards = s.cards || {};
  s.xp = s.xp || {};
  s.done = s.done || [];
  s.streak = s.streak || { count: 0, last: null };
  return s;
}

function save() {
  try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch (e) { /* 隐私模式 */ }
}

function cardKey(w) { return 'q|' + formKey(w.f); }

function gradeCard(w, correct) {
  const k = cardKey(w);
  const c = state.cards[k] || { iv: 0, reps: 0, lapses: 0, ef: 2.5 };
  if (correct) {
    const i = LADDER.indexOf(c.iv);
    c.iv = LADDER[Math.min(i >= 0 ? i + 1 : 1, LADDER.length - 1)];
    c.reps = (c.reps || 0) + 1;
    c.ef = Math.min(3.0, (c.ef || 2.5) + 0.05);
  } else {
    c.iv = 1;
    c.lapses = (c.lapses || 0) + 1;
    c.ef = Math.max(1.3, (c.ef || 2.5) - 0.15);
    c.reps = 0;
  }
  const t = today();
  c.due = addDays(t, c.iv);
  c.last = t;
  c.uid = w.u; c.f = w.f; c.g = w.g;
  state.cards[k] = c;
  save();
}

function dueCards() {
  const t = today();
  return Object.keys(state.cards)
    .filter((k) => !state.cards[k].due || state.cards[k].due <= t)
    .map((k) => state.cards[k]);
}

function addXP(n) {
  const t = today();
  state.xp[t] = (state.xp[t] || 0) + n;
}

function xpToday() { return state.xp[today()] || 0; }

function touchStreak() {
  const s = state.streak;
  const t = today();
  if (s.last === t) return s.count;
  const y = addDays(t, -1);
  s.count = (s.last === y ? (s.count || 0) + 1 : 1);
  s.last = t;
  return s.count;
}

/* ---------------------------------------------------------------- 题目 */

function pickDistractors(w, n) {
  const seen = new Set([formKey(w.f)]);
  const cands = [];
  for (let i = 0; i < WORDS.length; i++) {
    const x = WORDS[i];
    const k = formKey(x.f);
    if (seen.has(k) || !x.g) continue;
    seen.add(k);
    cands.push(x);
  }
  return shuffle(cands).slice(0, n || 3);
}

function makeQuestion(w) {
  const wrong = pickDistractors(w, 3);
  const kinds = ['k2e', 'e2k', 'spell'];
  if (TW) kinds.push('tengwar');
  let kind = kinds[Math.floor(Math.random() * kinds.length)];
  if (kind !== 'spell' && wrong.length < 3) kind = 'spell';

  const form = displayForm(w.f);
  const gloss = shortGloss(w.g);

  if (kind === 'k2e') {
    const opts = shuffle([gloss].concat(wrong.map((x) => shortGloss(x.g))));
    return {
      kind: 'k2e', label: '这个词什么意思', word: w,
      promptHtml: '<div class="p-big serif">' + esc(form) + '</div><div class="p-sub">昆雅</div>',
      options: opts, answer: gloss,
    };
  }
  if (kind === 'e2k' || kind === 'tengwar') {
    const opts = shuffle([form].concat(wrong.map((x) => displayForm(x.f))));
    const t = kind === 'tengwar' ? tw(w.f) : '';
    if (kind === 'tengwar' && !t) kind = 'e2k';
    return {
      kind: kind, label: kind === 'tengwar' ? '读出这串精灵文字母' : '选昆雅词', word: w,
      promptHtml: kind === 'tengwar'
        ? '<div class="tw tw-big">' + esc(t) + '</div><div class="p-sub">Tengwar</div>'
        : '<div class="p-big">' + esc(gloss) + '</div><div class="p-sub">意思</div>',
      options: opts, answer: form,
    };
  }
  return {
    kind: 'spell', label: '写出昆雅词', word: w,
    promptHtml: '<div class="p-big">' + esc(gloss) + '</div><div class="p-sub">意思</div>',
    options: null, answer: form, hint: form.slice(0, 1) + '…',
  };
}

/* ---------------------------------------------------------------- 会话 */

function startLesson(lessonId) {
  const found = findLesson(lessonId);
  if (!found) return;
  session = {
    mode: 'lesson', lessonId: lessonId, title: found.lesson.t,
    items: found.lesson.words.map((w) => ({ w: w, again: false })),
    i: 0, ok: 0, bad: 0, phase: 'ask', picked: -1, fb: null, done: false,
  };
  session.q = makeQuestion(session.items[0].w);
  render();
}

function startReview() {
  const due = dueCards();
  if (!due.length) { toast('暂时没有要复习的'); return; }
  const items = due.slice(0, 20).map((c) => ({
    w: BY_UID[c.uid] || { u: c.uid, f: c.f, g: c.g, s: '' }, again: false,
  }));
  session = {
    mode: 'review', lessonId: null, title: '复习 ' + items.length + ' 个词',
    items: items, i: 0, ok: 0, bad: 0, phase: 'ask', picked: -1, fb: null, done: false,
  };
  session.q = makeQuestion(session.items[0].w);
  render();
}

function answerAt(i) {
  const s = session;
  if (!s || s.phase !== 'ask') return;
  const q = s.q;
  const correct = q.options[i] === q.answer;
  s.picked = i;
  settle(s, correct, null);
}

function answerSpell() {
  const s = session;
  if (!s || s.phase !== 'ask') return;
  const input = document.getElementById('spell-in');
  const typed = input ? input.value.trim() : '';
  if (!typed) { toast('先写一个答案'); return; }
  const q = s.q;
  const correct = formFold(typed) === formFold(q.answer);
  const exact = typed === q.answer;
  s.picked = -1;
  settle(s, correct, correct && !exact ? '拼对了，不过注意重音符号：' + q.answer : null);
}

function settle(s, correct, note) {
  const item = s.items[s.i];
  const w = item.w;
  if (correct) { s.ok++; addXP(s.mode === 'review' ? 3 : 2); }
  else { s.bad++; }
  gradeCard(w, correct);
  // 错题当堂回来：本轮的错词排到队尾再考一次
  if (!correct && !item.again) s.items.push({ w: w, again: true });
  s.fb = correct
    ? { ok: true, answer: s.q.answer, note: note || (displayForm(w.f) + ' · ' + shortGloss(w.g, 60)) }
    : { ok: false, answer: s.q.answer };
  s.phase = 'fb';
  save();
  render();
}

function nextQuestion() {
  const s = session;
  s.i++;
  if (s.i >= s.items.length) {
    s.done = true;
    touchStreak();
    if (s.mode === 'lesson' && s.lessonId && state.done.indexOf(s.lessonId) < 0) {
      state.done.push(s.lessonId);
    }
    save();
    render();
    return;
  }
  s.q = makeQuestion(s.items[s.i].w);
  s.phase = 'ask';
  s.picked = -1;
  s.fb = null;
  render();
}

/* ---------------------------------------------------------------- 视图 */

function findLesson(lid) {
  for (const u of DATA.units) {
    for (const l of u.lessons) if (l.id === lid) return { unit: u, lesson: l };
  }
  return null;
}

function findChapter(cid) {
  for (const c of DATA.chapters) if (c.id === cid) return c;
  return null;
}

function tabOf(name) {
  if (name === 'learn' || name === 'unit') return 'learn';
  if (name === 'read' || name === 'chapter') return 'read';
  if (name === 'dict') return 'dict';
  return 'learn';
}

function headerHtml() {
  const cur = stack[stack.length - 1];
  const inSess = !!session;
  let sub = '';
  let back = false;
  if (!inSess) {
    if (cur.name === 'unit') { sub = '单元'; back = true; }
    else if (cur.name === 'chapter') { sub = '原文'; back = true; }
  }
  const showChips = !inSess;
  return '<header class="hdr">' +
    (inSess || back ? '<button class="iconbtn" data-act="back">‹</button>' : '') +
    '<div><div class="hdr-t">' + (inSess ? esc(session.title) : '昆雅') + '</div>' +
    (sub ? '<div class="hdr-sub">' + esc(sub) + '</div>' : '') + '</div>' +
    '<div class="hdr-sp"></div>' +
    (showChips
      ? '<div class="chips"><span class="chip">🔥 ' + (state.streak.count || 0) + '</span>' +
        '<span class="chip">' + xpToday() + ' XP</span></div>'
      : '') +
    '</header>';
}

function tabsHtml() {
  const cur = stack[stack.length - 1];
  const on = tabOf(cur.name);
  const items = [['learn', '学', '❋'], ['read', '读', '❦'], ['dict', '查', '⌕']];
  return '<nav class="tabs">' + items.map(function (it) {
    return '<button class="tab' + (on === it[0] ? ' on' : '') + '" data-act="tab" data-tab="' + it[0] + '">' +
      '<span class="ti">' + it[2] + '</span>' + it[1] + '</button>';
  }).join('') + '</nav>';
}

function learnHome() {
  const due = dueCards().length;
  let totalLessons = 0;
  let doneLessons = 0;
  DATA.units.forEach(function (u) {
    totalLessons += u.lessons.length;
    u.lessons.forEach(function (l) { if (state.done.indexOf(l.id) >= 0) doneLessons++; });
  });
  const strong = Object.keys(state.cards).filter(function (k) { return (state.cards[k].iv || 0) >= 8; }).length;

  let h = '<div class="h1">今天学一点昆雅</div>' +
    '<p class="sub">' + DATA.units.length + ' 个单元 · ' + totalLessons + ' 节 · ' + WORDS.length + ' 个词</p>';

  if (due > 0) {
    h += '<div class="banner" data-act="review">' +
      '<div class="b-t">今天该复习 <span class="b-n">' + due + '</span> 个词</div>' +
      '<div class="b-s">答对拉长间隔，答错打回 1 天——按你上次的表现排的。</div></div>';
  }

  h += '<div class="stats">' +
    '<div class="stat"><div class="sv">' + doneLessons + '/' + totalLessons + '</div><div class="sl">已学节</div></div>' +
    '<div class="stat"><div class="sv">' + strong + '</div><div class="sl">巩固词</div></div>' +
    '<div class="stat"><div class="sv">' + (state.streak.count || 0) + '</div><div class="sl">连胜</div></div>' +
    '</div>';

  h += '<div class="sec-t">课程</div>';
  DATA.units.forEach(function (u, i) {
    const dn = u.lessons.filter(function (l) { return state.done.indexOf(l.id) >= 0; }).length;
    const pct = Math.round((dn / u.lessons.length) * 100);
    h += '<div class="card" data-act="unit" data-id="' + u.id + '">' +
      '<div class="badge' + (dn === u.lessons.length ? ' done' : '') + '">' + (dn === u.lessons.length ? '✓' : (i + 1)) + '</div>' +
      '<div class="grow"><div class="c-t">' + esc(u.t) + '</div>' +
      '<div class="c-s">' + esc(u.l) + ' · ' + dn + '/' + u.lessons.length + ' 节</div>' +
      '<div class="progress"><i style="width:' + pct + '%"></i></div></div>' +
      '<div class="arrow">›</div></div>';
  });
  return h;
}

function unitView(id) {
  const u = DATA.units.filter(function (x) { return x.id === id; })[0];
  if (!u) return '<div class="empty">找不到这个单元</div>';
  let h = '<div class="h1">' + esc(u.t) + '</div><p class="sub">' + esc(u.l) + ' · 每节 6 个词</p>';
  u.lessons.forEach(function (l) {
    const done = state.done.indexOf(l.id) >= 0;
    h += '<div class="card" data-act="lesson" data-id="' + l.id + '">' +
      '<div class="badge' + (done ? ' done' : '') + '">' + (done ? '✓' : l.words.length) + '</div>' +
      '<div class="grow"><div class="c-t">' + esc(l.t) + '</div>' +
      '<div class="c-s">' + l.words.map(function (w) { return displayForm(w.f); }).slice(0, 4).join(' · ') + ' …</div></div>' +
      '<div class="arrow">›</div></div>';
  });
  return h;
}

function readHome() {
  let h = '<div class="h1">读原文</div><p class="sub">' +
    DATA.chapters.reduce(function (n, c) {
      return n + c.lessons.reduce(function (m, l) { return m + l.sents.length; }, 0);
    }, 0) + ' 句全部出自托尔金笔下，按出处分章</p>';
  h += '<div class="sec-t">章节</div>';
  DATA.chapters.forEach(function (c) {
    const n = c.lessons.reduce(function (m, l) { return m + l.sents.length; }, 0);
    const done = state.done.indexOf('CH:' + c.id) >= 0;
    h += '<div class="card" data-act="chapter" data-id="' + esc(c.id) + '">' +
      '<div class="badge' + (done ? ' done' : '') + '">' + (done ? '✓' : n) + '</div>' +
      '<div class="grow"><div class="c-t">' + esc(c.t) + '</div>' +
      '<div class="c-s">' + esc(c.l) + '</div></div><div class="arrow">›</div></div>';
  });
  return h;
}

function chapterView(id) {
  const c = findChapter(id);
  if (!c) return '<div class="empty">找不到这一章</div>';
  const sents = [];
  c.lessons.forEach(function (l) { l.sents.forEach(function (s) { sents.push(s); }); });
  let h = '<div class="h1">' + esc(c.t) + '</div><p class="sub">' + esc(c.l) + '</p>';
  sents.forEach(function (s) { h += sentenceHtml(s); });
  h += '<button class="btn block" data-act="mark-chapter" data-id="' + esc(c.id) + '" style="margin-top:8px">这一章读完了</button>';
  return h;
}

function sentenceHtml(s) {
  const t = tw(s.f);
  return '<div class="sent">' +
    (t ? '<div class="tw tw-s">' + esc(t) + '</div>' : '') +
    '<div class="lat serif">' + esc(s.f) + '</div>' +
    '<div class="gl">' + esc(s.g) + '</div>' +
    '<div class="cite">' + esc(s.c) + '</div>' +
    '<button class="tokbtn" data-act="toks" data-uid="' + s.u + '">逐词拆解</button>' +
    '<div class="toks" id="toks-' + s.u + '"></div>' +
    '</div>';
}

function toksHtml(uid) {
  const bd = (DATA.bd && DATA.bd[String(uid)]) || [];
  if (!bd.length) return '<span class="tok unknown">这一句暂时没有拆解</span>';
  return bd.map(function (t) {
    const g = t[1];
    return '<span class="tok' + (g ? '' : ' unknown') + '">' +
      '<b class="serif">' + esc(t[0]) + '</b><br>' +
      '<span>' + esc(g || '—') + '</span></span>';
  }).join('');
}

function dictHome() {
  return '<div class="h1">查词</div>' +
    '<p class="sub">' + DATA.dict.length + ' 条 · 输入拉丁转写或英文释义，大小写与长音符号都可以省</p>' +
    '<input class="search" id="q" placeholder="试试 elen、cirya、star…" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">' +
    '<div id="dictres"></div>';
}

function dictResults(q) {
  const box = document.getElementById('dictres');
  if (!box) return;
  if (!q.trim()) {
    const hot = (DATA.hot && DATA.hot.length)
      ? DATA.hot
      : DATA.dict.filter(function (w) { return (w[3] || 9) <= 1; }).slice(0, 24);
    box.innerHTML = '<div class="sec-t" style="margin-top:4px">常用词</div>' + hot.map(dictRow).join('');
    return;
  }
  const key = formKey(q);
  const folded = formFold(q);
  const scored = [];
  for (let i = 0; i < DATA.dict.length; i++) {
    const w = DATA.dict[i];
    const f = formKey(w[0]);
    const g = w[1] || '';
    let score = -1;
    if (f === key) score = 0;
    else if (f.indexOf(key) === 0) score = 1;
    else if (f.indexOf(key) > 0) score = 2;
    else if (g.indexOf(q) >= 0) score = 3;
    else if (folded && formFold(w[0]).indexOf(folded) === 0) score = 4;
    if (score >= 0) scored.push([score, i]);
  }
  scored.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
  const rows = scored.slice(0, 60).map(function (p) { return DATA.dict[p[1]]; });
  box.innerHTML = rows.length
    ? rows.map(dictRow).join('')
    : '<div class="empty">没找到「' + esc(q) + '」<br>试试去掉长音符号，或者用中文查</div>';
}

function dictRow(w) {
  const tag = SPEECH_CN[w[2]] || '';
  return '<div class="row" data-act="word" data-form="' + esc(w[0]) + '">' +
    '<div class="r-f serif">' + esc(displayForm(w[0])) +
    (tag ? '<span class="tag">' + tag + '</span>' : '') + '</div>' +
    '<div class="r-g">' + esc(w[1]) + '</div>' +
    '<div class="r-detail" hidden></div></div>';
}

/* ---------------------------------------------------------------- 会话视图 */

function sessionView() {
  const s = session;
  if (s.done) {
    const pct = s.ok + s.bad ? Math.round((s.ok / (s.ok + s.bad)) * 100) : 100;
    return '<div class="done-card">' +
      '<div class="big">' + (s.bad === 0 ? '❋' : '❦') + '</div>' +
      '<div class="dt">' + (s.bad === 0 ? '全对，Namárië！' : '这一轮走完了') + '</div>' +
      '<div class="ds">' + s.ok + ' 对 · ' + s.bad + ' 错 · 正确率 ' + pct + '%<br>' +
      '连胜 ' + (state.streak.count || 0) + ' 天 · 今天 ' + xpToday() + ' XP</div>' +
      '<div style="margin-top:26px"><button class="btn block" data-act="finish">回去</button></div></div>';
  }

  const q = s.q;
  const pct = Math.round((s.i / s.items.length) * 100);
  let h = '<div class="sessbar"><i style="width:' + pct + '%"></i></div>';
  h += '<div class="qarea">';
  h += '<div class="qkind">' + esc(q.label) + '</div><div class="prompt">' + q.promptHtml + '</div>';

  if (q.kind === 'spell') {
    const disabled = s.phase !== 'ask';
    h += '<div class="spellbox">' +
      '<input id="spell-in" placeholder="' + esc(q.hint) + '" autocomplete="off" autocorrect="off" ' +
      'autocapitalize="off" spellcheck="false"' + (disabled ? ' disabled' : '') + '>' +
      '<button class="btn" data-act="spell-submit"' + (disabled ? ' disabled' : '') + '>提交</button></div>';
  } else {
    const letters = ['A', 'B', 'C', 'D'];
    h += q.options.map(function (o, i) {
      let cls = 'opt';
      if (s.phase === 'fb') {
        if (o === q.answer) cls += ' ok';
        else if (i === s.picked) cls += ' bad';
      }
      return '<button class="' + cls + '" data-act="opt" data-i="' + i + '"' +
        (s.phase !== 'ask' ? ' disabled' : '') + '>' +
        '<span class="ol">' + letters[i] + '</span>' + esc(o) + '</button>';
    }).join('');
  }
  h += '</div>';

  if (s.phase === 'fb') {
    const fb = s.fb;
    h += '<div class="feedback ' + (fb.ok ? 'ok' : 'bad') + '">' +
      '<div class="fb-head ' + (fb.ok ? 'ok' : 'bad') + '">' + (fb.ok ? '✓ 对了' : '✕ 再看一眼') + '</div>' +
      '<div class="fb-body">' + (fb.ok
        ? esc(fb.note || '')
        : '正确答案：<b class="serif">' + esc(fb.answer) + '</b>') + '</div>' +
      '<button class="btn" data-act="cont">继续</button></div>';
  }
  return h;
}

/* ---------------------------------------------------------------- 渲染 */

/* AGPL-3.0 §13：通过网络使用本应用的人要有拿到源码的机会，所以页脚列出来源 */
const SRC_LINE = '<a class="src" href="https://github.com/liangfeng113/elvish-quenya"' +
  ' target="_blank" rel="noopener">源码 · AGPL-3.0 ｜ 词库 Eldamo © Paul Strack (CC-BY)</a>';

function render() {
  const el = app();
  const inSess = !!session;
  let body;
  if (inSess) {
    body = sessionView();
  } else {
    const cur = stack[stack.length - 1];
    if (cur.name === 'unit') body = unitView(cur.id);
    else if (cur.name === 'chapter') body = chapterView(cur.id);
    else if (cur.name === 'dict') body = dictHome();
    else if (cur.name === 'read') body = readHome();
    else body = learnHome();
  }
  const mainCls = 'main' + (inSess ? ' session no-tabs' : '');
  el.innerHTML = headerHtml() + '<main class="' + mainCls + '">' + body +
    (inSess ? '' : SRC_LINE) + '</main>' +
    (inSess ? '' : tabsHtml());

  if (!inSess && stack[stack.length - 1].name === 'dict') {
    const q = document.getElementById('q');
    if (q) {
      q.addEventListener('input', function () { dictResults(q.value); });
      dictResults('');
    }
  }
  if (inSess && session && session.phase === 'ask' && session.q && session.q.kind === 'spell') {
    const inp = document.getElementById('spell-in');
    if (inp) {
      inp.focus();
      inp.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); answerSpell(); }
      });
    }
  }
}

/* ---------------------------------------------------------------- 交互 */

function push(r) { stack.push(r); render(); }

function back() {
  if (session) { session = null; render(); return; }
  if (stack.length > 1) { stack.pop(); render(); }
}

document.addEventListener('click', function (e) {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  const act = el.dataset.act;

  if (act === 'tab') {
    session = null;
    stack = [{ name: el.dataset.tab }];
    render();
  } else if (act === 'back') {
    back();
  } else if (act === 'unit') {
    push({ name: 'unit', id: el.dataset.id });
  } else if (act === 'lesson') {
    startLesson(el.dataset.id);
  } else if (act === 'review') {
    startReview();
  } else if (act === 'chapter') {
    push({ name: 'chapter', id: el.dataset.id });
  } else if (act === 'toks') {
    const box = document.getElementById('toks-' + el.dataset.uid);
    if (box) {
      if (box.innerHTML) { box.innerHTML = ''; }
      else { box.innerHTML = toksHtml(el.dataset.uid); }
    }
  } else if (act === 'mark-chapter') {
    const id = 'CH:' + el.dataset.id;
    if (state.done.indexOf(id) < 0) {
      state.done.push(id);
      addXP(10);
      touchStreak();
      save();
      toast('记下了 · +10 XP');
    } else {
      toast('这一章已经算读过了');
    }
    render();
  } else if (act === 'opt') {
    answerAt(parseInt(el.dataset.i, 10));
  } else if (act === 'spell-submit') {
    answerSpell();
  } else if (act === 'cont') {
    nextQuestion();
  } else if (act === 'finish') {
    session = null;
    render();
  } else if (act === 'word') {
    const row = el.closest('.row');
    const box = row.querySelector('.r-detail');
    if (box.hasAttribute('hidden')) {
      const form = el.dataset.form;
      const t = tw(form);
      const gloss = row.querySelector('.r-g').textContent;
      box.innerHTML = (t ? '<div class="tw">' + esc(t) + '</div>' : '') +
        '<div style="white-space:normal">' + esc(gloss) + '</div>';
      box.removeAttribute('hidden');
    } else {
      box.setAttribute('hidden', '');
      box.innerHTML = '';
    }
  }
});

/* ---------------------------------------------------------------- 启动 */

async function boot() {
  try {
    const res = await fetch('data.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    DATA = await res.json();
  } catch (e) {
    app().innerHTML = '<div class="empty">数据没能加载：' + esc(e.message) +
      '<br><br>确认是从 mobile/ 起的服务，且 data.json 在旁边。</div>';
    return;
  }
  for (let i = 0; i < DATA.units.length; i++) {
    const u = DATA.units[i];
    for (let j = 0; j < u.lessons.length; j++) {
      const l = u.lessons[j];
      for (let k = 0; k < l.words.length; k++) {
        WORDS.push(l.words[k]);
        BY_UID[l.words[k].u] = l.words[k];
      }
    }
  }
  TW = initTW();
  state = loadState();
  render();
}

boot();
