@echo off
REM Chay mot phat tren Windows: tao moi truong ao, cai, kiem tra, chay shadow.
cd /d "%~dp0"

where python >nul 2>&1 || (echo Khong tim thay python. Cai Python 3.9+ truoc. & exit /b 1)

if not exist .venv (
  echo ==^> tao moi truong ao .venv
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo ==^> cai goi ^(khong co thu vien ngoai^)
pip install -q -e .

echo ==^> chay bo kiem tra bat bien
python -m frog selftest

echo ==^> chay shadow
python -m frog run --out out

echo.
echo Xong. Xem out\metrics.json va out\trace.jsonl
pause
