"""
管线执行写库模块。

负责把管线执行过程持久化到数据库：
- PipelineRun：每次 generate_bom() 执行
- NodeExecution：每个 Skill 执行
- LlmCall：每次 call_json() 调用
- BomVersion：最终 BOM 快照
- RuleModification：规则修订原因
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from . import SessionLocal
from .models import (
    Clause, BomVersion, PipelineRun, NodeExecution, LlmCall, RuleModification,
)
from ..logging_config import get_logger

log = get_logger("db.recorder")


# ==================== 管线执行 ====================

def start_pipeline_run(
    block_code: str,
    block_name: str,
    mode: str,
    input_cleaned_json: dict,
) -> int:
    """管线开始时调用，返回 pipeline_run_id。"""
    session = SessionLocal()
    try:
        # 确保 clause 存在
        clause = session.query(Clause).filter_by(block_code=block_code).first()
        if not clause:
            clause = Clause(block_code=block_code, block_name=block_name)
            session.add(clause)
            session.flush()

        run = PipelineRun(
            block_code=block_code,
            mode=mode,
            status="running",
            input_cleaned_json=input_cleaned_json,
            started_at=datetime.now(),
        )
        session.add(run)
        session.commit()
        run_id = run.id
        log.info(f"pipeline_run 开始: id={run_id}, block_code={block_code}, mode={mode}")
        return run_id
    except Exception as e:
        session.rollback()
        log.error(f"pipeline_run 创建失败: {e}")
        raise
    finally:
        session.close()


def finish_pipeline_run(
    run_id: int,
    status: str = "success",
    output_bom_json: Optional[dict] = None,
    output_prompt_text: str = "",
    error_message: Optional[str] = None,
):
    """管线结束时调用。"""
    session = SessionLocal()
    try:
        run = session.query(PipelineRun).get(run_id)
        if not run:
            log.error(f"pipeline_run {run_id} 不存在")
            return

        run.status = status
        run.finished_at = datetime.now()
        if run.started_at:
            run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        run.output_bom_json = output_bom_json
        run.output_prompt_text = output_prompt_text
        if error_message:
            run.error_message = error_message

        session.commit()
        log.info(f"pipeline_run 完成: id={run_id}, status={status}, duration={run.duration_ms}ms")
    except Exception as e:
        session.rollback()
        log.error(f"pipeline_run 更新失败: {e}")
        raise
    finally:
        session.close()


# ==================== 节点执行 ====================

def record_node_execution(
    pipeline_run_id: int,
    skill_name: str,
    sequence: int,
    input_json: Optional[dict] = None,
    output_json: Optional[dict] = None,
    is_retry: bool = False,
    success: bool = True,
    duration_ms: Optional[int] = None,
) -> int:
    """记录一个 Skill 的执行。返回 node_execution_id。"""
    session = SessionLocal()
    try:
        node = NodeExecution(
            pipeline_run_id=pipeline_run_id,
            skill_name=skill_name,
            sequence=sequence,
            is_retry=is_retry,
            input_json=input_json,
            output_json=output_json,
            success=success,
            duration_ms=duration_ms,
        )
        session.add(node)
        session.commit()
        node_id = node.id
        log.info(f"node_execution: run={pipeline_run_id}, skill={skill_name}, seq={sequence}, success={success}, {duration_ms}ms")
        return node_id
    except Exception as e:
        session.rollback()
        log.error(f"node_execution 记录失败: {e}")
        raise
    finally:
        session.close()


# ==================== LLM 调用 ====================

def record_llm_call(
    node_execution_id: Optional[int],
    api_format: str,
    model: str,
    temperature: float,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    assistant_response: Optional[str] = None,
    raw_response: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> int:
    """记录一次大模型调用。返回 llm_call_id。"""
    session = SessionLocal()
    try:
        call = LlmCall(
            node_execution_id=node_execution_id,
            api_format=api_format,
            model=model,
            temperature=temperature,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            assistant_response=assistant_response,
            raw_response=raw_response,
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        session.add(call)
        session.commit()
        call_id = call.id
        log.info(f"llm_call: id={call_id}, model={model}, temp={temperature}, success={success}, {duration_ms}ms")
        return call_id
    except Exception as e:
        session.rollback()
        log.error(f"llm_call 记录失败: {e}")
        raise
    finally:
        session.close()


# ==================== BOM 版本 ====================

def save_bom_version(
    block_code: str,
    version: int,
    source: str,
    semantic_definition: str,
    extraction_rules_json: dict,
    recall_profile_json: dict,
    full_bom_json: dict,
    prompt_text: str,
    pipeline_run_id: Optional[int] = None,
    created_by: str = "",
    previous_bom_id: Optional[int] = None,
) -> int:
    """保存 BOM 版本快照。返回 bom_version_id。"""
    session = SessionLocal()
    try:
        bom = BomVersion(
            block_code=block_code,
            version=version,
            source=source,
            semantic_definition=semantic_definition,
            extraction_rules_json=extraction_rules_json,
            recall_profile_json=recall_profile_json,
            full_bom_json=full_bom_json,
            prompt_text=prompt_text,
            pipeline_run_id=pipeline_run_id,
            created_by=created_by,
            previous_bom_id=previous_bom_id,
        )
        session.add(bom)

        # 更新 clause 的 current_version
        clause = session.query(Clause).filter_by(block_code=block_code).first()
        if clause:
            clause.current_version = version

        session.commit()
        bom_id = bom.id
        log.info(f"bom_version 保存: id={bom_id}, block_code={block_code}, version={version}, source={source}")
        return bom_id
    except Exception as e:
        session.rollback()
        log.error(f"bom_version 保存失败: {e}")
        raise
    finally:
        session.close()


# ==================== 修订原因 ====================

def save_rule_modifications(
    bom_version_id: int,
    modifications: list[dict],
    operator: str = "",
):
    """保存规则修订记录。"""
    session = SessionLocal()
    try:
        for mod in modifications:
            record = RuleModification(
                bom_version_id=bom_version_id,
                modification_type=mod.get("type", ""),
                reason=mod.get("reason", ""),
                before_text=mod.get("before", ""),
                after_text=mod.get("after", ""),
                operator=operator,
            )
            session.add(record)
        session.commit()
        log.info(f"rule_modifications 保存: bom_version_id={bom_version_id}, count={len(modifications)}")
    except Exception as e:
        session.rollback()
        log.error(f"rule_modifications 保存失败: {e}")
        raise
    finally:
        session.close()
