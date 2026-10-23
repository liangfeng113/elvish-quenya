# 昆雅 · 手机版（局域网 PWA）

桌面版是 Tkinter 的，搬不上 iPhone。这里把**内容与排课逻辑原样复用**，
只重写了「壳」——同一份 `elvish.db`、同一个 `app/course.py`，所以手机上看到的
180 词 / 244 句和桌面上完全一致。

| | 桌面版 | 手机版 |
|---|---|---|
| 入口 | `昆雅.vbs` → `app/learn_app.py`（Tkinter） | `昆雅手机.cmd` → `mobile/serve.py`（HTTP） |
| 界面 | 四个页签 + 全屏上课层 | 三个页签（学 / 读 / 查） |
| 数据 | `data/elvish.db` 直读 | `mobile/web/data.json`（导出产物） |
| 进度 | `data/progress.json` | 浏览器 localStorage `quenya.mobile.v1` |
| 发音 | espeak-ng 的 `qya` 声 | 暂无 |

## 怎么用

1. 双击 **`昆雅手机.cmd`**（或 `python mobile\serve.py 8123`）。
2. 窗口里会打印一行地址，形如 `http://192.168.1.14:8123/`。
3. iPhone 的 **Safari** 打开这个地址——手机要和电脑在同一个 Wi-Fi。
4. 分享按钮 → **添加到主屏幕**，之后从桌面图标进，全屏无地址栏。

**第一次连不上多半是 Windows 防火墙**。放行一条（管理员 PowerShell 执行一次即可，
只对专用网络开放）：

```powershell
netsh advfirewall firewall add rule name="Quenya mobile 8123" dir=in action=allow protocol=TCP localport=8123 profile=private
```

## 目录

```
mobile/
├── 昆雅手机.cmd        双击启动（会自动找 Python）
├── serve.py            局域网静态服务器，只读，不往公网暴露
├── export.py           从 data/elvish.db 导出 data.json（改了课程就重跑）
├── prepare_assets.py   一次性搬运 Tengwar 转写库 / 字体 / 图标
├── shots/              界面截图
└── web/
    ├── index.html
    ├── app.css         羊皮纸配色，跟随系统深色模式
    ├── app.js          三个页签、题目生成、SM-2 排期（照搬 course.py）
    ├── data.json       内容导出产物（约 600 KB）
    ├── manifest.webmanifest / icon-180.png
    ├── vendor/         Glǽmscribe 转写库 + quenya-tengwar-classical 模式
    └── fonts/          FreeMonoTengwar.ttf（浏览器自己排版，tehta 才叠得对）
```

## 正式站点（Netlify）

部署到自己的 Netlify 站点即可（站点名自定），永久、免密码、HTTPS。

发布（改完内容后重新推一次）：

```powershell
powershell -File mobile\deploy.ps1
```

首次部署装 CLI 时踩过的三个坑，记下来免得重犯：

1. `npm install netlify-cli` 默认会跑 postinstall 脚本，DSH 沙箱下报 `EPERM spawn`；
   加 `--ignore-scripts` 就装得上（35 秒，938 个包）。
2. CLI 要在 `~/.netlify` 建状态目录，沙箱工作区模式拦下了 mkdir；
   要么放宽权限跑一次，要么把状态目录指到工作区里。
3. **API 直接部署走不通**：`POST /sites/{id}/deploys` 带 `files` 清单时，返回的
   `required` 永远是空数组、文件数为 0，最后得到一个空站点。用 CLI 才行。
4. 新建站点默认 `sso_login: true`（访问要登录 Netlify），会返回 401 Login Redirect；
   用 `PATCH /api/v1/sites/{id}` 传 `{"sso_login": false}` 关掉。

## 发布一份临时预览（不在家时用）

`web/` 是纯静态的，可以整包丢给任何静态托管。**打包必须用正斜杠路径**：

```powershell
python -c "import os,zipfile;web=r'...\mobile\web';out=r'...\mobile\dist\quenya-mobile.zip';z=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED);[z.write(os.path.join(r,f),os.path.relpath(os.path.join(r,f),web).replace(os.sep,'/')) for r,_,fs in os.walk(web) for f in fs];z.close()"
```

别用 `Compress-Archive`：PowerShell 5.1 会写成 `vendor\glaemscribe.min.js` 这种反斜杠条目，
Netlify / 大多数主机解压后形不成目录，Tengwar 转写库直接 404。

然后把 zip 拖到 <https://app.netlify.com/drop>（免登录即可拿到地址）。注意匿名部署的限制：
**一小时后过期，且认领前带默认密码**（页面上会显示）。想长期用就点 “Claim this site” 登录一次，
或者把仓库推到 GitHub Pages / Cloudflare Pages。

## 内容更新

桌面版改了课程或换了词库之后：

```powershell
python mobile\export.py     # 重新生成 web/data.json
```

`web/` 里其余文件不用动。手机刷新页面即可（服务端发了 `no-store`）。

## 已知限制

- **没有发音**。iOS 的 SpeechSynthesis 里没有昆雅（espeak 的 `qya` 在 Windows 上跑），
  要发声得预生成音频文件，或者等加一个本地合成接口。
- **不能离线**。Service Worker 只在 HTTPS/localhost 下注册，局域网 http 装不了；
  想离线得给服务器配一张自签证书（Safari 首次要手动信任）。
- **手机版和桌面版进度互不相通**：一个存 localStorage、一个存 `progress.json`。
- 只收昆雅系词条（q/nq/mq/eq）。辛达林、帖勒瑞等不在词库里，
  所以查 `mellon` 是查不到的——它在 Eldamo 里记在辛达林名下。

## 授权

- 词库与原文出处：Eldamo（CC BY 4.0，见项目根目录 `assets/NOTICE.txt`）。
- Tengwar 转写：Glǽmscribe 1.3.1，AGPL-3.0，© Benjamin Babut，放在 `web/vendor/`。
- 精灵文字体：FreeMonoTengwar，GPL，见 `assets/tengwar-font/…/GPL.txt`。
