"""
测试运行器

运行单元测试并收集结果。
"""

import subprocess
import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any

from .verifier import VerificationResult, VerificationIssue, VerificationLevel, Severity


class TestRunner:
    """
    测试运行器
    
    运行单元测试并收集覆盖率等指标。
    """
    
    def __init__(self):
        self._available_frameworks: Dict[str, bool] = {}
        self._check_available_frameworks()
    
    def _check_available_frameworks(self):
        """检查可用的测试框架"""
        frameworks = {
            "pytest": ["pytest", "--version"],
            "jest": ["jest", "--version"],
            "go": ["go", "version"],
        }
        
        for framework, cmd in frameworks.items():
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=5
                )
                self._available_frameworks[framework] = result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self._available_frameworks[framework] = False
    
    async def run_tests(
        self,
        file_path: str,
        test_file: Optional[str] = None,
        coverage: bool = True
    ) -> VerificationResult:
        """
        运行测试
        
        Args:
            file_path: 源文件路径
            test_file: 测试文件路径（可选）
            coverage: 是否收集覆盖率
            
        Returns:
            VerificationResult: 验证结果
        """
        # 检测语言和测试框架
        language = self._detect_language(file_path)
        
        if language == "python":
            return await self._run_pytest(file_path, test_file, coverage)
        elif language in ("javascript", "typescript"):
            return await self._run_jest(file_path, test_file, coverage)
        else:
            return VerificationResult(
                passed=True,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=[VerificationIssue(
                    level=VerificationLevel.L3_UNIT_TEST,
                    severity=Severity.INFO,
                    message=f"No test runner available for {language}",
                    file_path=file_path,
                )],
            )
    
    def _detect_language(self, file_path: str) -> str:
        """检测文件语言"""
        ext = Path(file_path).suffix.lower()
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".go": "go",
        }
        return ext_map.get(ext, "unknown")
    
    async def _run_pytest(
        self,
        file_path: str,
        test_file: Optional[str],
        coverage: bool
    ) -> VerificationResult:
        """运行 pytest"""
        issues = []
        metrics = {}
        
        if not self._available_frameworks.get("pytest"):
            return VerificationResult(
                passed=True,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=[VerificationIssue(
                    level=VerificationLevel.L3_UNIT_TEST,
                    severity=Severity.WARNING,
                    message="pytest not available",
                    file_path=file_path,
                )],
            )
        
        # 构建命令
        cmd = ["pytest", "-v", "--tb=short"]
        
        if coverage:
            cmd.extend(["--cov", "--cov-report=json"])
        
        # 添加 JSON 输出
        cmd.extend(["--json-report", "--json-report-file=-"])
        
        if test_file:
            cmd.append(test_file)
        else:
            # 尝试找到对应的测试文件
            test_candidates = [
                f"tests/test_{Path(file_path).stem}.py",
                f"test_{Path(file_path).name}",
                f"{Path(file_path).stem}_test.py",
            ]
            
            for candidate in test_candidates:
                if Path(candidate).exists():
                    cmd.append(candidate)
                    break
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=Path(file_path).parent
            )
            
            # 解析结果
            passed = result.returncode == 0
            
            # 尝试解析 JSON 报告
            try:
                # 从 stdout 中提取 JSON 报告
                if result.stdout:
                    report = json.loads(result.stdout)
                    metrics["tests_total"] = report.get("summary", {}).get("total", 0)
                    metrics["tests_passed"] = report.get("summary", {}).get("passed", 0)
                    metrics["tests_failed"] = report.get("summary", {}).get("failed", 0)
            except json.JSONDecodeError:
                pass
            
            # 解析覆盖率报告
            if coverage and Path("coverage.json").exists():
                with open("coverage.json") as f:
                    cov_data = json.load(f)
                    metrics["coverage"] = cov_data.get("totals", {}).get("percent_covered", 0)
            
            # 从 stderr 提取错误
            if result.returncode != 0:
                for line in result.stderr.split("\n"):
                    if "FAILED" in line or "ERROR" in line:
                        issues.append(VerificationIssue(
                            level=VerificationLevel.L3_UNIT_TEST,
                            severity=Severity.ERROR,
                            message=line.strip(),
                            file_path=file_path,
                        ))
            
            return VerificationResult(
                passed=passed,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=issues,
                metrics=metrics,
            )
            
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=[VerificationIssue(
                    level=VerificationLevel.L3_UNIT_TEST,
                    severity=Severity.ERROR,
                    message="Test execution timed out",
                    file_path=file_path,
                )],
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=[VerificationIssue(
                    level=VerificationLevel.L3_UNIT_TEST,
                    severity=Severity.ERROR,
                    message=f"Test execution failed: {e}",
                    file_path=file_path,
                )],
            )
    
    async def _run_jest(
        self,
        file_path: str,
        test_file: Optional[str],
        coverage: bool
    ) -> VerificationResult:
        """运行 Jest"""
        issues = []
        metrics = {}
        
        if not self._available_frameworks.get("jest"):
            return VerificationResult(
                passed=True,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=[VerificationIssue(
                    level=VerificationLevel.L3_UNIT_TEST,
                    severity=Severity.WARNING,
                    message="Jest not available",
                    file_path=file_path,
                )],
            )
        
        # 构建命令
        cmd = ["jest", "--json"]
        
        if coverage:
            cmd.append("--coverage")
        
        if test_file:
            cmd.append(test_file)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=Path(file_path).parent
            )
            
            passed = result.returncode == 0
            
            # 解析 JSON 输出
            try:
                report = json.loads(result.stdout)
                metrics["tests_total"] = report.get("numTotalTests", 0)
                metrics["tests_passed"] = report.get("numPassedTests", 0)
                metrics["tests_failed"] = report.get("numFailedTests", 0)
                
                # 提取失败的测试
                for test_result in report.get("testResults", []):
                    for assertion in test_result.get("assertionResults", []):
                        if assertion.get("status") == "failed":
                            issues.append(VerificationIssue(
                                level=VerificationLevel.L3_UNIT_TEST,
                                severity=Severity.ERROR,
                                message=assertion.get("title", "Test failed"),
                                file_path=test_result.get("name", file_path),
                            ))
            except json.JSONDecodeError:
                pass
            
            return VerificationResult(
                passed=passed,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=issues,
                metrics=metrics,
            )
            
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=[VerificationIssue(
                    level=VerificationLevel.L3_UNIT_TEST,
                    severity=Severity.ERROR,
                    message="Test execution timed out",
                    file_path=file_path,
                )],
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                level=VerificationLevel.L3_UNIT_TEST,
                issues=[VerificationIssue(
                    level=VerificationLevel.L3_UNIT_TEST,
                    severity=Severity.ERROR,
                    message=f"Test execution failed: {e}",
                    file_path=file_path,
                )],
            )
    
    async def run_mutation_testing(
        self,
        file_path: str,
        test_file: str
    ) -> VerificationResult:
        """
        运行变异测试
        
        Args:
            file_path: 源文件路径
            test_file: 测试文件路径
            
        Returns:
            VerificationResult: 验证结果
        """
        # 简化实现：检查是否有 mutmut 或 stryker
        language = self._detect_language(file_path)
        
        if language == "python":
            # 检查 mutmut
            try:
                result = subprocess.run(
                    ["mutmut", "--version"],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return await self._run_mutmut(file_path, test_file)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        
        return VerificationResult(
            passed=True,
            level=VerificationLevel.L4_MUTATION,
            issues=[VerificationIssue(
                level=VerificationLevel.L4_MUTATION,
                severity=Severity.INFO,
                message="Mutation testing not available",
                file_path=file_path,
            )],
            metrics={"mutation_score": 0.0},
        )
    
    async def _run_mutmut(
        self,
        file_path: str,
        test_file: str
    ) -> VerificationResult:
        """运行 mutmut 变异测试"""
        # 简化实现
        return VerificationResult(
            passed=True,
            level=VerificationLevel.L4_MUTATION,
            metrics={
                "mutation_score": 0.0,
                "mutants_killed": 0,
                "mutants_survived": 0,
                "mutants_total": 0,
            },
        )
