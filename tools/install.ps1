<#
  昆雅 · 学 —— 安装/移除桌面快捷方式与开机自启

  这个脚本由 安装.cmd / 移除.cmd 调用，也可以手动跑：
     powershell -NoProfile -ExecutionPolicy Bypass -File tools\install.ps1
     powershell -NoProfile -ExecutionPolicy Bypass -File tools\install.ps1 -Remove

  做什么：
     1. 桌面快捷方式        %USERPROFILE%\Desktop\昆雅.lnk
     2. 开始菜单快捷方式    %APPDATA%\Microsoft\Windows\Start Menu\Programs\昆雅.lnk
     3. 开机自启            %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\昆雅.lnk
        （用启动文件夹而不是注册表，因为它看得见、想删就删）

  只写这三个 .lnk，不改系统设置、不碰注册表、不需要管理员。
#>
param(
    [switch]$Remove,
    [switch]$NoAutostart,
    [switch]$DryRun,
    [string]$TestTarget = ""      # 仅用于自检：把链接都建到这个目录里
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$App = Join-Path $Root "app\learn_app.py"
$Icon = Join-Path $Root "assets\quenya.ico"
$PyDir = "C:\Users\1\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python"
$Pyw = Join-Path $PyDir "pythonw.exe"
$Name = "昆雅"

function Info($m) { Write-Host $m }
function Ok($m)   { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Bad($m)  { Write-Host "  [跳过] $m" -ForegroundColor Yellow }

# ---------- 前置检查 ----------
Info ""
Info "昆雅 · 学 —— 快捷方式安装"
Info ("项目目录 " + $Root)

if (-not (Test-Path $App))  { throw "找不到应用主程序: $App" }
if (-not (Test-Path $Pyw))  { throw "找不到 pythonw.exe: $Pyw" }
if (-not (Test-Path $Icon)) {
    Info "图标不存在，先试着生成一次…"
    $Py = Join-Path $PyDir "python.exe"
    if (Test-Path $Py) {
        & $Py (Join-Path $Root "tools\make_icon.py") | Out-Null
    }
}

# ---------- 目标位置 ----------
$targets = @()
if ($TestTarget -ne "") {
    if (-not (Test-Path $TestTarget)) { New-Item -ItemType Directory -Path $TestTarget | Out-Null }
    $targets = @(
        @{ Kind = "测试"; Path = (Join-Path $TestTarget "$Name.lnk") },
        @{ Kind = "测试自启"; Path = (Join-Path $TestTarget "_startup_$Name.lnk") }
    )
} else {
    $targets += @{ Kind = "桌面";   Path = (Join-Path ([Environment]::GetFolderPath('Desktop')) "$Name.lnk") }
    $targets += @{ Kind = "开始菜单"; Path = (Join-Path ([Environment]::GetFolderPath('Programs')) "$Name.lnk") }
    if (-not $NoAutostart) {
        $targets += @{ Kind = "开机自启"; Path = (Join-Path ([Environment]::GetFolderPath('Startup')) "$Name.lnk") }
    }
}

$ws = New-Object -ComObject WScript.Shell

if ($Remove) {
    Info ""
    Info "移除快捷方式："
    foreach ($t in $targets) {
        if (Test-Path $t.Path) {
            if ($DryRun) { Ok ("[dry-run] 会删除 " + $t.Path) }
            else { Remove-Item $t.Path -Force; Ok ("已删除 " + $t.Kind) }
        } else {
            Bad ($t.Kind + "：本来就没有")
        }
    }
    Info ""
    Info "完成。"
    exit 0
}

# ---------- 创建 ----------
Info ""
Info "创建快捷方式："
foreach ($t in $targets) {
    if ($DryRun) {
        Ok ("[dry-run] 会创建 " + $t.Path)
        continue
    }
    try {
        $sc = $ws.CreateShortcut($t.Path)
        $sc.TargetPath = $Pyw
        $sc.Arguments = '"' + $App + '"'
        $sc.WorkingDirectory = $Root
        if (Test-Path $Icon) { $sc.IconLocation = $Icon + ",0" }
        $sc.Description = "昆雅 · 学 —— 读托尔金原文的昆雅精灵语"
        $sc.WindowStyle = 1
        $sc.Save()

        # 回读校验：确认真的写对了，而不是"调用成功"
        $chk = $ws.CreateShortcut($t.Path)
        $good = ($chk.TargetPath -eq $Pyw) -and ($chk.Arguments -match "learn_app\.py")
        if ($good) { Ok ($t.Kind + " → " + $t.Path) }
        else { Write-Host ("  [异常] " + $t.Kind + " 写出来了但内容不对: " + $chk.TargetPath) -ForegroundColor Red }
    } catch {
        Write-Host ("  [失败] " + $t.Kind + "：" + $_.Exception.Message) -ForegroundColor Red
    }
}

Info ""
if (-not $TestTarget) {
    Info "说明："
    Info "  · 开机自启用的是「启动」文件夹里的快捷方式，想关掉就直接删掉它，"
    Info "    或者双击项目里的「移除快捷方式.cmd」。"
    Info "  · 没有改注册表、没有要管理员权限。"
}
Info ""
Info "完成。"
