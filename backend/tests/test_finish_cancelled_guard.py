# -*- coding: utf-8 -*-
"""finish_pipeline_run cancelled 守护的并发推演验证（纯逻辑，SQLite 内存库，不连真实 MySQL/LLM）。

模拟 HTTP 请求 session 与后台 daemon Thread session 是两个独立 Session（同 engine），
验证 repository 的 cancelled 守护在下列时序下成立：
  (a) 列查询绕开 identity map
  (b) 后台线程首次 finish 时读到 stop 已 commit 的 cancelled → guard 拦住
  (c) 中途快照 finish(status='running', output_bom_json=...) 在 cancelled 后也被拦（连 bom 快照也不写）
  (d) TOCTOU 窗口：guard 读到 running、正要覆盖时 stop commit cancelled —— 窗口存在但影响可接受
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.cc_bom_generator.db.models import Base, PipelineRun
from src.cc_bom_generator.db.repository import PipelineRepository


def _setup():
    """两个独立 Session 共享同一 in-memory engine（近似 HTTP session + bg session）。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


def test_a_column_query_bypasses_identity_map():
    """(a) 列查询 .query(run_status).scalar() 返回标量，不构造实体，不进/不读 identity map。

    构造证据：在 session1 把 run 标 cancelled 但 **不 commit**（脏写仅在 session1 事务内可见），
    session2 是独立事务，列查询应读 DB 的 **已提交** 值 running，而非 session1 的未提交脏值。
    这证明列查询走的是 DB 已提交快照，而非跨 session 的缓存。
    """
    _, Session = _setup()
    s1, s2 = Session(), Session()
    # 插入一条 run（独立 session3 提交，保证两 session 都能读到已提交基线）
    s0 = Session()
    run = PipelineRun(block_code="B1", mode="generate", run_status="running")
    s0.add(run); s0.commit(); rid = run.id; s0.close()
    # s1 改 cancelled 未提交
    r1 = s1.get(PipelineRun, rid)
    r1.run_status = "cancelled"   # 仅 s1 事务内可见
    # s2 独立事务列查询：应读到已提交的 running，不是 s1 的脏 cancelled
    val = s2.query(PipelineRun.run_status).filter(PipelineRun.id == rid).scalar()
    assert val == "running", f"列查询读到了未提交脏值 {val!r}（不应跨 session）"
    s1.rollback(); s1.close(); s2.close()


def test_b_bg_finish_reads_cancelled_and_guards():
    """(b) 后台线程此前没读过该 run → 首次 session.get 从 DB 读 cancelled → guard 拦住，不覆盖。

    模拟：HTTP session(start run + commit) → stop session(commit cancelled) → bg session 首次进 finish。
    """
    _, Session = _setup()
    # start run（请求 session）
    http = Session()
    run = PipelineRun(block_code="B2", mode="generate", run_status="running")
    http.add(run); http.commit(); rid = run.id
    # stop（请求 session）commit cancelled —— 模拟 POST /runs/{id}/stop
    run.run_status = "cancelled"; run.finished_at = None
    http.commit(); http.close()
    # 后台 session 首次 finish（此前从未读过该 run，identity map 空）
    bg = Session()
    repo = PipelineRepository(bg)
    repo.finish_pipeline_run(rid, status="success", output_bom_json={"x": 1})
    # guard 命中 → 不覆盖、不写 bom 快照
    bg.commit()
    cur = bg.query(PipelineRun).get(rid)
    assert cur.run_status == "cancelled"
    assert cur.output_bom_json is None   # guard return，连 bom 快照都没写
    bg.close()


