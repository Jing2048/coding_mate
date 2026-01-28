"""
类型检查器

执行静态类型检查。
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Optional

from .verifier import VerificationResult, VerificationIssue, VerificationLevel, Severity


class TypeChecker:
    """
    类型检查器
    
    使用语言特定的类型检查工具（如 mypy, tsc）检查类型错误。
    """
    
    def __init__(self):
        self._available_tools: dict = {}
        self._check_available_tools()
    
    def _check_available_tools(self):
        """检查可用的类型检查工具"""
        tools = {
            "mypy": ["mypy", "--version"],
            "tsc": ["tsc", "--version"],
            "pyright": ["pyright", "--version"],
            "swiftc": ["swiftc", "--version"],
        }
        
        for tool, cmd in tools.items():
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self._available_tools[tool] = True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self._available_tools[tool] = False
    
    async def check(
        self,
        file_path: str,
        content: str,
        language: str = "python"
    ) -> VerificationResult:
        """
        执行类型检查
        
        Args:
            file_path: 文件路径
            content: 文件内容
            language: 编程语言
            
        Returns:
            VerificationResult: 验证结果
        """
        if language == "python":
            return await self._check_python(file_path, content)
        elif language in ("typescript", "javascript"):
            return await self._check_typescript(file_path, content)
        elif language == "swift":
            return await self._check_swift(file_path, content)
        else:
            return VerificationResult(
                passed=True,
                level=VerificationLevel.L1_TYPE,
                issues=[],
            )
    
    async def _check_python(
        self,
        file_path: str,
        content: str
    ) -> VerificationResult:
        """检查 Python 类型"""
        issues = []
        
        # 尝试使用 mypy
        if self._available_tools.get("mypy"):
            issues = await self._run_mypy(file_path, content)
        else:
            # 基本的类型提示检查
            issues = self._basic_python_type_check(content, file_path)
        
        return VerificationResult(
            passed=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            level=VerificationLevel.L1_TYPE,
            issues=issues,
        )
    
    async def _run_mypy(
        self,
        file_path: str,
        content: str
    ) -> List[VerificationIssue]:
        """运行 mypy"""
        issues = []
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False
        ) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                ["mypy", "--no-error-summary", temp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # 解析 mypy 输出
            for line in result.stdout.split("\n"):
                if not line.strip():
                    continue
                
                # 格式: file.py:line: level: message
                parts = line.split(":", 3)
                if len(parts) >= 4:
                    try:
                        line_num = int(parts[1])
                        level = parts[2].strip()
                        message = parts[3].strip()
                        
                        severity = Severity.ERROR if "error" in level else Severity.WARNING
                        
                        issues.append(VerificationIssue(
                            level=VerificationLevel.L1_TYPE,
                            severity=severity,
                            message=message,
                            file_path=file_path,
                            line=line_num,
                            rule="mypy",
                        ))
                    except ValueError:
                        pass
        
        except subprocess.TimeoutExpired:
            issues.append(VerificationIssue(
                level=VerificationLevel.L1_TYPE,
                severity=Severity.WARNING,
                message="Type checking timed out",
                file_path=file_path,
            ))
        finally:
            os.unlink(temp_path)
        
        return issues
    
    def _basic_python_type_check(
        self,
        content: str,
        file_path: str
    ) -> List[VerificationIssue]:
        """基本的 Python 类型检查"""
        issues = []
        lines = content.split("\n")
        
        for i, line in enumerate(lines, 1):
            # 检查函数定义是否有类型提示
            if line.strip().startswith("def "):
                if "->" not in line and ":" in line:
                    # 函数没有返回类型提示
                    issues.append(VerificationIssue(
                        level=VerificationLevel.L1_TYPE,
                        severity=Severity.INFO,
                        message="Function missing return type hint",
                        file_path=file_path,
                        line=i,
                        suggestion="Add return type annotation: def func(...) -> ReturnType:",
                    ))
        
        return issues
    
    async def _check_typescript(
        self,
        file_path: str,
        content: str
    ) -> VerificationResult:
        """检查 TypeScript 类型"""
        issues = []
        
        if self._available_tools.get("tsc"):
            issues = await self._run_tsc(file_path, content)
        
        return VerificationResult(
            passed=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            level=VerificationLevel.L1_TYPE,
            issues=issues,
        )
    
    async def _run_tsc(
        self,
        file_path: str,
        content: str
    ) -> List[VerificationIssue]:
        """运行 TypeScript 编译器"""
        issues = []
        
        # 创建临时文件
        suffix = ".ts" if "interface" in content or "type" in content else ".js"
        
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False
        ) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                ["tsc", "--noEmit", "--strict", temp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            for line in result.stdout.split("\n"):
                if not line.strip():
                    continue
                
                # 解析 tsc 输出
                if "error TS" in line:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.L1_TYPE,
                        severity=Severity.ERROR,
                        message=line,
                        file_path=file_path,
                        rule="tsc",
                    ))
        
        except subprocess.TimeoutExpired:
            pass
        finally:
            os.unlink(temp_path)
        
        return issues
    
    async def _check_swift(
        self,
        file_path: str,
        content: str
    ) -> VerificationResult:
        """检查 Swift 类型"""
        issues = []
        
        if self._available_tools.get("swiftc"):
            issues = await self._run_swiftc(file_path, content)
        else:
            # 基本的 Swift 类型检查（检查常见错误）
            issues = self._basic_swift_type_check(content, file_path)
        
        return VerificationResult(
            passed=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            level=VerificationLevel.L1_TYPE,
            issues=issues,
        )
    
    async def _run_swiftc(
        self,
        file_path: str,
        content: str
    ) -> List[VerificationIssue]:
        """运行 Swift 编译器进行类型检查"""
        issues = []
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".swift",
            delete=False
        ) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            # swiftc -typecheck 只进行类型检查，不生成代码
            result = subprocess.run(
                ["swiftc", "-typecheck", temp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # 解析 swiftc 输出
            for line in result.stderr.split("\n"):
                if not line.strip():
                    continue
                
                # Swift 错误格式: file.swift:line:column: error: message
                if "error:" in line or "warning:" in line:
                    parts = line.split(":", 4)
                    if len(parts) >= 5:
                        try:
                            line_num = int(parts[1]) if parts[1].strip().isdigit() else None
                            col_num = int(parts[2]) if parts[2].strip().isdigit() else None
                            level = parts[3].strip()
                            message = parts[4].strip()
                            
                            severity = Severity.ERROR if "error" in level else Severity.WARNING
                            
                            issues.append(VerificationIssue(
                                level=VerificationLevel.L1_TYPE,
                                severity=severity,
                                message=message,
                                file_path=file_path,
                                line=line_num,
                                column=col_num,
                                rule="swiftc",
                            ))
                        except (ValueError, IndexError):
                            # 如果解析失败，仍然添加问题
                            issues.append(VerificationIssue(
                                level=VerificationLevel.L1_TYPE,
                                severity=Severity.WARNING,
                                message=line.strip(),
                                file_path=file_path,
                                rule="swiftc",
                            ))
        
        except subprocess.TimeoutExpired:
            issues.append(VerificationIssue(
                level=VerificationLevel.L1_TYPE,
                severity=Severity.WARNING,
                message="Swift type checking timed out",
                file_path=file_path,
            ))
        finally:
            os.unlink(temp_path)
        
        return issues
    
    def _basic_swift_type_check(
        self,
        content: str,
        file_path: str
    ) -> List[VerificationIssue]:
        """基本的 Swift 类型检查"""
        issues = []
        lines = content.split("\n")
        
        for i, line in enumerate(lines, 1):
            # 检查函数定义是否有返回类型
            if "func " in line and "->" not in line and "{" in line:
                # 函数没有显式返回类型（可能是 Void）
                # 检查是否是 Void 返回
                if not line.strip().endswith("{"):
                    issues.append(VerificationIssue(
                        level=VerificationLevel.L1_TYPE,
                        severity=Severity.INFO,
                        message="Function missing explicit return type",
                        file_path=file_path,
                        line=i,
                        suggestion="Add return type annotation: func name() -> ReturnType",
                    ))
        
        return issues
