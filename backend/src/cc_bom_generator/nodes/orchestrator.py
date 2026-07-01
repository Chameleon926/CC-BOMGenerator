"""
生成场景编排器 —— 按序执行 Skill，管理回修循环，写库记录。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from ..logging_config import get_logger
from ..schemas.generation_state import GenerationState
from ..db import recorder
from .base import BaseSkill

log = get_logger("orchestrator")


class GenerationOrchestrator:
    """按序执行 Skill 列表，支持受控回修，自动写库。"""

    def __init__(
        self,
        skills: List[BaseSkill],
        retry_skills: List[BaseSkill] | None = None,
        max_retries: int = 1,
    ):
        self.skills = skills
        self.max_retries = max_retries
        self.retry_skills = retry_skills or self._default_retry_skills()

    def run(self, state: GenerationState) -> GenerationState:
        """执行完整管线，自动记录到数据库。"""
        cleaned = state.cleaned
        log.info(f"管线启动: 条款={cleaned.clause} ({cleaned.block_code}), 正例数={len(cleaned.positive_values)}")

        # ---- 写库：创建 pipeline_run ----
        run_id = recorder.start_pipeline_run(
            block_code=cleaned.block_code,
            block_name=cleaned.clause,
            mode="generate",
            input_cleaned_json=cleaned.model_dump(mode="json"),
        )
        state._pipeline_run_id = run_id

        error_msg = None
        try:
            # ---- 正常流程 ----
            seq = 0
            for skill in self.skills:
                seq += 1
                state = self._execute_skill(skill, state, seq, run_id, is_retry=False)

                # 每次生成/修改 BOM 后更新 pipeline_run 的 output 快照
                if state.bom:
                    recorder.finish_pipeline_run(
                        run_id, status="running",
                        output_bom_json=state.bom.model_dump(mode="json"),
                    )

            # ---- 回修检查 ----
            if self._needs_retry(state):
                state = self._do_retry(state, run_id)

        except Exception as e:
            error_msg = str(e)
            log.error(f"管线异常: {e}")
            raise
        finally:
            # ---- 写库：结束 pipeline_run ----
            final_status = "fail" if error_msg else "success"
            final_bom = state.bom.model_dump(mode="json") if state.bom else None
            final_prompt = state.full_prompt.prompt_text if state.full_prompt else ""
            recorder.finish_pipeline_run(
                run_id,
                status=final_status,
                output_bom_json=final_bom,
                output_prompt_text=final_prompt,
                error_message=error_msg,
            )

        # ---- 写库：保存 BOM 版本 ----
        if state.bom and state.full_prompt:
            bom_id = recorder.save_bom_version(
                block_code=state.bom.block_code,
                version=state.bom.version,
                source=state.bom.source.value,
                semantic_definition=state.bom.semantic_definition,
                extraction_rules_json=state.bom.extraction_rules.model_dump(mode="json"),
                recall_profile_json=state.bom.recall_profile.model_dump(mode="json"),
                full_bom_json=state.bom.model_dump(mode="json"),
                prompt_text=state.full_prompt.prompt_text,
                pipeline_run_id=run_id,
            )
            state._bom_version_id = bom_id

        log.info(f"管线完成: 条款={cleaned.clause}, status={final_status}")
        return state

    def _execute_skill(
        self,
        skill: BaseSkill,
        state: GenerationState,
        sequence: int,
        run_id: int,
        is_retry: bool,
    ) -> GenerationState:
        """执行单个 Skill，记录耗时和输出到数据库。"""
        start = datetime.now()
        log.info(f"执行 Skill: {skill.name} (seq={sequence}, retry={is_retry})")

        success = True
        try:
            state = skill.execute(state)
        except Exception as e:
            success = False
            log.error(f"Skill {skill.name} 异常: {e}")
            raise
        finally:
            duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            # 写库：node_execution
            output_snapshot = None
            if state.bom:
                output_snapshot = {"bom_version": state.bom.version}
            if state.verification:
                output_snapshot = output_snapshot or {}
                output_snapshot["verification_summary"] = state.verification.summary

            recorder.record_node_execution(
                pipeline_run_id=run_id,
                skill_name=skill.name,
                sequence=sequence,
                input_json=None,
                output_json=output_snapshot,
                is_retry=is_retry,
                success=success,
                duration_ms=duration_ms,
            )

        return state

    def _needs_retry(self, state: GenerationState) -> bool:
        if state.retry_count >= self.max_retries:
            return False
        if state.verification:
            if state.verification.red_flags:
                return True
            for check in state.verification.checks:
                if isinstance(check, dict) and check.get("verdict") == "fail":
                    return True
        if not state.rule_check_passed:
            return True
        return False

    def _do_retry(self, state: GenerationState, run_id: int) -> GenerationState:
        state.retry_count += 1
        retry_context = self._collect_retry_feedback(state)
        log.info(f"触发回修（第 {state.retry_count} 次）: {retry_context}")

        for skill in self.retry_skills:
            if hasattr(skill, 'current_bom'):
                skill.current_bom = self._build_retry_bom_text(state)
            state = self._execute_skill(skill, state, sequence=100 + state.retry_count, run_id=run_id, is_retry=True)

        if self._needs_retry(state) and state.retry_count < self.max_retries:
            log.info(f"回修后仍有问题，但已达回修上限，输出当前版本")
        elif not self._needs_retry(state):
            log.info(f"回修成功，问题已解决")

        return state

    def _collect_retry_feedback(self, state: GenerationState) -> str:
        parts = []
        if not state.rule_check_passed:
            killed = state.rule_check_details.get('killed_examples', [])
            if killed:
                parts.append(f"拦截规则误杀{len(killed)}个正例")
        if state.verification and state.verification.red_flags:
            parts.append(f"自检红旗{len(state.verification.red_flags)}个")
            for flag in state.verification.red_flags[:2]:
                parts.append(f"  - {flag[:60]}")
        return "; ".join(parts) if parts else "未知问题"

    def _build_retry_bom_text(self, state: GenerationState) -> str:
        if state.bom is None:
            return "（无）"
        parts = [f"当前定义：{state.bom.semantic_definition}", f"\n当前规则："]
        for r in state.bom.extraction_rules.absolute_interception_rules:
            parts.append(f"  拦截：{r.rule}")
        for r in state.bom.extraction_rules.core_match_rules:
            parts.append(f"  匹配：{r.rule}")
        if not state.rule_check_passed:
            killed = state.rule_check_details.get('killed_examples', [])
            if killed:
                parts.append(f"\n⚠️ 上轮问题：拦截规则误杀了以下正例，请修正：")
                for k in killed:
                    parts.append(f"  - '{k['example']}' 被关键词 '{k['killed_by']}' 命中")
        if state.verification and state.verification.red_flags:
            parts.append(f"\n⚠️ 自检红旗：")
            for flag in state.verification.red_flags:
                parts.append(f"  - {flag}")
        return "\n".join(parts)

    def _default_retry_skills(self) -> List[BaseSkill]:
        from .skills.definition_rule import DefinitionRuleSkill
        from .skills.profile_build_skill import ProfileBuildSkill
        from .skills.rule_check import RuleCheckSkill
        from .skills.self_check import SelfCheckSkill
        return [DefinitionRuleSkill(), ProfileBuildSkill(), RuleCheckSkill(), SelfCheckSkill()]


def create_default_orchestrator() -> GenerationOrchestrator:
    from .skills.feature_extract import FeatureExtractSkill
    from .skills.example_retrieve import ExampleRetrieveSkill
    from .skills.definition_rule import DefinitionRuleSkill
    from .skills.profile_build_skill import ProfileBuildSkill
    from .skills.rule_check import RuleCheckSkill
    from .skills.self_check import SelfCheckSkill
    from .skills.prompt_assemble_skill import PromptAssembleSkill

    skills = [
        FeatureExtractSkill(),
        ExampleRetrieveSkill(),
        DefinitionRuleSkill(),
        ProfileBuildSkill(),
        RuleCheckSkill(),
        SelfCheckSkill(),
        PromptAssembleSkill(),
    ]
    return GenerationOrchestrator(skills=skills, max_retries=1)