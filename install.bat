@echo off
REM Cai lenh `mira` vao PATH. Mo terminal moi, go mira la vao phien.
cd /d "%~dp0"
where python >nul 2>&1 || (
  echo Khong tim thay python. Cai Python 3.9+ va bat Add to PATH.
  exit /b 1
)
python -m r0 install
