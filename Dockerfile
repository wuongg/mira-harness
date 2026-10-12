FROM python:3.12-slim

WORKDIR /app

# Không có thư viện ngoài — chỉ copy mã nguồn
COPY pyproject.toml README.md ./
COPY r0 ./r0
COPY tests ./tests
COPY labels.csv ./

RUN pip install --no-cache-dir -e .

# Chạy bộ kiểm tra lúc build: nếu bất biến vỡ thì image không được tạo
RUN mira selftest

CMD ["mira", "run", "--out", "out"]
