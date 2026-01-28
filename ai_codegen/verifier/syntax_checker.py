"""
语法检查器

使用 Tree-sitter 检查代码语法正确性。
"""

from typing import List, Optional
from .verifier import VerificationResult, VerificationIssue, VerificationLevel, Severity


class SyntaxChecker:
    """
    语法检查器
    
    使用 Tree-sitter 检查代码是否有语法错误。
    """
    
    def __init__(self):
        self._parser = None
    
    async def check(
        self,
        file_path: str,
        content: str,
        language: str = "python"
    ) -> VerificationResult:
        """
        检查语法
        
        Args:
            file_path: 文件路径
            content: 文件内容
            language: 编程语言
            
        Returns:
            VerificationResult: 验证结果
        """
        issues = []
        
        # 尝试使用 tree-sitter
        try:
            from ..parser.tree_sitter_parser import TreeSitterParser
            
            parser = TreeSitterParser(languages=[language])
            result = parser.parse_source(content, file_path, language)
            
            if result.errors:
                for error in result.errors:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.L0_SYNTAX,
                        severity=Severity.ERROR,
                        message=error,
                        file_path=file_path,
                    ))
            
        except ImportError:
            # 回退到基本检查
            issues.extend(self._basic_syntax_check(file_path, content, language))
        
        return VerificationResult(
            passed=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            level=VerificationLevel.L0_SYNTAX,
            issues=issues,
        )
    
    def _basic_syntax_check(
        self,
        file_path: str,
        content: str,
        language: str
    ) -> List[VerificationIssue]:
        """基本语法检查"""
        issues = []
        
        if language == "python":
            try:
                compile(content, file_path, "exec")
            except SyntaxError as e:
                issues.append(VerificationIssue(
                    level=VerificationLevel.L0_SYNTAX,
                    severity=Severity.ERROR,
                    message=str(e.msg) if e.msg else str(e),
                    file_path=file_path,
                    line=e.lineno,
                    column=e.offset,
                ))
        
        elif language in ("javascript", "typescript"):
            # 基本的括号匹配检查
            issues.extend(self._check_bracket_matching(file_path, content))
        
        elif language == "swift":
            # Swift 基本的括号匹配检查
            issues.extend(self._check_bracket_matching(file_path, content))
        
        return issues
    
    def _check_bracket_matching(
        self,
        file_path: str,
        content: str
    ) -> List[VerificationIssue]:
        """检查括号匹配"""
        issues = []
        
        brackets = {"(": ")", "[": "]", "{": "}"}
        stack = []
        in_string = False
        string_char = None
        
        lines = content.split("\n")
        
        for line_num, line in enumerate(lines, 1):
            col = 0
            for char in line:
                col += 1
                
                # 处理字符串
                if char in ('"', "'", "`"):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                        string_char = None
                    continue
                
                if in_string:
                    continue
                
                # 处理括号
                if char in brackets:
                    stack.append((char, line_num, col))
                elif char in brackets.values():
                    if not stack:
                        issues.append(VerificationIssue(
                            level=VerificationLevel.L0_SYNTAX,
                            severity=Severity.ERROR,
                            message=f"Unmatched closing bracket '{char}'",
                            file_path=file_path,
                            line=line_num,
                            column=col,
                        ))
                    else:
                        opening, _, _ = stack.pop()
                        if brackets[opening] != char:
                            issues.append(VerificationIssue(
                                level=VerificationLevel.L0_SYNTAX,
                                severity=Severity.ERROR,
                                message=f"Mismatched brackets: '{opening}' and '{char}'",
                                file_path=file_path,
                                line=line_num,
                                column=col,
                            ))
        
        # 检查未闭合的括号
        for opening, line_num, col in stack:
            issues.append(VerificationIssue(
                level=VerificationLevel.L0_SYNTAX,
                severity=Severity.ERROR,
                message=f"Unclosed bracket '{opening}'",
                file_path=file_path,
                line=line_num,
                column=col,
            ))
        
        return issues
