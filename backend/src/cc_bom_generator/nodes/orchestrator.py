"""
生成场景编排器 —— 按序执行 Skill，管理回修循环。

正常流程: Skill1→2→3→4→5→6→7
Skill 5(RuleCheck) 失败 → 标记但不中断
Skill 6(SelfCheck) 有红旗 且 retry_count < 1
  → 把红旗 + current_bom 回灌 Skill 3
  → Skill 3→4→5→6 再跑一次
  → retry_count = 1，不再回修
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..contracts.generation_state import GenerationState
from ..contracts.bom import BOM, BomSource
from ..contracts.cleaned_test_set import CleanedTestSet, FullPrompt
from ..contracts.diagnosis import Verification
from .base import BaseSkill


class GenerationOrchestrator:
    """按序执行 Skill 列表，支持受控回修。"""

    def __init__(
        self,
        skills: List[BaseSkill],
        retry_skills: List[BaseSkill] | None = None,
        max_retries: int = 1,
    ):
        """
        Args:
            skills: 正常流程的 Skill 列表（按执行顺序）
            retry_skills: 回修时重跑的 Skill 子序列（默认为 None，自动取定义+画像+校验+自检）
            max_retries: 最大回修次数（默认 1）
        """
        self.skills = skills
        self.max_retries = max_retries
        # 回修时重跑的 Skill：DefinitionRule → ProfileBuild → RuleCheck → SelfCheck
        self.retry_skills = retry_skills or self._default_retry_skills()

    def run(self, state: GenerationState) -> GenerationState:
        """执行完整管线。"""
        print(f"========== 生成场景管线启动 ==========")
        print(f"条款: {state.cleaned.clause} ({state.cleaned.block_code})")
        print(f"正例数: {len(state.cleaned.positive_values)}")
        print()

        # 正常流程：逐个执行
        for skill in self.skills:
            state = skill.execute(state)

        # 回修检查
        if self._needs_retry(state):
            state = self._do_retry(state)

        print(f"\n========== 管线完成 ==========")
        return state

    def _needs_retry(self, state: GenerationState) -> bool:
        """判断是否需要回修：有红旗/拦截失败 且 retry_count < max_retries。"""
        if state.retry_count >= self.max_retries:
            return False

        # SelfCheck 有阻塞问题
        if state.verification:
            if state.verification.red_flags:
                return True
            for check in state.verification.checks:
                if isinstance(check, dict) and check.get("verdict") == "fail":
                    return True

        # RuleCheck 未通过
        if not state.rule_check_passed:
            return True

        return False

    def _do_retry(self, state: GenerationState) -> GenerationState:
        """执行一次回修：重跑 DefinitionRule → ProfileBuild → RuleCheck → SelfCheck。"""
        state.retry_count += 1
        print(f"\n  🔄 触发回修（第 {state.retry_count} 次）...")

        # 收集回修上下文（当前 BOM 的问题反馈）
        retry_context = self._collect_retry_feedback(state)
        print(f"  🔄 回修原因: {retry_context[:80]}...")

        # 更新 DefinitionRuleSkill 的 current_bom 参数
        for skill in self.retry_skills:
            if hasattr(skill, 'current_bom'):
                skill.current_bom = self._build_retry_bom_text(state)
            state = skill.execute(state)

        # 再次检查
        if self._needs_retry(state) and state.retry_count < self.max_retries:
            print(f"  ⚠️ 回修后仍有问题，但已达回修上限，输出当前版本")
        elif not self._needs_retry(state):
            print(f"  ✅ 回修成功，问题已解决")

        return state

    def _collect_retry_feedback(self, state: GenerationState) -> str:
        """收集回修原因文本。"""
        parts = []
        if not state.rule_check_passed:
            details = state.rule_check_details
            killed = details.get('killed_examples', [])
            if killed:
                parts.append(f"拦截规则误杀{len(killed)}个正例")

        if state.verification and state.verification.red_flags:
            parts.append(f"自检红旗{len(state.verification.red_flags)}个")
            for flag in state.verification.red_flags[:2]:
                parts.append(f"  - {flag[:60]}")

        return "; ".join(parts) if parts else "未知问题"

    def _build_retry_bom_text(self, state: GenerationState) -> str:
        """把当前 BOM + 问题反馈拼成 current_bom 文本。"""
        if state.bom is None:
            return "（无）"

        parts = [
            f"当前定义：{state.bom.semantic_definition}",
            f"\n当前规则：",
        ]

        for r in state.bom.extraction_rules.absolute_interception_rules:
            parts.append(f"  拦截：{r.rule}")
        for r in state.bom.extraction_rules.core_match_rules:
            parts.append(f"  匹配：{r.rule}")

        # 加上问题反馈
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
        """默认回修 Skill 序列。"""
        # 延迟导入避免循环依赖
        from .skills.definition_rule import DefinitionRuleSkill
        from .skills.profile_build_skill import ProfileBuildSkill
        from .skills.rule_check import RuleCheckSkill
        from .skills.self_check import SelfCheckSkill

        return [
            DefinitionRuleSkill(),  # current_bom 会在 _do_retry 里动态设置
            ProfileBuildSkill(),
            RuleCheckSkill(),
            SelfCheckSkill(),
        ]


def create_default_orchestrator() -> GenerationOrchestrator:
    """创建默认的生成场景编排器。"""
    from .skills.feature_extract import FeatureExtractSkill
    from .skills.example_retrieve import ExampleRetrieveSkill
    from .skills.definition_rule import DefinitionRuleSkill
    from .skills.profile_build_skill import ProfileBuildSkill
    from .skills.rule_check import RuleCheckSkill
    from .skills.self_check import SelfCheckSkill
    from .skills.prompt_assemble_skill import PromptAssembleSkill

    skills = [
        FeatureExtractSkill(),     # 1. 特征挖掘
        ExampleRetrieveSkill(),     # 2. 正例挑选
        DefinitionRuleSkill(),     # 3. 定义+规则
        ProfileBuildSkill(),       # 4. 画像
        RuleCheckSkill(),          # 5. 程序化校验
        SelfCheckSkill(),          # 6. LLM 自检
        PromptAssembleSkill(),     # 7. 组装提示词
    ]

    return GenerationOrchestrator(skills=skills, max_retries=1)
