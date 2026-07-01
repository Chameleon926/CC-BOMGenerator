"""
管线执行仓储（Repository）—— run 级 Unit-of-Work 事务版。

设计要点（vs 旧 recorder.py 函数式）：
- 构造注入 Session，所有方法共享同一个 session。
- 方法内只 add/flush，**永不 commit/rollback/close** —— 事务边界由调用层控制：
  · HTTP 入口：services.generate_service 用 FastAPI 注入的 session，成功 commit / 异常 rollback。
  · 非 HTTP 入口：nodes.pipeline.generate_bom 用 db.session_scope()（出块 commit / 异常 rollback）。
- 一次管线 run = 一个 session = 一个事务：要么完整落库要么整体回滚，避免半残记录。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    Clause, BomVersion, PipelineRun, NodeExecution, LlmCall, RuleModification,
)
from ..logging_config import get_logger

log = get_logger("db.repository")


class PipelineRepository:
    """管线执行相关写库的仓储。Session 由外部注入，事务由外部控制。"""

    def __init__(self, session: Session):
        self.session = session

    # ==================== 管线执行 ====================

    def start_pipeline_run(
        self,
        block_code: str,
        block_name: str,
        mode: str,
        input_cleaned_json: dict,
    ) -> int:
        clause = self.session.query(Clause).filter_by(block_code=block_code).first()
        if not clause:
            clause = Clause(block_code=block_code, block_name=block_name)
            self.session.add(clause)
            self.session.flush()

        run = PipelineRun(
            block_code=block_code,
            mode=mode,
            run_status="running",
            input_cleaned_json=input_cleaned_json,
        )
        self.session.add(run)
        self.session.flush()
        run_id = run.id
        log.info(f"pipeline_run 开始: id={run_id}, block_code={block_code}, mode={mode}")
        return run_id

    def finish_pipeline_run(
        self,
        run_id: int,
        status: str = "success",
        output_bom_json: Optional[dict] = None,
        output_prompt_text: str = "",
        error_message: Optional[str] = None,
        retry_count: int = 0,
    ) -> None:
        """管线结束时调用（中途更新快照也用，仅 flush 不 commit）。"""
        run = self.session.get(PipelineRun, run_id)
        if not run:
            log.error(f"pipeline_run {run_id} 不存在")
            return

        run.run_status = status
        run.finished_at = datetime.now()
        if run.started_at:
            run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        if output_bom_json is not None:
            run.output_bom_json = output_bom_json
        if output_prompt_text:
            run.output_prompt_text = output_prompt_text
        if error_message:
            run.error_message = error_message
        run.retry_count = retry_count

        log.info(f"pipeline_run 完成: id={run_id}, status={status}, duration={run.duration_ms}ms")

    # ==================== 节点执行 ====================

    def record_node_execution(
        self,
        pipeline_run_id: int,
        skill_name: str,
        seq: int,
        input_json: Optional[dict] = None,
        output_json: Optional[dict] = None,
        is_retry: bool = False,
        retry_round: int = 0,
        success: bool = True,
        duration_ms: Optional[int] = None,
    ) -> int:
        node = NodeExecution(
            pipeline_run_id=pipeline_run_id,
            skill_name=skill_name,
            seq=seq,
            is_retry=is_retry,
            retry_round=retry_round,
            input_json=input_json,
            output_json=output_json,
            success=success,
            duration_ms=duration_ms,
        )
        self.session.add(node)
        self.session.flush()
        node_id = node.id
        log.info(f"node_execution: run={pipeline_run_id}, skill={skill_name}, seq={seq}, retry_round={retry_round}, success={success}, {duration_ms}ms")
        return node_id

    # ==================== LLM 调用 ====================

    def record_llm_call(
        self,
        node_execution_id: Optional[int],
        api_format: str,
        model_name: str,
        temperature: float,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        assistant_response: Optional[str] = None,
        raw_response: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> int:
        call = LlmCall(
            node_execution_id=node_execution_id,
            api_format=api_format,
            model_name=model_name,
            temperature=temperature,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            assistant_response=assistant_response,
            raw_response=raw_response,
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        self.session.add(call)
        self.session.flush()
        call_id = call.id
        log.info(f"llm_call: id={call_id}, model={model_name}, temp={temperature}, success={success}, {duration_ms}ms")
        return call_id

    # ==================== BOM 版本 ====================

    def save_bom_version(
        self,
        block_code: str,
        version: int,
        bom_source: str,
        semantic_definition: str,
        full_bom_json: dict,
        prompt_text: str,
        pipeline_run_id: Optional[int] = None,
        created_by: str = "",
        previous_bom_id: Optional[int] = None,
    ) -> int:
        bom = BomVersion(
            block_code=block_code,
            version=version,
            bom_source=bom_source,
            semantic_definition=semantic_definition,
            full_bom_json=full_bom_json,
            prompt_text=prompt_text,
            pipeline_run_id=pipeline_run_id,
            created_by=created_by,
            previous_bom_id=previous_bom_id,
        )
        self.session.add(bom)

        clause = self.session.query(Clause).filter_by(block_code=block_code).first()
        if clause:
            clause.current_version = version

        self.session.flush()
        bom_id = bom.id
        log.info(f"bom_version 保存: id={bom_id}, block_code={block_code}, version={version}, source={bom_source}")
        return bom_id

    # ==================== 修订原因 ====================

    def save_rule_modifications(
        self,
        bom_version_id: int,
        modifications: list[dict],
        operator: str = "",
    ) -> None:
        for mod in modifications:
            record = RuleModification(
                bom_version_id=bom_version_id,
                modification_type=mod.get("type", ""),
                reason=mod.get("reason", ""),
                before_json=mod.get("before"),
                after_json=mod.get("after"),
                operator=operator,
            )
            self.session.add(record)
        log.info(f"rule_modifications 保存: bom_version_id={bom_version_id}, count={len(modifications)}")
