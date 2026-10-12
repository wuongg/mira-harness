.PHONY: help venv install test run labels clean

help:
	@echo "make install   cai vao moi truong ao .venv"
	@echo "make test      chay bo kiem tra bat bien"
	@echo "make run       chay shadow (320 tac vu, cache hit 90%)"
	@echo "make labels    xuat phieu gan nhan"
	@echo "make clean     xoa ket qua va moi truong ao"

venv:
	python3 -m venv .venv

install: venv
	. .venv/bin/activate && pip install -e .

test:
	. .venv/bin/activate && mira selftest

run:
	. .venv/bin/activate && mira run --out out

labels:
	. .venv/bin/activate && mira labels export --out out/labels.csv

clean:
	rm -rf out out-* .venv build *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} +
