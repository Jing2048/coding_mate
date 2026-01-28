"""
主验证器

协调多层验证流水线。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import asyncio


class VerificationLevel(Enum):
    """验证层级"""
    L0_SYNTAX = "syntax"
    L1_TYPE = "type"
    L2_CONTRACT = "contract"
    L3_UNIT_TEST = "unit_test"
    L4_MUTATION = "mutation"
    L5_INTEGRATION = "integration"


class Severity(Enum):
    """问题严重程度"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class VerificationIssue:
    """验证问题"""
    level: VerificationLevel
    severity: Severity
    message: str
    file_path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    rule: Optional[str] = None
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "rule": self.rule,
            "suggestion": self.suggestion,
        }


@dataclass
class VerificationResult:
    """验证结果"""
    passed: bool
    level: VerificationLevel
    issues: List[VerificationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "level": self.level.value,
            "issues": [i.to_dict() for i in self.issues],
            "metrics": self.metrics,
            "duration_ms": self.duration_ms,
        }
    
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)
    
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)


@dataclass
class VerificationReport:
    """验证报告"""
    file_path: str
    results: Dict[VerificationLevel, VerificationResult] = field(default_factory=dict)
    passed: bool = True
    total_issues: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "results": {k.value: v.to_dict() for k, v in self.results.items()},
            "passed": self.passed,
            "total_issues": self.total_issues,
        }
    
    def add_result(self, result: VerificationResult):
        self.results[result.level] = result
        self.total_issues += len(result.issues)
        if not result.passed:
            self.passed = False


class VerificationConfig:
    """验证配置"""
    
    def __init__(self):
        self.enabled_levels: Set[VerificationLevel] = {
            VerificationLevel.L0_SYNTAX,
            VerificationLevel.L1_TYPE,
            VerificationLevel.L2_CONTRACT,
            VerificationLevel.L3_UNIT_TEST,
        }
        
        self.fail_fast: bool = True
        self.coverage_threshold: float = 0.8
        self.mutation_threshold: float = 0.7
        
        self.language_config: Dict[str, Dict] = {
            "python": {
                "syntax_tool": "tree-sitter",
                "type_tool": "mypy",
                "test_framework": "pytest",
            },
            "typescript": {
                "syntax_tool": "tree-sitter",
                "type_tool": "tsc",
                "test_framework": "jest",
            },
            "swift": {
                "syntax_tool": "tree-sitter",
                "type_tool": "swiftc",
                "test_framework": "xctest",
            },
        }


