"""`python -m r0` in cảnh báo rồi gọi mira."""
import sys

print("r0 và r0-shadow sẽ bị gỡ sau phiên bản kế tiếp. Hãy gọi mira.", file=sys.stderr)

from mira.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
