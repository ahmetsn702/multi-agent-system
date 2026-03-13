@echo off
echo.
echo  ╔══════════════════════════════════════╗
echo  ║   Multi-Agent AI - Web Sunucusu      ║
echo  ╟──────────────────────────────────────╢

:: PC'nin yerel IP adresini bul
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set IP=%%a
    goto :found
)
:found
set IP=%IP: =%

echo  ║  PC Adresi : http://%IP%:8000    ║
echo  ║  Android   : http://%IP%:8000    ║
echo  ╚══════════════════════════════════════╝
echo.
echo  Tarayicinizda / telefonunuzda yukardaki adresi acin.
echo  Durdurmak icin: Ctrl+C
echo.

cd /d "%~dp0"  REM updated: removed AWS refs
uvicorn api.main_api:app --host 0.0.0.0 --port 8000 --reload
pause
