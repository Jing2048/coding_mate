"""
策略优化器

基于执行数据优化代码生成策略。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import json


class StrategyType(Enum):
    """策略类型"""
    CONTEXT_SELECTION = "context_selection"
    PROMPT_TEMPLATE = "prompt_template"
    VERIFICATION_ORDER = "verification_order"
    RETRY_POLICY = "retry_policy"
    PARALLELISM = "parallelism"


@dataclass
class Strategy:
    """策略定义"""
    name: str
    strategy_type: StrategyType
    parameters: Dict[str, Any]
    score: float = 0.0  # 效果评分
    usage_count: int = 0
    success_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.strategy_type.value,
            "parameters": self.parameters,
            "score": self.score,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "success_rate": self.success_count / self.usage_count if self.usage_count > 0 else 0,
        }


class StrategyOptimizer:
    """
    策略优化器
    
    基于历史执行数据优化代码生成策略。
    """
    
    def __init__(self, metrics_collector: Optional[Any] = None):
        """
        初始化优化器
        
        Args:
            metrics_collector: 指标收集器
        """
        self._metrics_collector = metrics_collector
        self._strategies: Dict[str, List[Strategy]] = {
            st.value: [] for st in StrategyType
        }
        
        # 初始化默认策略
        self._init_default_strategies()
    
    def _init_default_strategies(self):
        """初始化默认策略"""
        # 上下文选择策略
        self._strategies[StrategyType.CONTEXT_SELECTION.value] = [
            Strategy(
                name="interface_first",
                strategy_type=StrategyType.CONTEXT_SELECTION,
                parameters={
                    "priority_order": ["interface", "dependency", "code"],
                    "max_tokens": 20000,
                },
                score=0.7,
            ),
            Strategy(
                name="code_first",
                strategy_type=StrategyType.CONTEXT_SELECTION,
                parameters={
                    "priority_order": ["code", "interface", "dependency"],
                    "max_tokens": 20000,
                },
                score=0.6,
            ),
            Strategy(
                name="balanced",
                strategy_type=StrategyType.CONTEXT_SELECTION,
                parameters={
                    "priority_order": ["interface", "code", "dependency"],
                    "max_tokens": 25000,
                },
                score=0.75,
            ),
        ]
        
        # 重试策略
        self._strategies[StrategyType.RETRY_POLICY.value] = [
            Strategy(
                name="aggressive",
                strategy_type=StrategyType.RETRY_POLICY,
                parameters={
                    "max_retries": 5,
                    "backoff": "exponential",
                    "base_delay_ms": 1000,
                },
                score=0.6,
            ),
            Strategy(
                name="conservative",
                strategy_type=StrategyType.RETRY_POLICY,
                parameters={
                    "max_retries": 2,
                    "backoff": "linear",
                    "base_delay_ms": 2000,
                },
                score=0.7,
            ),
            Strategy(
                name="adaptive",
                strategy_type=StrategyType.RETRY_POLICY,
                parameters={
                    "max_retries": 3,
                    "backoff": "adaptive",
                    "base_delay_ms": 1500,
                    "adapt_to_error_type": True,
                },
                score=0.8,
            ),
        ]
        
        # 验证顺序策略
        self._strategies[StrategyType.VERIFICATION_ORDER.value] = [
            Strategy(
                name="fail_fast",
                strategy_type=StrategyType.VERIFICATION_ORDER,
                parameters={
                    "order": ["syntax", "type", "contract", "unit_test"],
                    "stop_on_error": True,
                },
                score=0.75,
            ),
            Strategy(
                name="complete",
                strategy_type=StrategyType.VERIFICATION_ORDER,
                parameters={
                    "order": ["syntax", "type", "contract", "unit_test", "integration"],
                    "stop_on_error": False,
                },
                score=0.65,
            ),
        ]
        
        # 并行度策略
        self._strategies[StrategyType.PARALLELISM.value] = [
            Strategy(
                name="sequential",
                strategy_type=StrategyType.PARALLELISM,
                parameters={"max_parallel": 1},
                score=0.6,
            ),
            Strategy(
                name="moderate",
                strategy_type=StrategyType.PARALLELISM,
                parameters={"max_parallel": 3},
                score=0.8,
            ),
            Strategy(
                name="aggressive",
                strategy_type=StrategyType.PARALLELISM,
                parameters={"max_parallel": 5},
                score=0.7,
            ),
        ]
    
    def get_best_strategy(
        self,
        strategy_type: StrategyType,
        context: Optional[Dict[str, Any]] = None
    ) -> Strategy:
        """
        获取最佳策略
        
        Args:
            strategy_type: 策略类型
            context: 上下文信息（可用于条件选择）
            
        Returns:
            Strategy: 最佳策略
        """
        strategies = self._strategies.get(strategy_type.value, [])
        
        if not strategies:
            raise ValueError(f"No strategies found for type: {strategy_type}")
        
        # 基于 Thompson Sampling 的选择
        # 简化实现：选择得分最高的策略
        best = max(strategies, key=lambda s: s.score)
        
        return best
    
    def record_outcome(
        self,
        strategy: Strategy,
        success: bool,
        metrics: Optional[Dict[str, Any]] = None
    ):
        """
        记录策略执行结果
        
        Args:
            strategy: 使用的策略
            success: 是否成功
            metrics: 执行指标
        """
        strategy.usage_count += 1
        
        if success:
            strategy.success_count += 1
        
        # 更新策略得分 (简化的 EMA 更新)
        alpha = 0.1  # 学习率
        reward = 1.0 if success else 0.0
        strategy.score = (1 - alpha) * strategy.score + alpha * reward
    
    def optimize(self):
        """
        基于收集的数据优化策略
        """
        if not self._metrics_collector:
            return
        
        stats = self._metrics_collector.get_statistics()
        
        # 根据任务类型调整策略
        for task_type, type_stats in stats.get("by_task_type", {}).items():
            success_rate = (
                type_stats["success"] / type_stats["count"]
                if type_stats["count"] > 0 else 0
            )
            
            # 如果成功率低，调整策略
            if success_rate < 0.5:
                # 增加重试次数
                for strategy in self._strategies.get(StrategyType.RETRY_POLICY.value, []):
                    if "adaptive" in strategy.name:
                        strategy.score = min(1.0, strategy.score + 0.05)
                
                # 使用更保守的并行度
                for strategy in self._strategies.get(StrategyType.PARALLELISM.value, []):
                    if strategy.parameters.get("max_parallel", 0) <= 2:
                        strategy.score = min(1.0, strategy.score + 0.05)
    
    def suggest_improvements(self) -> List[str]:
        """
        建议改进措施
        
        Returns:
            List[str]: 改进建议列表
        """
        suggestions = []
        
        if not self._metrics_collector:
            return ["Enable metrics collection for optimization suggestions"]
        
        stats = self._metrics_collector.get_statistics()
        
        overall_success = stats.get("success_rate", 0)
        
        if overall_success < 0.6:
            suggestions.append(
                "Low overall success rate. Consider:"
                "\n  - Improving interface definitions"
                "\n  - Adding more context to prompts"
                "\n  - Enabling more verification levels"
            )
        
        avg_tokens = stats.get("average_tokens_per_task", 0)
        if avg_tokens > 10000:
            suggestions.append(
                f"High token usage ({avg_tokens:.0f}/task). Consider:"
                "\n  - Reducing context size"
                "\n  - Using more focused prompts"
                "\n  - Breaking down large tasks"
            )
        
        # 检查各任务类型
        for task_type, type_stats in stats.get("by_task_type", {}).items():
            type_success = (
                type_stats["success"] / type_stats["count"]
                if type_stats["count"] > 0 else 0
            )
            
            if type_success < 0.5:
                suggestions.append(
                    f"Task type '{task_type}' has low success rate ({type_success:.1%})."
                    f" Review templates and context for this type."
                )
        
        return suggestions
    
    def export_strategies(self) -> Dict[str, Any]:
        """导出所有策略"""
        return {
            strategy_type: [s.to_dict() for s in strategies]
            for strategy_type, strategies in self._strategies.items()
        }
    
    def import_strategies(self, data: Dict[str, Any]):
        """导入策略"""
        for strategy_type, strategies in data.items():
            if strategy_type in self._strategies:
                self._strategies[strategy_type] = [
                    Strategy(
                        name=s["name"],
                        strategy_type=StrategyType(s["type"]),
                        parameters=s["parameters"],
                        score=s.get("score", 0.5),
                        usage_count=s.get("usage_count", 0),
                        success_count=s.get("success_count", 0),
                    )
                    for s in strategies
                ]