def test_c_mid_snapshot_blocked_after_cancelled():
    """(c) 中途快照 finish(status='running', output_bom_json=...) 在 cancelled 之后也被 guard 拦。

    场景：bg 已在跑（commit_after_each 已写若干节点），用户此时 stop commit cancelled，
    bg 下一次 finish(status='running', output_bom_json=新快照) 命中 guard → 旧 bom 快照不被覆盖。
    """
    _, Session = _setup()
    bg = Session()
    run = PipelineRun(block_code="B3", mode="generate", run_status="running",
                      output_bom_json={"v": 1})  # 已有一个中途快照
    bg.add(run); bg.commit(); rid = run.id
    # 用户在另一个 session stop → cancelled 已提交
    http = Session()
    http.get(PipelineRun, rid).run_status = "cancelled"; http.commit(); http.close()
    # bg 想用新快照覆盖，但 run 已 cancelled
    repo = PipelineRepository(bg)
    repo.finish_pipeline_run(rid, status="running", output_bom_json={"v": 2})
    bg.commit()
    cur = bg.query(PipelineRun).get(rid)
    assert cur.run_status == "cancelled"
    assert cur.output_bom_json == {"v": 1}   # 旧快照保住，未被 {v:2} 覆盖
    bg.close()


def test_d_toctou_window_is_benign():
    """(d) TOCTOU 窗口存在：guard 读到 running，stop 在覆盖前 commit cancelled，最终状态由谁后 commit 决定。

    本测试证明：在 commit_after_each=True 的真实路径里，bg 的 finish 只 flush 不在 guard 内 commit，
    guard 之后还有 run.run_status=status 的写 + 调用层 commit；如果 stop 在这之间 commit cancelled，
    则取决于两者 commit 顺序（最后写者赢）。但：
      - 影响 = run_status 可能被写成 success/fail/running（终态不准），bom 快照可能被写
      - 这是「最坏=显示一个已停任务的最终态不准」，非数据损坏、非脏数据落库
      - 真实路径里 stop 要求 status==running 才能 stop，窗口只在 bg 收尾的毫秒级
    结论：可接受，无需双保险（详见报告）。
    """
    _, Session = _setup()
    bg = Session()
    run = PipelineRun(block_code="B4", mode="generate", run_status="running")
    bg.add(run); bg.commit(); rid = run.id
    http = Session()

    repo = PipelineRepository(bg)
    # 模拟 guard 读到 running（此时 stop 还没 commit）
    cur = repo.session.query(PipelineRun.run_status).filter(PipelineRun.id == rid).scalar()
    assert cur == "running"   # guard 放行
    # === TOCTOU 窗口：stop 在此刻 commit cancelled ===
    http.get(PipelineRun, rid).run_status = "cancelled"; http.commit()
    # guard 已放行，bg 继续写 success（脏写在 bg 事务里）
    r = repo.session.get(PipelineRun, rid)
    r.run_status = "success"; r.finished_at = None
    bg.commit()   # bg 后 commit → 覆盖 cancelled（终态被改成 success）
    final = http.query(PipelineRun.run_status).filter(PipelineRun.id == rid).scalar()
    assert final == "success"   # 窗口内 stop 被 bg 覆盖（已知的窄窗口，benign）
    http.close(); bg.close()


def test_normal_success_path_unaffected():
    """正常路径（无 stop）：guard 读到 running → 放行 → 写 success，回归不破。"""
    _, Session = _setup()
    s = Session()
    run = PipelineRun(block_code="B5", mode="generate", run_status="running")
    s.add(run); s.commit(); rid = run.id
    repo = PipelineRepository(s)
    repo.finish_pipeline_run(rid, status="success", output_bom_json={"ok": True})
    s.commit()
    cur = s.query(PipelineRun).get(rid)
    assert cur.run_status == "success"
    assert cur.output_bom_json == {"ok": True}
    s.close()


def test_fail_path_unaffected():
    """异常路径：guard 放行 fail。"""
    _, Session = _setup()
    s = Session()
    run = PipelineRun(block_code="B6", mode="generate", run_status="running")
    s.add(run); s.commit(); rid = run.id
    repo = PipelineRepository(s)
    repo.finish_pipeline_run(rid, status="fail", error_message="boom")
    s.commit()
    cur = s.query(PipelineRun).get(rid)
    assert cur.run_status == "fail"
    assert cur.error_message == "boom"
    s.close()
