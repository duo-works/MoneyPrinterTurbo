@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist "storage\youtube_automation\logs" mkdir "storage\youtube_automation\logs"
if not exist "venv\Scripts\python.exe" (
  echo [%date% %time%] ERROR: venv\Scripts\python.exe bulunamadi.>> "storage\youtube_automation\logs\scheduler.log"
  exit /b 1
)
echo [%date% %time%] YouTube otomasyon dongusu basladi.>> "storage\youtube_automation\logs\scheduler.log"
"venv\Scripts\python.exe" "youtube_retry_runner.py" >> "storage\youtube_automation\logs\scheduler.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] YouTube otomasyon dongusu tamamlandi. Kod: %EXIT_CODE%>> "storage\youtube_automation\logs\scheduler.log"
exit /b %EXIT_CODE%
