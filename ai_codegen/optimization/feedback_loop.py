"""
反馈循环

实现基于执行结果的持续学习和改进。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import json
from pathlib import Path


@dataclass
class FeedbackEntry:
    """反馈条目"""
    id: str
    task_id: str
    feedback_type: str  # success, failure, improvement
    source: str  # human, automated, llm
    content: str
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    applied: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "feedback_type": self.feedback_type,
            "source": self.source,
            "content": self.content,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "applied": self.applied,
        }


@dataclass
class LearningPattern:
    """学习到的模式"""
    pattern_id: str
    description: str
    condition: str  # 触发条件
    action: str  # 建议的操作
    confidence: float = 0.5
    occurrences: int = 0
    success_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "description": self.description,
            "condition": self.condition,
            "action": self.action,
            "confidence": self.confidence,
            "occurrences": self.occurrences,
            "success_count": self.success_count,
            "success_rate": self.success_count / self.occurrences if self.occurrences > 0 else 0,
        }


class FeedbackLoop:
    """
    反馈循环
    
    收集执行反馈，识别模式，持续改进代码生成质量。
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化反馈循环
        
        Args:
            storage_path: 存储路径
        """
        self._storage_path = Path(storage_path) if storage_path else None
        self._feedback_entries: List[FeedbackEntry] = []
        self._patterns: Dict[str, LearningPattern] = {}
        self._callbacks: Dict[str, List[Callable]] = {
            "pattern_detected": [],
            "feedback_received": [],
        }
        
        # 初始化常见模式
        self._init_common_patterns()
    
    def _init_common_patterns(self):
        """初始化常见的失败模式"""
        common_patterns = [
            LearningPattern(
                pattern_id="missing_import",
                description="Generated code missing necessary imports",
                condition="NameError or ImportError in verification",
                action="Add import analysis step before code generation",
                confidence=0.8,
            ),
            LearningPattern(
                pattern_id="type_mismatch",
                description="Type mismatch between interface and implementation",
                condition="Type errors in verification",
                action="Include interface types explicitly in prompt",
                confidence=0.7,
            ),
            LearningPattern(
                pattern_id="incomplete_implementation",
                description="Generated code has placeholder or TODO comments",
                condition="Contains 'TODO', 'FIXME', or '...' in output",
                action="Request complete implementation explicitly",
                confidence=0.9,
            ),
            LearningPattern(
                pattern_id="test_coverage_low",
                description="Generated tests don't cover edge cases",
                condition="Mutation testing score below threshold",
                action="Include edge cases from contract in test prompt",
                confidence=0.6,
            ),
            LearningPattern(
                pattern_id="context_overflow",
                description="Context too large causing truncation",
                condition="Token count exceeds budget",
                action="Use more aggressive context pruning",
                confidence=0.75,
            ),
        ]
        
        for pattern in common_patterns:
            self._patterns[pattern.pattern_id] = pattern
    
    def on(self, event: str, callback: Callable):
        """注册事件回调"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs):
        """触发事件"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception:
                pass
    
    def add_feedback(
        self,
        task_id: str,
        feedback_type: str,
        content: str,
        source: str = "automated",
        context: Optional[Dict] = None
    ) -> FeedbackEntry:
        """
        添加反馈
        
        Args:
            task_id: 任务 ID
            feedback_type: 反馈类型 (success, failure, improvement)
            content: 反馈内容
            source: 来源 (human, automated, llm)
            context: 上下文信息
            
        Returns:
            FeedbackEntry: 反馈条目
        """
        import uuid
        
        entry = FeedbackEntry(
            id=str(uuid.uuid4())[:8],
            task_id=task_id,
            feedback_type=feedback_type,
            source=source,
            content=content,
            context=context or {},
        )
        
        self._feedback_entries.append(entry)
        self._emit("feedback_received", entry)
        
        # 尝试检测模式
        if feedback_type == "failure":
            self._detect_patterns(entry)
        
        # 保存
        if self._storage_path:
            self._save_feedback(entry)
        
        return entry
    
    def _detect_patterns(self, entry: FeedbackEntry):
        """检测失败模式"""
        content_lower = entry.content.lower()
        context = entry.context
        
        for pattern_id, pattern in self._patterns.items():
            matched = False
            
            # 基于条件检测
            if pattern_id == "missing_import":
                if "nameerror" in content_lower or "importerror" in content_lower:
                    matched = True
                    
            elif pattern_id == "type_mismatch":
                if "type" in content_lower and "error" in content_lower:
                    matched = True
                    
            elif pattern_id == "incomplete_implementation":
                code = context.get("generated_code", "")
                if "TODO" in code or "FIXME" in code or "..." in code:
                    matched = True
                    
            elif pattern_id == "test_coverage_low":
                mutation_score = context.get("mutation_score", 1.0)
                if mutation_score < 0.7:
                    matched = True
                    
            elif pattern_id == "context_overflow":
                tokens = context.get("tokens_used", 0)
                budget = context.get("token_budget", float("inf"))
                if tokens > budget * 0.95:
                    matched = True
            
            if matched:
                pattern.occurrences += 1
                self._emit("pattern_detected", pattern, entry)
    
    def record_pattern_outcome(
        self,
        pattern_id: str,
        success: bool
    ):
        """记录模式应用结果"""
        if pattern_id in self._patterns:
            pattern = self._patterns[pattern_id]
            pattern.occurrences += 1
            if success:
                pattern.success_count += 1
            
            # 更新置信度
            alpha = 0.1
            reward = 1.0 if success else 0.0
            pattern.confidence = (1 - alpha) * pattern.confidence + alpha * reward
    
    def get_recommendations(
        self,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        获取基于上下文的建议
        
        Args:
            context: 当前上下文
            
        Returns:
            List[Dict]: 建议列表
        """
        recommendations = []
        
        # 基于历史反馈
        recent_failures = [
            f for f in self._feedback_entries[-50:]
            if f.feedback_type == "failure"
        ]
        
        # 统计失败原因
        failure_reasons = {}
        for failure in recent_failures:
            reason = failure.context.get("error_type", "unknown")
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        
        # 基于高频失败原因生成建议
        for reason, count in sorted(
            failure_reasons.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]:
            # 查找相关模式
            for pattern in self._patterns.values():
                if reason.lower() in pattern.condition.lower():
                    if pattern.confidence > 0.5:
                        recommendations.append({
                            "pattern": pattern.pattern_id,
                            "description": pattern.description,
                            "action": pattern.action,
                            "confidence": pattern.confidence,
                            "based_on": f"{count} recent failures",
                        })
        
        # 基于当前上下文的特定建议
        task_type = context.get("task_type", "")
        
        if task_type == "implementation":
            recommendations.append({
                "pattern": "implementation_best_practice",
                "description": "Implementation task detected",
                "action": "Ensure interface definition is included in context",
                "confidence": 0.9,
            })
        
        elif task_type == "unit_test":
            recommendations.append({
                "pattern": "test_best_practice",
                "description": "Test generation task detected",
                "action": "Include contract conditions and edge cases in prompt",
                "confidence": 0.85,
            })
        
        return recommendations
    
    def learn_from_success(
        self,
        task_id: str,
        context: Dict[str, Any],
        result: Dict[str, Any]
    ):
        """
        从成功案例学习
        
        Args:
            task_id: 任务 ID
            context: 执行上下文
            result: 执行结果
        """
        # 记录成功的配置
        success_config = {
            "task_type": context.get("task_type"),
            "context_size": context.get("context_tokens", 0),
            "interface_included": context.get("interface_included", False),
            "retry_count": result.get("retry_count", 0),
        }
        
        # 添加成功反馈
        self.add_feedback(
            task_id=task_id,
            feedback_type="success",
            content="Task completed successfully",
            source="automated",
            context=success_config,
        )
        
        # 更新相关模式的成功计数
        if success_config.get("interface_included"):
            if "type_mismatch" in self._patterns:
                self._patterns["type_mismatch"].success_count += 1
    
    def generate_improvement_report(self) -> Dict[str, Any]:
        """生成改进报告"""
        total_feedback = len(self._feedback_entries)
        success_count = sum(
            1 for f in self._feedback_entries
            if f.feedback_type == "success"
        )
        failure_count = sum(
            1 for f in self._feedback_entries
            if f.feedback_type == "failure"
        )
        
        # 模式分析
        pattern_analysis = []
        for pattern in self._patterns.values():
            if pattern.occurrences > 0:
                pattern_analysis.append({
                    "pattern": pattern.pattern_id,
                    "description": pattern.description,
                    "occurrences": pattern.occurrences,
                    "confidence": pattern.confidence,
                    "recommended_action": pattern.action,
                })
        
        # 按出现次数排序
        pattern_analysis.sort(key=lambda x: x["occurrences"], reverse=True)
        
        # 改进建议
        suggestions = []
        
        if failure_count > success_count * 0.3:
            suggestions.append(
                "High failure rate detected. Review interface definitions "
                "and ensure they are complete and accurate."
            )
        
        for pattern in pattern_analysis[:3]:
            if pattern["occurrences"] > 5:
                suggestions.append(
                    f"Pattern '{pattern['pattern']}' detected {pattern['occurrences']} times. "
                    f"Recommended action: {pattern['recommended_action']}"
                )
        
        return {
            "summary": {
                "total_feedback": total_feedback,
                "success_count": success_count,
                "failure_count": failure_count,
                "success_rate": success_count / total_feedback if total_feedback > 0 else 0,
            },
            "pattern_analysis": pattern_analysis,
            "suggestions": suggestions,
            "generated_at": datetime.now().isoformat(),
        }
    
    def _save_feedback(self, entry: FeedbackEntry):
        """保存反馈到文件"""
        if not self._storage_path:
            return
        
        self._storage_path.mkdir(parents=True, exist_ok=True)
        
        file_path = self._storage_path / "feedback.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    
    def load_feedback(self):
        """加载历史反馈"""
        if not self._storage_path:
            return
        
        file_path = self._storage_path / "feedback.jsonl"
        if not file_path.exists():
            return
        
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    entry = FeedbackEntry(
                        id=data["id"],
                        task_id=data["task_id"],
                        feedback_type=data["feedback_type"],
                        source=data["source"],
                        content=data["content"],
                        context=data.get("context", {}),
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        applied=data.get("applied", False),
                    )
                    self._feedback_entries.append(entry)
    
    def export_patterns(self) -> Dict[str, Any]:
        """导出学习到的模式"""
        return {
            pattern_id: pattern.to_dict()
            for pattern_id, pattern in self._patterns.items()
        }
    
    def import_patterns(self, data: Dict[str, Any]):
        """导入模式"""
        for pattern_id, pattern_data in data.items():
            self._patterns[pattern_id] = LearningPattern(
                pattern_id=pattern_data["pattern_id"],
                description=pattern_data["description"],
                condition=pattern_data["condition"],
                action=pattern_data["action"],
                confidence=pattern_data.get("confidence", 0.5),
                occurrences=pattern_data.get("occurrences", 0),
                success_count=pattern_data.get("success_count", 0),
            )
