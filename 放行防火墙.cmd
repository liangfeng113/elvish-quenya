@echo off
chcp 65001 >nul
rem Allow inbound TCP 8123 for the private network profile (ASCII comments only)
title Quenya mobile - firewall rule

net session >nul 2>&1
if errorlevel 1 (
  echo 需要管理员权限，正在弹出 UAC 确认框……
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall delete rule name="Quenya mobile 8123" >nul 2>&1
netsh advfirewall firewall add rule name="Quenya mobile 8123" dir=in action=allow protocol=TCP localport=8123 profile=private
if errorlevel 1 (
  echo.
  echo 添加失败。可以手工在「Windows 安全中心 - 防火墙和网络保护 - 允许应用通过防火墙」里放行 python.exe。
) else (
  echo.
  echo 已放行：TCP 8123，仅专用网络（家里/公司 Wi-Fi）。公用网络不开放。
)
echo.
pause
