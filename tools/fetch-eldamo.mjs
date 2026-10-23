// 并发分块下载 Eldamo 数据模型（这台机器单连接只有 ~120KB/s，必须分块）
// 用法: node fetch-eldamo.mjs <输出路径>
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';

const URL_ = 'https://eldamo.org/content/data-model/eldamo-data.xml';
const OUT = process.argv[2] || 'data/eldamo-data.xml';
const CHUNK = 8 * 1024 * 1024;
const CONCURRENCY = 12;
const RETRIES = 5;

const agent = new https.Agent({ keepAlive: true, maxSockets: CONCURRENCY });

function head(url) {
  return new Promise((res, rej) => {
    const req = https.request(url, { method: 'HEAD', agent, headers: { 'user-agent': 'dsh-elvish/0.1' } }, (r) => {
      r.resume();
      res({ status: r.statusCode, len: Number(r.headers['content-length']), ranges: r.headers['accept-ranges'] });
    });
    req.on('error', rej);
    req.end();
  });
}

function fetchRange(url, start, end) {
  return new Promise((res, rej) => {
    const req = https.request(url, {
      agent,
      headers: { 'user-agent': 'dsh-elvish/0.1', range: `bytes=${start}-${end}` },
    }, (r) => {
      if (r.statusCode !== 206 && r.statusCode !== 200) {
        r.resume();
        return rej(new Error(`HTTP ${r.statusCode} for ${start}-${end}`));
      }
      const bufs = [];
      r.on('data', (c) => bufs.push(c));
      r.on('end', () => {
        const buf = Buffer.concat(bufs);
        const want = end - start + 1;
        if (buf.length !== want) return rej(new Error(`short read ${buf.length}/${want}`));
        res(buf);
      });
      r.on('error', rej);
    });
    req.on('error', rej);
    req.setTimeout(120000, () => req.destroy(new Error('timeout')));
    req.end();
  });
}

async function fetchChunk(url, start, end) {
  let lastErr;
  for (let i = 0; i < RETRIES; i++) {
    try {
      return await fetchRange(url, start, end);
    } catch (e) {
      lastErr = e;
      await new Promise((r) => setTimeout(r, 500 * (i + 1)));
    }
  }
  throw new Error(`chunk ${start}-${end} failed after ${RETRIES}: ${lastErr.message}`);
}

async function main() {
  const info = await head(URL_);
  if (!info.len) throw new Error('no content-length');
  console.log(`size=${(info.len / 1048576).toFixed(2)} MB  accept-ranges=${info.ranges}`);

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const fd = fs.openSync(OUT, 'w');
  fs.ftruncateSync(fd, info.len);

  const jobs = [];
  for (let s = 0; s < info.len; s += CHUNK) {
    const e = Math.min(s + CHUNK - 1, info.len - 1);
    jobs.push({ s, e });
  }
  console.log(`chunks=${jobs.length} concurrency=${CONCURRENCY}`);

  let done = 0;
  const t0 = Date.now();
  let next = 0;
  async function worker() {
    while (true) {
      const i = next++;
      if (i >= jobs.length) return;
      const { s, e } = jobs[i];
      const buf = await fetchChunk(URL_, s, e);
      fs.writeSync(fd, buf, 0, buf.length, s);
      done++;
      const mb = ((done * CHUNK) / 1048576).toFixed(1);
      process.stdout.write(`\r  ${done}/${jobs.length} chunks (~${mb} MB) ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  fs.closeSync(fd);
  process.stdout.write('\n');

  const size = fs.statSync(OUT).size;
  if (size !== info.len) throw new Error(`final size mismatch ${size} != ${info.len}`);
  const headBuf = Buffer.alloc(200);
  const rfd = fs.openSync(OUT, 'r');
  fs.readSync(rfd, headBuf, 0, 200, 0);
  fs.closeSync(rfd);
  const tail = headBuf.toString('utf8').trimStart().slice(0, 120);
  console.log(`OK ${OUT} ${(size / 1048576).toFixed(2)} MB`);
  console.log(`head: ${tail}`);
}

main().catch((e) => {
  console.error('FAILED: ' + e.message);
  process.exit(1);
});
