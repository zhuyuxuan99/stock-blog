@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ================================================
echo    Stock Strategy Comparison - Update Data
echo ================================================
echo.

echo [1/2] Fetching latest stock data...
python fetch_stock_prices.py
set RESULT=%errorlevel%

echo.
echo Python exit code: %RESULT%
echo.

if %RESULT% equ 0 (
    echo [2/2] Data updated successfully^^!
    echo.

    set PORT=8888

    echo [3/3] Pushing to GitHub...
    git fetch origin master 2>&1
    git stash push -- recommendations.json stock_returns.json 2>nul
    git rebase origin/master 2>&1
    if !errorlevel! neq 0 (
        echo   同步远程变更时发生冲突，尝试以本地数据为准...
        git checkout --ours recommendations.json stock_returns.json 2>nul
        git add recommendations.json stock_returns.json 2>nul
        git rebase --continue 2>&1
    )
    git stash pop 2>nul
    git add recommendations.json stock_returns.json strategy_comparison.html fetch_stock_prices.py up_run.bat
    git commit -m "Auto update: stock data %date% %time%" >nul 2>&1
    git push --set-upstream origin HEAD 2>&1
    if !errorlevel! neq 0 (
        echo   ^(git push skipped - remote not configured or no network^)
    ) else (
        echo   Push completed.
    )
    echo.

    echo Checking port !PORT!...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :!PORT! ^| findstr LISTENING') do (
        echo Killing process %%a occupying port !PORT!...
        taskkill /F /PID %%a >nul 2>&1
    )

    echo Open in browser: http://localhost:!PORT!/strategy_comparison.html
    echo Press Ctrl+C to stop server
    echo.
    start "" http://localhost:!PORT!/strategy_comparison.html
    python -m http.server !PORT!
) else (
    echo Failed to fetch data. Check network or Tushare Token.
)

echo.
pause