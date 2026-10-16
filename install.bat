@echo off
REM Cai lenh `frog` vao PATH. Mo terminal moi, go frog la vao phien.
cd /d "%~dp0"
where python >nul 2>&1 || (
  echo Khong tim thay python. Cai Python 3.9+ va bat Add to PATH.
  exit /b 1
)
python -m frog install
