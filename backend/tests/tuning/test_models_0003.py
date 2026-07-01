"""alembic 0003 ORM 结构冒烟测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.db.models import Badcase, PendingDelta


def test_badcase_has_trace_json():
    assert hasattr(Badcase, "trace_json"), "Badcase 应有 trace_json 列"


def test_pending_delta_fields():
    cols = {c.name for c in PendingDelta.__table__.columns}
    assert {"id", "block_code", "from_bom_version_id", "delta_json", "status", "reviewed_by", "reviewed_at", "created_at"} <= cols
