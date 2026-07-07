@echo off
chcp 65001 > nul
echo ========================================
echo   HTTPS 本地服务器启动脚本
echo ========================================
echo.

:: 检查Python是否安装
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python
    pause
    exit /b 1
)

:: 关闭占用端口的进程
echo [1/2] 检查端口占用...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8200 ^| findstr LISTENING') do (
    echo 关闭占用8200端口的进程 %%a ...
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8443 ^| findstr LISTENING') do (
    echo 关闭占用8443端口的进程 %%a ...
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/2] 启动HTTP/HTTPS服务器...
echo.
echo HTTP:  http://localhost:8200/
echo HTTPS: https://localhost:8443/
echo.
echo 按 Ctrl+C 停止服务器
echo.

python "%~dp0https_server.py"

echo.
pause
