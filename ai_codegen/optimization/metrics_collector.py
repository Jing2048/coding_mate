"""
指标收集器

收集代码生成和执行的各类指标。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from pathlib import Path


@dataclass
class ExecutionMetrics:
    """执行指标"""
    task_id: str
    task_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    
    # 性能指标
    duration_ms: int = 0
    tokens_used: int = 0
    llm_calls: int = 0
    
    # 质量指标
    generated_files: int = 0
    generated_lines: int = 0
    syntax_errors: int = 0
    type_errors: int = 0
    test_failures: int = 0
    
    # 验证指标
    verification_passed: bool = False
    verification_levels_passed: List[str] = field(default_factory=list)
    
    # 重试指标
    retry_count: int = 0
    feedback_rounds: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "llm_calls": self.llm_calls,
            "generated_files": self.generated_files,
            "generated_lines": self.generated_lines,
            "syntax_errors": self.syntax_errors,
            "type_errors": self.type_errors,
            "test_failures": self.test_failures,
            "verification_passed": self.verification_passed,
            "verification_levels_passed": self.verification_levels_passed,
            "retry_count": self.retry_count,
            "feedback_rounds": self.feedback_rounds,
        }


@dataclass
class SessionMetrics:
    """会话指标"""
    session_id: str
    start_time: datetime
    task_metrics: List[ExecutionMetrics] = field(default_factory=list)
    
    # 聚合指标
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_tokens: int = 0
    total_duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "success_rate": self.successful_tasks / self.total_tasks if self.total_tasks > 0 else 0,
            "task_metrics": [m.to_dict() for m in self.task_metrics],
        }


class MetricsCollector:
    """
    指标收集器
    
    收集和存储代码生成执行的各类指标，用于分析和优化。
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化收集器
        
        Args:
            storage_path: 指标存储路径
        """
        self._storage_path = Path(storage_path) if storage_path else None
        self._current_session: Optional[SessionMetrics] = None
        self._historical_metrics: List[SessionMetrics] = []
    
    def start_session(self, session_id: Optional[str] = None) -> str:
        """开始新会话"""
        import uuid
        
        session_id = session_id or str(uuid.uuid4())[:8]
        self._current_session = SessionMetrics(
            session_id=session_id,
            start_time=datetime.now(),
        )
        return session_id
    
    def start_task(self, task_id: str, task_type: str) -> ExecutionMetrics:
        """开始任务计时"""
        metrics = ExecutionMetrics(
            task_id=task_id,
            task_type=task_type,
            start_time=datetime.now(),
        )
        
        if self._current_session:
            self._current_session.task_metrics.append(metrics)
            self._current_session.total_tasks += 1
        
        return metrics
    
    def end_task(
        self,
        metrics: ExecutionMetrics,
        success: bool = True
    ):
        """结束任务计时"""
        metrics.end_time = datetime.now()
        metrics.duration_ms = int(
            (metrics.end_time - metrics.start_time).total_seconds() * 1000
        )
        
        if self._current_session:
            if success:
                self._current_session.successful_tasks += 1
            else:
                self._current_session.failed_tasks += 1
            
            self._current_session.total_tokens += metrics.tokens_used
            self._current_session.total_duration_ms += metrics.duration_ms
    
    def record_llm_call(
        self,
        metrics: ExecutionMetrics,
        tokens: int
    ):
        """记录 LLM 调用"""
        metrics.llm_calls += 1
        metrics.tokens_used += tokens
    
    def record_generation(
        self,
        metrics: ExecutionMetrics,
        files: int,
        lines: int
    ):
        """记录代码生成"""
        metrics.generated_files += files
        metrics.generated_lines += lines
    
    def record_verification(
        self,
        metrics: ExecutionMetrics,
        level: str,
        passed: bool,
        errors: int = 0
    ):
        """记录验证结果"""
        if passed:
            metrics.verification_levels_passed.append(level)
        
        if level == "syntax":
            metrics.syntax_errors += errors
        elif level == "type":
            metrics.type_errors += errors
        elif level == "unit_test":
            metrics.test_failures += errors
    
    def record_retry(self, metrics: ExecutionMetrics):
        """记录重试"""
        metrics.retry_count += 1
    
    def record_feedback(self, metrics: ExecutionMetrics):
        """记录反馈轮次"""
        metrics.feedback_rounds += 1
    
    def end_session(self):
        """结束会话"""
        if self._current_session:
            self._historical_metrics.append(self._current_session)
            
            if self._storage_path:
                self._save_session(self._current_session)
            
            self._current_session = None
    
    def _save_session(self, session: SessionMetrics):
        """保存会话到文件"""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        
        file_path = self._storage_path / f"session_{session.session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
    
    def load_historical(self) -> List[SessionMetrics]:
        """加载历史指标"""
        if not self._storage_path or not self._storage_path.exists():
            return []
        
        sessions = []
        for file_path in self._storage_path.glob("session_*.json"):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 简化：不完全还原对象
                sessions.append(data)
        
        return sessions
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        all_sessions = self._historical_metrics.copy()
        if self._current_session:
            all_sessions.append(self._current_session)
        
        if not all_sessions:
            return {}
        
        total_tasks = sum(s.total_tasks for s in all_sessions)
        successful_tasks = sum(s.successful_tasks for s in all_sessions)
        total_tokens = sum(s.total_tokens for s in all_sessions)
        total_duration = sum(s.total_duration_ms for s in all_sessions)
        
        # 按任务类型统计
        type_stats: Dict[str, Dict] = {}
        for session in all_sessions:
            for task in session.task_metrics:
                if task.task_type not in type_stats:
                    type_stats[task.task_type] = {
                        "count": 0,
                        "success": 0,
                        "total_duration_ms": 0,
                        "total_tokens": 0,
                    }
                
                type_stats[task.task_type]["count"] += 1
                if task.verification_passed:
                    type_stats[task.task_type]["success"] += 1
                type_stats[task.task_type]["total_duration_ms"] += task.duration_ms
                type_stats[task.task_type]["total_tokens"] += task.tokens_used
        
        return {
            "total_sessions": len(all_sessions),
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0,
            "total_tokens": total_tokens,
            "total_duration_ms": total_duration,
            "average_tokens_per_task": total_tokens / total_tasks if total_tasks > 0 else 0,
            "average_duration_per_task": total_duration / total_tasks if total_tasks > 0 else 0,
            "by_task_type": type_stats,
        }
    
    def get_trends(self, window: int = 10) -> Dict[str, List[float]]:
        """获取趋势数据"""
        all_sessions = self._historical_metrics[-window:]
        
        return {
            "success_rates": [
                s.successful_tasks / s.total_tasks if s.total_tasks > 0 else 0
                for s in all_sessions
            ],
            "avg_durations": [
                s.total_duration_ms / s.total_tasks if s.total_tasks > 0 else 0
                for s in all_sessions
            ],
            "avg_tokens": [
                s.total_tokens / s.total_tasks if s.total_tasks > 0 else 0
                for s in all_sessions
            ],
        }
