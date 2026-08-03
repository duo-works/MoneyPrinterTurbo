@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist "storage\youtube_automation\logs" mkdir "storage\youtube_automation\logs"
if not exist "venv\Scripts\python.exe" (
  echo [%date% %time%] ERROR: venv\Scripts\python.exe bulunamadi.>> "storage\youtube_automation\logs\scheduler.log"
  exit /b 1
)
echo [%date% %time%] YouTube 20:00 otomasyon dongusu 19:50'de basladi.>> "storage\youtube_automation\logs\scheduler.log"
"venv\Scripts\python.exe" "youtube_retry_runner.py" --not-before 20:00 >> "storage\youtube_automation\logs\scheduler.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] YouTube 20:00 otomasyon dongusu tamamlandi. Kod: %EXIT_CODE%>> "storage\youtube_automation\logs\scheduler.log"
exit /b %EXIT_CODE%