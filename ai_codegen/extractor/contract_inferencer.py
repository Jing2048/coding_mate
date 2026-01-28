"""
契约推断器

从代码推断接口契约（前置/后置条件、异常规范）。
"""

from typing import List, Optional
from ai_codegen.models import Contract, ThrowSpec
from ai_codegen.parser.tree_sitter_parser import CodeSymbol
import re


class ContractInferencer:
    """契约推断器"""
    
    def infer_contract(self, symbol: CodeSymbol, source_code: str) -> Contract:
        """
        推断方法契约
        
        Args:
            symbol: 代码符号
            source_code: 源代码
        
        Returns:
            Contract 对象
        """
        contract = Contract()
        
        start_line = symbol.location.start_line
        end_line = symbol.location.end_line
        lines = source_code.split('\n')
        
        if start_line > len(lines):
            return contract
        
        func_body = '\n'.join(lines[start_line-1:min(end_line, len(lines))])
        
        # 推断前置条件
        contract.preconditions = self._infer_preconditions(func_body, symbol)
        
        # 推断后置条件
        contract.postconditions = self._infer_postconditions(func_body, symbol)
        
        # 推断异常
        contract.throws = self._infer_throws(func_body, symbol)
        
        # 推断不变量（类方法）
        if symbol.node_type.value in ('method', 'class'):
            contract.invariants = self._infer_invariants(func_body, symbol)
        
        return contract
    
    def _infer_preconditions(self, func_body: str, symbol: CodeSymbol) -> List[str]:
        """推断前置条件"""
        preconditions = []
        
        # None 检查
        if re.search(r'if\s+\w+\s+is\s+None', func_body):
            preconditions.append("参数不能为 None")
        if re.search(r'if\s+\w+\s+is\s+not\s+None', func_body):
            preconditions.append("参数必须不为 None")
        
        # 类型检查
        if 'isinstance' in func_body:
            isinstance_matches = re.findall(r'isinstance\s*\(\s*(\w+)\s*,\s*(\w+)', func_body)
            for var, type_name in isinstance_matches:
                preconditions.append(f"{var} 必须是 {type_name} 类型")
        
        # 范围检查
        range_checks = re.findall(r'if\s+(\w+)\s*([<>=]+)\s*(\d+)', func_body)
        for var, op, val in range_checks:
            if op == '<':
                preconditions.append(f"{var} < {val}")
            elif op == '>':
                preconditions.append(f"{var} > {val}")
            elif op in ('<=', '=<'):
                preconditions.append(f"{var} <= {val}")
            elif op in ('>=', '=>'):
                preconditions.append(f"{var} >= {val}")
        
        # 空值检查
        if re.search(r'if\s+not\s+\w+', func_body) or re.search(r'if\s+len\s*\(\s*\w+\s*\)\s*==\s*0', func_body):
            preconditions.append("参数不能为空")
        
        return preconditions
    
    def _infer_postconditions(self, func_body: str, symbol: CodeSymbol) -> List[str]:
        """推断后置条件"""
        postconditions = []
        
        # 返回值检查
        if 'return' in func_body:
            if 'return None' not in func_body and 'return' in func_body:
                # 检查是否有多个 return 语句
                return_count = func_body.count('return')
                if return_count == 1:
                    postconditions.append("返回值不为 None")
                elif return_count > 1:
                    # 可能有条件返回 None
                    if 'return None' in func_body:
                        postconditions.append("可能返回 None 或有效值")
                    else:
                        postconditions.append("返回值不为 None")
        
        # 状态变化（简单推断）
        if 'self.' in func_body and '=' in func_body:
            postconditions.append("对象状态可能发生变化")
        
        return postconditions
    
    def _infer_throws(self, func_body: str, symbol: CodeSymbol) -> List[ThrowSpec]:
        """推断异常规范"""
        throws = []
        
        if 'raise' in func_body:
            # 提取 raise 语句
            raise_patterns = [
                r'raise\s+(\w+)',
                r'raise\s+(\w+)\s*\(',
                r'raise\s+(\w+)\s*\([^)]*\)',
            ]
            
            for pattern in raise_patterns:
                matches = re.findall(pattern, func_body)
                for exc in matches:
                    # 过滤掉常见的异常类型
                    if exc not in ('Exception', 'Error', 'BaseException'):
                        throws.append(ThrowSpec(
                            exception_type=exc,
                            condition="当条件不满足时"
                        ))
        
        return throws
    
    def _infer_invariants(self, func_body: str, symbol: CodeSymbol) -> List[str]:
        """推断不变量"""
        invariants = []
        
        # 从文档字符串提取
        if symbol.docstring:
            if 'invariant' in symbol.docstring.lower():
                # 简单提取不变量描述
                invariant_matches = re.findall(r'invariant[:\s]+([^\n]+)', symbol.docstring, re.IGNORECASE)
                invariants.extend(invariant_matches)
        
        return invariants
