@echo off
rem 작업 스케줄러용: agent\run.bat rebalance  /  agent\run.bat surge
cd /d %~dp0..
if not exist agent\logs mkdir agent\logs
set PYTHONIOENCODING=utf-8
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set D=%%i
"C:\Users\lim\AppData\Local\Programs\Python\Python312\python.exe" -m agent.%1 --execute >> agent\logs\%D%_%1.log 2>&1
