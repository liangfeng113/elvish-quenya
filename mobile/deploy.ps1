# 把 mobile/web 发布到 Netlify 正式站点（your-site）
# 用法: powershell -File mobile\deploy.ps1
$ErrorActionPreference = 'Stop'

$mobile = $PSScriptRoot
$base = Split-Path -Parent $mobile
$cli = Join-Path $base '.tools\node_modules\.bin\netlify.cmd'
if (-not (Test-Path $cli)) {
    throw "没找到 Netlify CLI。先跑: npm install netlify-cli --no-save --prefix .tools --ignore-scripts"
}

$siteId = '8432534e-545b-4655-80f2-83c202a9c37a'   # 项目 your-site
$web = Join-Path $mobile 'web'

Write-Host "发布 $web -> https://your-site.netlify.app" -ForegroundColor Cyan
& $cli deploy --prod --no-build --dir $web --site $siteId

Write-Host ""
Write-Host "完成后记得刷新手机上的页面（服务端不缓存，但 Safari 会留旧的）。" -ForegroundColor DarkGray
