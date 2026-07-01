"""Skill 抽象基类 —— 所有节点 Skill 的统一接口。"""

from __future__ import annotations
from abc import ABC, abstractmethod

from ..schemas.generation_state import GenerationState


class BaseSkill(ABC):
    """每个 Skill 读 state 的一部分、处理、写 state 的一部分。"""

    name: str = "BaseSkill"
    use_llm: bool = False
    temperature: float = 0.3

    @abstractmethod
    def execute(self, state: GenerationState) -> GenerationState:
        """执行 Skill 逻辑，读写 state，返回更新后的 state。"""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} use_llm={self.use_llm} temp={self.temperature}>"
