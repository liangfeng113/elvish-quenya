// 取 cloudflared 的最新 Windows 版（走 api.github.com 拿签名直链，多连接并发下载）
const https = require('https');
const fs = require('fs');
const path = require('path');

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

const OUT_DIR = path.join(__dirname, 'bin');
const OUT = path.join(OUT_DIR, 'cloudflared.exe');
const UA = 'quenya-fetch/1.0';

function getJson(url) {
  return new Promise((res, rej) => {
    const req = https.get(url, { headers: { 'User-Agent': UA, Accept: 'application/vnd.github+json' } }, (r) => {
      if (r.statusCode >= 300 && r.headers.location) { r.resume(); return getJson(r.headers.location).then(res, rej); }
      let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => { try { res(JSON.parse(d)); } catch (e) { rej(e); } });
    });
    req.on('error', rej);
    req.setTimeout(30000, () => req.destroy(new Error('timeout')));
  });
}

function head(url) {
  return new Promise((res, rej) => {
    const req = https.request(url, { method: 'GET', headers: { 'User-Agent': UA, Range: 'bytes=0-0' } }, (r) => {
      res({ size: parseInt(r.headers['content-range'] ? r.headers['content-range'].split('/')[1] : r.headers['content-length'], 10), status: r.statusCode });
      r.resume();
    });
    req.on('error', rej); req.end();
  });
}

function getRange(url, start, end, tries = 3, hop = 0) {
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      const req = https.get(url, { headers: { 'User-Agent': UA, Range: `bytes=${start}-${end}` } }, (r) => {
        if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) {
          r.resume();
          if (hop > 4) return reject(new Error('重定向太多'));
          return getRange(r.headers.location, start, end, n, hop + 1).then(resolve, reject);
        }
        if (r.statusCode !== 206 && r.statusCode !== 200) { r.resume(); return n > 0 ? attempt(n - 1) : reject(new Error('HTTP ' + r.statusCode)); }
        const bufs = []; r.on('data', (c) => bufs.push(c));
        r.on('end', () => resolve(Buffer.concat(bufs)));
      });
      req.on('error', () => (n > 0 ? setTimeout(() => attempt(n - 1), 400) : reject(new Error('range fail'))));
      req.setTimeout(60000, () => req.destroy(new Error('timeout')));
    };
    attempt(tries);
  });
}

(async () => {
  const rel = await getJson('https://api.github.com/repos/cloudflare/cloudflared/releases/latest');
  const asset = (rel.assets || []).find((a) => a.name === 'cloudflared-windows-amd64.exe');
  if (!asset) throw new Error('没找到 windows-amd64 资产');
  console.log('版本', rel.tag_name, '｜大小', (asset.size / 1048576).toFixed(1), 'MB');

  fs.mkdirSync(OUT_DIR, { recursive: true });
  const N = 10;
  const CHUNK = Math.ceil(asset.size / N);
  const t0 = Date.now();
  const parts = await Promise.all(
    Array.from({ length: N }, (_, i) => {
      const s = i * CHUNK;
      const e = Math.min(s + CHUNK - 1, asset.size - 1);
      return getRange(asset.browser_download_url, s, e);
    })
  );
  const buf = Buffer.concat(parts);
  if (buf.length !== asset.size) throw new Error(`长度不符 ${buf.length} != ${asset.size}`);
  fs.writeFileSync(OUT, buf);
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  console.log('已保存', OUT, (buf.length / 1048576).toFixed(1), 'MB', `（${secs}s）`);
})().catch((e) => { console.error('失败:', e.message); process.exit(1); });
