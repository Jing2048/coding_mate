"""
契约验证器

验证代码是否符合接口契约定义。
"""

import re
from typing import List, Optional, Dict, Any

from .verifier import VerificationResult, VerificationIssue, VerificationLevel, Severity


class ContractValidator:
    """
    契约验证器
    
    验证代码实现是否符合接口契约（前置条件、后置条件、不变量）。
    """
    
    def __init__(self, interface_registry: Optional[Any] = None):
        """
        初始化验证器
        
        Args:
            interface_registry: 接口注册表
        """
        self._interface_registry = interface_registry
    
    async def validate(
        self,
        file_path: str,
        content: str,
        interface_name: Optional[str] = None
    ) -> VerificationResult:
        """
        验证契约
        
        Args:
            file_path: 文件路径
            content: 文件内容
            interface_name: 接口名称（可选）
            
        Returns:
            VerificationResult: 验证结果
        """
        issues = []
        
        # 从代码中提取契约注释
        code_contracts = self._extract_contracts_from_code(content, file_path)
        
        # 验证契约完整性
        issues.extend(self._validate_contract_completeness(code_contracts, file_path))
        
        # 如果有接口注册表，与接口定义对比
        if self._interface_registry and interface_name:
            issues.extend(
                self._validate_against_interface(
                    code_contracts,
                    interface_name,
                    file_path
                )
            )
        
        # 检查契约实现
        issues.extend(self._check_contract_implementation(content, code_contracts, file_path))
        
        return VerificationResult(
            passed=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            level=VerificationLevel.L2_CONTRACT,
            issues=issues,
            metrics={
                "contracts_found": len(code_contracts),
                "preconditions": sum(len(c.get("preconditions", [])) for c in code_contracts),
                "postconditions": sum(len(c.get("postconditions", [])) for c in code_contracts),
            },
        )
    
    def _extract_contracts_from_code(
        self,
        content: str,
        file_path: str
    ) -> List[Dict[str, Any]]:
        """从代码中提取契约注释"""
        contracts = []
        
        # 匹配函数/方法定义和其 docstring
        func_pattern = r'def\s+(\w+)\s*\([^)]*\)[^:]*:\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')?'
        
        for match in re.finditer(func_pattern, content, re.DOTALL):
            func_name = match.group(1)
            docstring = match.group(2) or match.group(3) or ""
            
            contract = {
                "name": func_name,
                "preconditions": [],
                "postconditions": [],
                "invariants": [],
                "throws": [],
            }
            
            # 提取 @precondition
            for pre_match in re.finditer(r"@precondition\s+(.+)", docstring, re.IGNORECASE):
                contract["preconditions"].append(pre_match.group(1).strip())
            
            # 提取 @postcondition
            for post_match in re.finditer(r"@postcondition\s+(.+)", docstring, re.IGNORECASE):
                contract["postconditions"].append(post_match.group(1).strip())
            
            # 提取 @invariant
            for inv_match in re.finditer(r"@invariant\s+(.+)", docstring, re.IGNORECASE):
                contract["invariants"].append(inv_match.group(1).strip())
            
            # 提取 @throws
            for throws_match in re.finditer(r"@throws\s+(\w+)\s+(?:if\s+)?(.+)", docstring, re.IGNORECASE):
                contract["throws"].append({
                    "exception": throws_match.group(1),
                    "condition": throws_match.group(2).strip(),
                })
            
            contracts.append(contract)
        
        return contracts
    
    def _validate_contract_completeness(
        self,
        contracts: List[Dict[str, Any]],
        file_path: str
    ) -> List[VerificationIssue]:
        """验证契约完整性"""
        issues = []
        
        for contract in contracts:
            func_name = contract["name"]
            
            # 检查是否有至少一个前置条件或后置条件
            if (not contract["preconditions"] and 
                not contract["postconditions"] and
                not func_name.startswith("_")):  # 忽略私有方法
                issues.append(VerificationIssue(
                    level=VerificationLevel.L2_CONTRACT,
                    severity=Severity.INFO,
                    message=f"Function '{func_name}' has no contract annotations",
                    file_path=file_path,
                    suggestion="Consider adding @precondition, @postcondition, or @invariant",
                ))
        
        return issues
    
    def _validate_against_interface(
        self,
        code_contracts: List[Dict[str, Any]],
        interface_name: str,
        file_path: str
    ) -> List[VerificationIssue]:
        """与接口定义对比验证"""
        issues = []
        
        if not self._interface_registry:
            return issues
        
        interface = self._interface_registry.get(interface_name)
        if not interface:
            return issues
        
        # 创建代码契约索引
        code_contract_index = {c["name"]: c for c in code_contracts}
        
        # 检查接口中的每个方法
        for method in interface.methods:
            if method.name not in code_contract_index:
                continue
            
            code_contract = code_contract_index[method.name]
            
            if method.contract:
                # 检查前置条件
                interface_pres = {p.description for p in method.contract.preconditions}
                code_pres = set(code_contract["preconditions"])
                
                missing_pres = interface_pres - code_pres
                for pre in missing_pres:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.L2_CONTRACT,
                        severity=Severity.WARNING,
                        message=f"Method '{method.name}' missing precondition: {pre}",
                        file_path=file_path,
                    ))
                
                # 检查后置条件
                interface_posts = {p.description for p in method.contract.postconditions}
                code_posts = set(code_contract["postconditions"])
                
                missing_posts = interface_posts - code_posts
                for post in missing_posts:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.L2_CONTRACT,
                        severity=Severity.WARNING,
                        message=f"Method '{method.name}' missing postcondition: {post}",
                        file_path=file_path,
                    ))
        
        return issues
    
    def _check_contract_implementation(
        self,
        content: str,
        contracts: List[Dict[str, Any]],
        file_path: str
    ) -> List[VerificationIssue]:
        """检查契约是否在代码中实现"""
        issues = []
        
        for contract in contracts:
            func_name = contract["name"]
            
            # 获取函数体
            func_body = self._extract_function_body(content, func_name)
            if not func_body:
                continue
            
            # 检查前置条件是否有对应的验证代码
            for pre in contract["preconditions"]:
                if not self._has_validation_for(func_body, pre):
                    issues.append(VerificationIssue(
                        level=VerificationLevel.L2_CONTRACT,
                        severity=Severity.INFO,
                        message=f"Precondition may not be validated: {pre}",
                        file_path=file_path,
                        suggestion="Add validation code or assert statement",
                    ))
            
            # 检查异常是否被正确抛出
            for throws in contract["throws"]:
                exception_type = throws["exception"]
                if f"raise {exception_type}" not in func_body:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.L2_CONTRACT,
                        severity=Severity.WARNING,
                        message=f"Documented exception '{exception_type}' may not be raised",
                        file_path=file_path,
                    ))
        
        return issues
    
    def _extract_function_body(
        self,
        content: str,
        func_name: str
    ) -> Optional[str]:
        """提取函数体"""
        # 简化实现：找到函数定义后的缩进块
        lines = content.split("\n")
        in_function = False
        func_indent = 0
        body_lines = []
        
        for line in lines:
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            
            if stripped.startswith(f"def {func_name}("):
                in_function = True
                func_indent = current_indent
                continue
            
            if in_function:
                if stripped and current_indent <= func_indent:
                    break
                body_lines.append(line)
        
        return "\n".join(body_lines) if body_lines else None
    
    def _has_validation_for(self, func_body: str, condition: str) -> bool:
        """检查是否有验证代码"""
        # 简化实现：检查是否有 assert, if, raise 等关键字
        validation_keywords = ["assert", "if", "raise", "validate", "check"]
        
        # 提取条件中的关键词
        condition_words = re.findall(r'\b\w+\b', condition.lower())
        
        for keyword in validation_keywords:
            if keyword in func_body.lower():
                # 进一步检查是否与条件相关
                for word in condition_words:
                    if word in func_body.lower():
                        return True
        
        return False
