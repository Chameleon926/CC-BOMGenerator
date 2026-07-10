"""
生成场景编排器 —— 按序执行 Skill，管理回修循环，通过 Repository 写库。

事务边界：run(state, repo) 接收外部注入的 PipelineRepository（共享 session）。
orchestrator 只通过 repo 写库（repo 方法只 flush 不 commit），事务由调用层控制：
  · HTTP 入口：services.generate_service 管 commit / rollback
  · 非 HTTP 入口：nodes.pipeline.generate_bom 用 db.session_scope() 管 commit
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from ..logging_config import get_logger
from ..schemas.generation_state import GenerationState
from .base import BaseSkill

if TYPE_CHECKING:
    from ..db.repository import PipelineRepository

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
        self._commit_after_each = False

    def run(self, state: GenerationState, repo: "PipelineRepository", run_id: int | None = None, commit_after_each: bool = False) -> GenerationState:
        """执行完整管线，通过 repo 记录到数据库（事务由调用层控制）。

        run_id: 异步场景由调用方先 start_pipeline_run 拿到 run_id 并返回给前端，
                再起线程调本方法（传入 run_id）跑剩余节点；不传则内部创建。
        commit_after_each: HTTP 异步路径设 True，每个节点写库后立即 commit，
                让 /runs/{id}/status 实时看到节点进度（牺牲 run 级事务原子性；generate 半残可接受，有 run_status 标记）。
        """
        self._commit_after_each = commit_after_each
        cleaned = state.cleaned
        log.info(f"管线启动: 条款={cleaned.clause} ({cleaned.block_code}), 正例数={len(cleaned.positive_values)}")

        # ---- 写库：创建 pipeline_run（异步场景已由调用方创建，复用 run_id）----
        if run_id is None:
            run_id = repo.start_pipeline_run(
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
                state = self._execute_skill(skill, state, seq, run_id, repo, is_retry=False)

                # 每次生成/修改 BOM 后更新 pipeline_run 的 output 快照（仅 flush，不破坏外层事务）
                if state.bom:
                    repo.finish_pipeline_run(
                        run_id, status="running",
                        output_bom_json=state.bom.model_dump(mode="json"),
                    )
                    if self._commit_after_each:
                        repo.session.commit()

            # ---- 回修检查 ----
            if self._needs_retry(state):
                state = self._do_retry(state, run_id, repo)

        except Exception as e:
            error_msg = str(e)
            log.error(f"管线异常: {e}")
            raise
        finally:
            # ---- 写库：结束 pipeline_run ----
            final_status = "fail" if error_msg else "success"
            final_bom = state.bom.model_dump(mode="json") if state.bom else None
            final_prompt = state.full_prompt.prompt_text if state.full_prompt else ""
            repo.finish_pipeline_run(
                run_id,
                status=final_status,
                output_bom_json=final_bom,
                output_prompt_text=final_prompt,
                error_message=error_msg,
            )
            if self._commit_after_each:
                repo.session.commit()

        # ---- 写库：保存 BOM 版本 ----
        if state.bom and state.full_prompt:
            bom_id = repo.save_bom_version(
                block_code=state.bom.block_code,
                version=state.bom.version,
                bom_source=state.bom.source.value,
                semantic_definition=state.bom.semantic_definition,
                full_bom_json=state.bom.model_dump(mode="json"),
                prompt_text=state.full_prompt.prompt_text,
                pipeline_run_id=run_id,
            )
            state._bom_version_id = bom_id
            if self._commit_after_each:
                repo.session.commit()

        log.info(f"管线完成: 条款={cleaned.clause}, status={final_status}")
        return state

    def _execute_skill(
        self,
        skill: BaseSkill,
        state: GenerationState,
        sequence: int,
        run_id: int,
        repo: "PipelineRepository",
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
            if state.selected_examples:
                # Skill2 选取的代表正例（带 doc_id 行结构），落库供 result.selected_examples 追溯
                output_snapshot = output_snapshot or {}
                output_snapshot["selected_examples"] = [
                    ex.model_dump(mode="json") for ex in state.selected_examples
                ]
            if state.keywords or state.confusion_words:
                # Skill1 统计抽取的关键词/混淆词，落库供 result 在后续失败时也能展示部分结果
                output_snapshot = output_snapshot or {}
                if state.keywords:
                    output_snapshot["keywords"] = [k for k in state.keywords if k.strip()]
                if state.confusion_words:
                    output_snapshot["confusion_words"] = [k for k in state.confusion_words if k.strip()]
            if state.verification:
                output_snapshot = output_snapshot or {}
                output_snapshot["verification_summary"] = state.verification.summary

            repo.record_node_execution(
                pipeline_run_id=run_id,
                skill_name=skill.name,
                seq=sequence,
                input_json=None,
                output_json=output_snapshot,
                is_retry=is_retry,
                retry_round=state.retry_count if is_retry else 0,
                success=success,
                duration_ms=duration_ms,
            )
            if self._commit_after_each:
                repo.session.commit()  # 节点级 commit，让 /status 实时可见

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

    def _do_retry(self, state: GenerationState, run_id: int, repo: "PipelineRepository") -> GenerationState:
        state.retry_count += 1
        retry_context = self._collect_retry_feedback(state)
        log.info(f"触发回修（第 {state.retry_count} 次）: {retry_context}")

        for skill in self.retry_skills:
            if hasattr(skill, 'current_bom'):
                skill.current_bom = self._build_retry_bom_text(state)
            state = self._execute_skill(skill, state, sequence=100 + state.retry_count, run_id=run_id, repo=repo, is_retry=True)

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
        """拼当前 BOM 文本作为 DefinitionRuleSkill 的 current_bom 种子。

        含全精细字段（logic/poison_words/reasoning_chain/scene_judgments）+ 上轮自检/校验问题，
        使 gen_stage1 回修时能看到上轮精细规则而非退化为粗规则。空列表优雅跳过。
        """
        if state.bom is None:
            return "（无）"
        bom = state.bom
        parts = [f"当前定义：{bom.semantic_definition}", "当前规则："]

        # 【拦截】（命中即放弃）
        if bom.extraction_rules.absolute_interception_rules:
            parts.append("【拦截】（命中即放弃）")
            for r in bom.extraction_rules.absolute_interception_rules:
                logic = f"（逻辑：{r.logic}）" if r.logic else ""
                scene = f"[{r.scene}] " if r.scene else ""
                parts.append(f"  - {scene}{r.rule}{logic}")

        # 【匹配】（满足即提取）
        if bom.extraction_rules.core_match_rules:
            parts.append("【匹配】（满足即提取）")
            for r in bom.extraction_rules.core_match_rules:
                logic = f"（逻辑：{r.logic}）" if r.logic else ""
                scene = f"[{r.scene}] " if r.scene else ""
                parts.append(f"  - {scene}{r.rule}{logic}")

        # 【毒药词】（一票否决）
        if bom.extraction_rules.poison_words:
            parts.append(f"【毒药词】（一票否决）：{', '.join(bom.extraction_rules.poison_words)}")

        # 【思维链】（排雷步骤）
        if bom.reasoning_chain:
            parts.append("【思维链】（排雷步骤）：")
            for step in bom.reasoning_chain:
                parts.append(f"  - {step}")

        # 【判例分析】
        if bom.scene_judgments:
            parts.append("【判例分析】：")
            for sj in bom.scene_judgments:
                scene = f"[{sj.scene}] " if sj.scene else ""
                parts.append(
                    f"  - {scene}反例：{sj.negative_case} | 正例：{sj.positive_case} | 分析：{sj.analysis}"
                )

        # ⚠️ 上轮自检/校验问题（red_flags + 误杀正例注入种子，回修时针对性修）
        feedback = self._collect_retry_feedback(state)
        if feedback and feedback != "未知问题":
            parts.append("⚠️ 上轮自检/校验问题：")
            parts.append(feedback)

        return "\n".join(parts)

    def _default_retry_skills(self) -> List[BaseSkill]:
        from .skills.definition_rule import DefinitionRuleSkill
        from .skills.profile_build_skill import ProfileBuildSkill
        from .skills.rule_check import RuleCheckSkill
        from .skills.self_check import SelfCheckSkill
        from .skills.prompt_assemble_skill import PromptAssembleSkill
        return [DefinitionRuleSkill(), ProfileBuildSkill(), RuleCheckSkill(), SelfCheckSkill(), PromptAssembleSkill()]


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
