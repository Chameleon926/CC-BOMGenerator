"""FastAPI 依赖聚合点（留扩展位，后续加鉴权/限流等依赖在此挂）。"""

from ..db import get_db

__all__ = ["get_db"]
