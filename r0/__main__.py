"""Shim một bậc. Lệnh cũ `r0` gọi thẳng frog, không đi qua mira. Xóa sau 2027-04-16."""
from frog.cli import deprecated_main

if __name__ == "__main__":
    raise SystemExit(deprecated_main())
