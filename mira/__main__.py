"""Shim một bậc. Lệnh cũ `mira` gọi thẳng frog. Xóa sau 2027-04-16."""
from frog.cli import deprecated_mira

if __name__ == "__main__":
    raise SystemExit(deprecated_mira())
