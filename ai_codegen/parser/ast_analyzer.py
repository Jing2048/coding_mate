"""
AST 分析器

提供高级的 AST 分析功能，包括代码结构分析、复杂度计算等。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
import re

from .tree_sitter_parser import ParseResult, CodeSymbol, NodeType


@dataclass
class FunctionMetrics:
    """函数度量"""
    name: str
    lines_of_code: int
    cyclomatic_complexity: int
    parameters_count: int
    return_statements: int
    nested_depth: int
    cognitive_complexity: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "lines_of_code": self.lines_of_code,
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "parameters_count": self.parameters_count,
            "return_statements": self.return_statements,
            "nested_depth": self.nested_depth,
            "cognitive_complexity": self.cognitive_complexity,
        }


@dataclass
class ClassMetrics:
    """类度量"""
    name: str
    lines_of_code: int
    methods_count: int
    attributes_count: int
    inheritance_depth: int
    coupling: int  # 依赖的类数量
    cohesion: float  # 内聚度 (0-1)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "lines_of_code": self.lines_of_code,
            "methods_count": self.methods_count,
            "attributes_count": self.attributes_count,
            "inheritance_depth": self.inheritance_depth,
            "coupling": self.coupling,
            "cohesion": self.cohesion,
        }


@dataclass
class ModuleMetrics:
    """模块度量"""
    path: str
    lines_of_code: int
    lines_of_comments: int
    blank_lines: int
    classes_count: int
    functions_count: int
    imports_count: int
    average_function_complexity: float
    max_function_complexity: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "lines_of_code": self.lines_of_code,
            "lines_of_comments": self.lines_of_comments,
            "blank_lines": self.blank_lines,
            "classes_count": self.classes_count,
            "functions_count": self.functions_count,
            "imports_count": self.imports_count,
            "average_function_complexity": self.average_function_complexity,
            "max_function_complexity": self.max_function_complexity,
        }


class ASTAnalyzer:
    """
    AST 分析器
    
    提供代码结构分析、度量计算、模式识别等功能。
    """
    
    def __init__(self):
        self._complexity_keywords = {
            "python": ["if", "elif", "for", "while", "except", "with", "and", "or"],
            "javascript": ["if", "else if", "for", "while", "catch", "case", "&&", "||", "?"],
            "typescript": ["if", "else if", "for", "while", "catch", "case", "&&", "||", "?"],
        }
    
    def analyze_module(
        self,
        source_code: str,
        parse_result: ParseResult
    ) -> ModuleMetrics:
        """
        分析模块度量
        
        Args:
            source_code: 源代码
            parse_result: 解析结果
            
        Returns:
            ModuleMetrics: 模块度量
        """
        lines = source_code.split("\n")
        
        lines_of_code = 0
        lines_of_comments = 0
        blank_lines = 0
        
        in_multiline_comment = False
        
        for line in lines:
            stripped = line.strip()
            
            if not stripped:
                blank_lines += 1
                continue
            
            # 检查多行注释
            if parse_result.language == "python":
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    if in_multiline_comment:
                        in_multiline_comment = False
                        lines_of_comments += 1
                    elif stripped.count('"""') == 2 or stripped.count("'''") == 2:
                        lines_of_comments += 1
                    else:
                        in_multiline_comment = True
                        lines_of_comments += 1
                    continue
                    
                if in_multiline_comment:
                    lines_of_comments += 1
                    continue
                    
                if stripped.startswith("#"):
                    lines_of_comments += 1
                else:
                    lines_of_code += 1
            else:
                # JavaScript/TypeScript
                if stripped.startswith("/*"):
                    in_multiline_comment = True
                    lines_of_comments += 1
                    if "*/" in stripped:
                        in_multiline_comment = False
                    continue
                    
                if in_multiline_comment:
                    lines_of_comments += 1
                    if "*/" in stripped:
                        in_multiline_comment = False
                    continue
                    
                if stripped.startswith("//"):
                    lines_of_comments += 1
                else:
                    lines_of_code += 1
        
        # 统计符号
        classes_count = sum(
            1 for s in parse_result.symbols 
            if s.node_type == NodeType.CLASS
        )
        functions_count = sum(
            1 for s in parse_result.symbols 
            if s.node_type in (NodeType.FUNCTION, NodeType.METHOD)
        )
        
        # 计算复杂度
        function_complexities = []
        for symbol in parse_result.symbols:
            if symbol.node_type in (NodeType.FUNCTION, NodeType.METHOD):
                complexity = self._estimate_complexity(
                    source_code, 
                    symbol, 
                    parse_result.language
                )
                function_complexities.append(complexity)
        
        avg_complexity = (
            sum(function_complexities) / len(function_complexities)
            if function_complexities else 0
        )
        max_complexity = max(function_complexities) if function_complexities else 0
        
        return ModuleMetrics(
            path=parse_result.file_path,
            lines_of_code=lines_of_code,
            lines_of_comments=lines_of_comments,
            blank_lines=blank_lines,
            classes_count=classes_count,
            functions_count=functions_count,
            imports_count=len(parse_result.imports),
            average_function_complexity=round(avg_complexity, 2),
            max_function_complexity=max_complexity,
        )
    
    def analyze_function(
        self,
        source_code: str,
        symbol: CodeSymbol,
        language: str
    ) -> FunctionMetrics:
        """
        分析函数度量
        
        Args:
            source_code: 源代码
            symbol: 函数符号
            language: 编程语言
            
        Returns:
            FunctionMetrics: 函数度量
        """
        lines = source_code.split("\n")
        
        # 获取函数代码
        start_line = symbol.location.start_line - 1
        end_line = symbol.location.end_line
        func_lines = lines[start_line:end_line]
        func_code = "\n".join(func_lines)
        
        # 计算行数
        loc = len([l for l in func_lines if l.strip()])
        
        # 计算复杂度
        complexity = self._estimate_complexity(source_code, symbol, language)
        
        # 计算参数数量
        params = self._count_parameters(symbol.signature, language)
        
        # 计算返回语句数量
        returns = self._count_returns(func_code, language)
        
        # 计算嵌套深度
        nested = self._calculate_nesting(func_code, language)
        
        return FunctionMetrics(
            name=symbol.name,
            lines_of_code=loc,
            cyclomatic_complexity=complexity,
            parameters_count=params,
            return_statements=returns,
            nested_depth=nested,
        )
    
    def _estimate_complexity(
        self,
        source_code: str,
        symbol: CodeSymbol,
        language: str
    ) -> int:
        """估算圈复杂度"""
        lines = source_code.split("\n")
        start_line = symbol.location.start_line - 1
        end_line = symbol.location.end_line
        func_code = "\n".join(lines[start_line:end_line])
        
        complexity = 1  # 基础复杂度
        
        keywords = self._complexity_keywords.get(language, [])
        
        for keyword in keywords:
            # 使用正则匹配关键字（避免匹配变量名中的子串）
            pattern = rf'\b{re.escape(keyword)}\b'
            matches = re.findall(pattern, func_code)
            complexity += len(matches)
        
        return complexity
    
    def _count_parameters(self, signature: str, language: str) -> int:
        """计算参数数量"""
        if not signature:
            return 0
            
        # 提取括号内容
        match = re.search(r'\(([^)]*)\)', signature)
        if not match:
            return 0
            
        params_str = match.group(1).strip()
        if not params_str:
            return 0
        
        # 分割参数
        params = []
        depth = 0
        current = ""
        
        for char in params_str:
            if char in "([{<":
                depth += 1
            elif char in ")]}>":
                depth -= 1
            elif char == "," and depth == 0:
                if current.strip():
                    params.append(current.strip())
                current = ""
                continue
            current += char
        
        if current.strip():
            params.append(current.strip())
        
        # 过滤 self/this
        params = [p for p in params if p not in ("self", "this", "cls")]
        
        return len(params)
    
    def _count_returns(self, code: str, language: str) -> int:
        """计算返回语句数量"""
        pattern = r'\breturn\b'
        return len(re.findall(pattern, code))
    
    def _calculate_nesting(self, code: str, language: str) -> int:
        """计算最大嵌套深度"""
        max_depth = 0
        current_depth = 0
        
        lines = code.split("\n")
        
        if language == "python":
            base_indent = None
            for line in lines:
                stripped = line.lstrip()
                if not stripped:
                    continue
                    
                indent = len(line) - len(stripped)
                
                if base_indent is None:
                    base_indent = indent
                    
                # 计算相对于基础缩进的深度
                relative_indent = max(0, indent - base_indent)
                depth = relative_indent // 4  # 假设 4 空格缩进
                
                max_depth = max(max_depth, depth)
        else:
            for char in code:
                if char == "{":
                    current_depth += 1
                    max_depth = max(max_depth, current_depth)
                elif char == "}":
                    current_depth = max(0, current_depth - 1)
        
        return max_depth
    
    def find_code_smells(
        self,
        parse_result: ParseResult,
        source_code: str
    ) -> List[Dict[str, Any]]:
        """
        检测代码异味
        
        Args:
            parse_result: 解析结果
            source_code: 源代码
            
        Returns:
            List[Dict]: 代码异味列表
        """
        smells = []
        
        for symbol in parse_result.symbols:
            if symbol.node_type in (NodeType.FUNCTION, NodeType.METHOD):
                metrics = self.analyze_function(
                    source_code, 
                    symbol, 
                    parse_result.language
                )
                
                # 检查长函数
                if metrics.lines_of_code > 50:
                    smells.append({
                        "type": "long_function",
                        "symbol": symbol.name,
                        "location": symbol.location.to_dict(),
                        "message": f"Function is too long ({metrics.lines_of_code} lines)",
                        "severity": "warning",
                    })
                
                # 检查高复杂度
                if metrics.cyclomatic_complexity > 10:
                    smells.append({
                        "type": "high_complexity",
                        "symbol": symbol.name,
                        "location": symbol.location.to_dict(),
                        "message": f"Function has high complexity ({metrics.cyclomatic_complexity})",
                        "severity": "warning",
                    })
                
                # 检查参数过多
                if metrics.parameters_count > 5:
                    smells.append({
                        "type": "too_many_parameters",
                        "symbol": symbol.name,
                        "location": symbol.location.to_dict(),
                        "message": f"Function has too many parameters ({metrics.parameters_count})",
                        "severity": "info",
                    })
                
                # 检查嵌套过深
                if metrics.nested_depth > 4:
                    smells.append({
                        "type": "deep_nesting",
                        "symbol": symbol.name,
                        "location": symbol.location.to_dict(),
                        "message": f"Function has deep nesting ({metrics.nested_depth} levels)",
                        "severity": "warning",
                    })
        
        return smells
    
    def get_code_structure(
        self,
        parse_result: ParseResult
    ) -> Dict[str, Any]:
        """
        获取代码结构摘要
        
        Args:
            parse_result: 解析结果
            
        Returns:
            Dict: 代码结构
        """
        classes = []
        functions = []
        
        for symbol in parse_result.symbols:
            if symbol.node_type == NodeType.CLASS:
                # 收集类的方法
                methods = [
                    s.name for s in parse_result.symbols
                    if s.parent == symbol.name and s.node_type == NodeType.METHOD
                ]
                
                classes.append({
                    "name": symbol.name,
                    "signature": symbol.signature,
                    "docstring": symbol.docstring,
                    "methods": methods,
                    "location": symbol.location.to_dict(),
                })
                
            elif symbol.node_type == NodeType.FUNCTION:
                functions.append({
                    "name": symbol.name,
                    "signature": symbol.signature,
                    "docstring": symbol.docstring,
                    "location": symbol.location.to_dict(),
                })
        
        return {
            "file": parse_result.file_path,
            "language": parse_result.language,
            "classes": classes,
            "functions": functions,
            "imports": parse_result.imports,
            "exports": parse_result.exports,
        }
