FROM python:3.12-slim

WORKDIR /app

# Không có thư viện ngoài — chỉ copy mã nguồn
COPY pyproject.toml README.md ./
COPY frog ./frog
COPY tests ./tests

RUN pip install --no-cache-dir -e .

# Chạy bộ kiểm tra lúc build: nếu bất biến vỡ thì image không được tạo
RUN frog selftest

CMD ["frog", "run", "--out", "out"]
