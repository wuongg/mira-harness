#!/usr/bin/env bash
# Chạy một phát: tự tạo môi trường ảo, cài, kiểm tra, chạy shadow.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "Không tìm thấy $PY. Cài Python 3.9+ trước."; exit 1; }

if [ ! -d .venv ]; then
  echo "==> tạo môi trường ảo .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
echo "==> cài gói (không có thư viện ngoài)"
pip install -q -e .

echo "==> chạy bộ kiểm tra bất biến"
python -m frog selftest

echo "==> chạy shadow"
python -m frog run --out out

echo
echo "Xong. Xem out/metrics.json và out/trace.jsonl"