class Verifier:
    """
    主验证器
    
    协调多层验证流水线，按顺序执行各层验证。
    """
    
    def __init__(
        self,
        config: Optional[VerificationConfig] = None,
        syntax_checker: Optional[Any] = None,
        type_checker: Optional[Any] = None,
        contract_validator: Optional[Any] = None,
        test_runner: Optional[Any] = None
    ):
        """
        初始化验证器
        
        Args:
            config: 验证配置
            syntax_checker: 语法检查器
            type_checker: 类型检查器
            contract_validator: 契约验证器
            test_runner: 测试运行器
        """
        self.config = config or VerificationConfig()
        
        # 延迟导入以避免循环依赖
        from .syntax_checker import SyntaxChecker
        from .type_checker import TypeChecker
        from .contract_validator import ContractValidator
        from .test_runner import TestRunner
        
        self._syntax_checker = syntax_checker or SyntaxChecker()
        self._type_checker = type_checker or TypeChecker()
        self._contract_validator = contract_validator or ContractValidator()
        self._test_runner = test_runner or TestRunner()
    
    async def verify(
        self,
        file_path: str,
        content: str,
        language: str = "python"
    ) -> VerificationReport:
        """
        执行完整验证流水线
        
        Args:
            file_path: 文件路径
            content: 文件内容
            language: 编程语言
            
        Returns:
            VerificationReport: 验证报告
        """
        report = VerificationReport(file_path=file_path)
        
        # 按层级顺序执行验证
        for level in VerificationLevel:
            if level not in self.config.enabled_levels:
                continue
            
            result = await self._run_level(level, file_path, content, language)
            report.add_result(result)
            
            # 如果配置了 fail_fast 且有错误，停止后续验证
            if self.config.fail_fast and not result.passed:
                break
        
        return report
    
    async def _run_level(
        self,
        level: VerificationLevel,
        file_path: str,
        content: str,
        language: str
    ) -> VerificationResult:
        """执行单层验证"""
        import time
        start_time = time.time()
        
        if level == VerificationLevel.L0_SYNTAX:
            result = await self._syntax_checker.check(file_path, content, language)
        elif level == VerificationLevel.L1_TYPE:
            result = await self._type_checker.check(file_path, content, language)
        elif level == VerificationLevel.L2_CONTRACT:
            result = await self._contract_validator.validate(file_path, content)
        elif level == VerificationLevel.L3_UNIT_TEST:
            result = await self._test_runner.run_tests(file_path)
        elif level == VerificationLevel.L4_MUTATION:
            result = await self._run_mutation_testing(file_path)
        elif level == VerificationLevel.L5_INTEGRATION:
            result = await self._run_integration_tests(file_path)
        else:
            result = VerificationResult(passed=True, level=level)
        
        result.duration_ms = int((time.time() - start_time) * 1000)
        return result
    
    async def _run_mutation_testing(self, file_path: str) -> VerificationResult:
        """运行变异测试"""
        # 简化实现
        return VerificationResult(
            passed=True,
            level=VerificationLevel.L4_MUTATION,
            metrics={"mutation_score": 0.0, "mutants_killed": 0, "mutants_total": 0},
        )
    
    async def _run_integration_tests(self, file_path: str) -> VerificationResult:
        """运行集成测试"""
        # 简化实现
        return VerificationResult(
            passed=True,
            level=VerificationLevel.L5_INTEGRATION,
        )
    
    async def verify_file(self, file_path: str, content: str) -> List[str]:
        """
        验证文件并返回错误列表
        
        Args:
            file_path: 文件路径
            content: 文件内容
            
        Returns:
            List[str]: 错误消息列表
        """
        # 检测语言
        language = self._detect_language(file_path)
        
        # 执行验证
        report = await self.verify(file_path, content, language)
        
        # 收集错误
        errors = []
        for result in report.results.values():
            for issue in result.issues:
                if issue.severity == Severity.ERROR:
                    errors.append(
                        f"[{issue.level.value}] {issue.file_path}:{issue.line}: {issue.message}"
                    )
        
        return errors
    
    def _detect_language(self, file_path: str) -> str:
        """检测文件语言"""
        from pathlib import Path
        
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".swift": "swift",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
        }
        
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "python")
    
    async def verify_batch(
        self,
        files: List[tuple[str, str]],
        language: str = "python"
    ) -> Dict[str, VerificationReport]:
        """
        批量验证文件
        
        Args:
            files: (文件路径, 内容) 元组列表
            language: 编程语言
            
        Returns:
            Dict: 文件路径到验证报告的映射
        """
        tasks = [
            self.verify(path, content, language)
            for path, content in files
        ]
        
        results = await asyncio.gather(*tasks)
        
        return {
            files[i][0]: results[i]
            for i in range(len(files))
        }
    
    def get_summary(self, reports: Dict[str, VerificationReport]) -> Dict[str, Any]:
        """获取验证摘要"""
        total_files = len(reports)
        passed_files = sum(1 for r in reports.values() if r.passed)
        
        issues_by_level = {}
        issues_by_severity = {}
        
        for report in reports.values():
            for result in report.results.values():
                level = result.level.value
                issues_by_level[level] = issues_by_level.get(level, 0) + len(result.issues)
                
                for issue in result.issues:
                    severity = issue.severity.value
                    issues_by_severity[severity] = issues_by_severity.get(severity, 0) + 1
        
        return {
            "total_files": total_files,
            "passed_files": passed_files,
            "failed_files": total_files - passed_files,
            "pass_rate": passed_files / total_files if total_files > 0 else 1.0,
            "issues_by_level": issues_by_level,
            "issues_by_severity": issues_by_severity,
        }
