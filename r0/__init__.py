"""Vỏ tương thích. Hãy import mira. Vỏ này bị gỡ sau phiên bản kế tiếp."""
import warnings

warnings.warn(
    "Gói r0 chỉ là vỏ. Hãy import mira. Vỏ này bị gỡ sau phiên bản kế tiếp.",
    DeprecationWarning,
    stacklevel=2,
)

from mira import __version__  # noqa: E402

__all__ = ["__version__"]
