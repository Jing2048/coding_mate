"""
契约定义

定义前置条件、后置条件、不变量等契约规范。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Union
from enum import Enum
import re


class ContractType(Enum):
    """契约类型"""
    PRECONDITION = "precondition"
    POSTCONDITION = "postcondition"
    INVARIANT = "invariant"
    THROWS = "throws"


@dataclass
class ContractViolation:
    """契约违反"""
    contract_type: ContractType
    description: str
    actual_value: Any = None
    expected: str = ""
    location: Optional[Dict[str, Any]] = None


@dataclass
class Precondition:
    """
    前置条件
    
    定义函数执行前必须满足的条件。
    """
    description: str
    check: Optional[Callable[..., bool]] = None
    expression: Optional[str] = None  # 可执行的表达式
    
    def validate(self, **kwargs) -> Optional[ContractViolation]:
        """验证前置条件"""
        if self.check:
            try:
                if not self.check(**kwargs):
                    return ContractViolation(
                        contract_type=ContractType.PRECONDITION,
                        description=self.description,
                        actual_value=kwargs,
                    )
            except Exception as e:
                return ContractViolation(
                    contract_type=ContractType.PRECONDITION,
                    description=f"Precondition check failed: {e}",
                )
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "precondition",
            "description": self.description,
            "expression": self.expression,
        }


@dataclass
class Postcondition:
    """
    后置条件
    
    定义函数执行后必须满足的条件。
    """
    description: str
    check: Optional[Callable[..., bool]] = None
    expression: Optional[str] = None
    
    def validate(self, result: Any, **kwargs) -> Optional[ContractViolation]:
        """验证后置条件"""
        if self.check:
            try:
                if not self.check(result, **kwargs):
                    return ContractViolation(
                        contract_type=ContractType.POSTCONDITION,
                        description=self.description,
                        actual_value=result,
                    )
            except Exception as e:
                return ContractViolation(
                    contract_type=ContractType.POSTCONDITION,
                    description=f"Postcondition check failed: {e}",
                )
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "postcondition",
            "description": self.description,
            "expression": self.expression,
        }


@dataclass
class Invariant:
    """
    不变量
    
    定义在任何时刻都必须满足的条件。
    """
    description: str
    check: Optional[Callable[..., bool]] = None
    expression: Optional[str] = None
    
    def validate(self, obj: Any) -> Optional[ContractViolation]:
        """验证不变量"""
        if self.check:
            try:
                if not self.check(obj):
                    return ContractViolation(
                        contract_type=ContractType.INVARIANT,
                        description=self.description,
                        actual_value=obj,
                    )
            except Exception as e:
                return ContractViolation(
                    contract_type=ContractType.INVARIANT,
                    description=f"Invariant check failed: {e}",
                )
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "invariant",
            "description": self.description,
            "expression": self.expression,
        }


@dataclass
class ThrowsSpec:
    """
    异常规范
    
    定义函数可能抛出的异常。
    """
    exception_type: str
    condition: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "throws",
            "exception_type": self.exception_type,
            "condition": self.condition,
        }


@dataclass
class Contract:
    """
    契约
    
    包含前置条件、后置条件、不变量和异常规范的完整契约定义。
    """
    name: str
    description: str = ""
    preconditions: List[Precondition] = field(default_factory=list)
    postconditions: List[Postcondition] = field(default_factory=list)
    invariants: List[Invariant] = field(default_factory=list)
    throws: List[ThrowsSpec] = field(default_factory=list)
    
    def add_precondition(
        self,
        description: str,
        check: Optional[Callable] = None,
        expression: Optional[str] = None
    ) -> "Contract":
        """添加前置条件"""
        self.preconditions.append(Precondition(
            description=description,
            check=check,
            expression=expression,
        ))
        return self
    
    def add_postcondition(
        self,
        description: str,
        check: Optional[Callable] = None,
        expression: Optional[str] = None
    ) -> "Contract":
        """添加后置条件"""
        self.postconditions.append(Postcondition(
            description=description,
            check=check,
            expression=expression,
        ))
        return self
    
    def add_invariant(
        self,
        description: str,
        check: Optional[Callable] = None,
        expression: Optional[str] = None
    ) -> "Contract":
        """添加不变量"""
        self.invariants.append(Invariant(
            description=description,
            check=check,
            expression=expression,
        ))
        return self
    
    def add_throws(self, exception_type: str, condition: str) -> "Contract":
        """添加异常规范"""
        self.throws.append(ThrowsSpec(
            exception_type=exception_type,
            condition=condition,
        ))
        return self
    
    def validate_preconditions(self, **kwargs) -> List[ContractViolation]:
        """验证所有前置条件"""
        violations = []
        for pre in self.preconditions:
            violation = pre.validate(**kwargs)
            if violation:
                violations.append(violation)
        return violations
    
    def validate_postconditions(self, result: Any, **kwargs) -> List[ContractViolation]:
        """验证所有后置条件"""
        violations = []
        for post in self.postconditions:
            violation = post.validate(result, **kwargs)
            if violation:
                violations.append(violation)
        return violations
    
    def validate_invariants(self, obj: Any) -> List[ContractViolation]:
        """验证所有不变量"""
        violations = []
        for inv in self.invariants:
            violation = inv.validate(obj)
            if violation:
                violations.append(violation)
        return violations
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "preconditions": [p.to_dict() for p in self.preconditions],
            "postconditions": [p.to_dict() for p in self.postconditions],
            "invariants": [i.to_dict() for i in self.invariants],
            "throws": [t.to_dict() for t in self.throws],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contract":
        """从字典创建契约"""
        contract = cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
        )
        
        for pre_data in data.get("preconditions", []):
            contract.add_precondition(
                description=pre_data.get("description", ""),
                expression=pre_data.get("expression"),
            )
        
        for post_data in data.get("postconditions", []):
            contract.add_postcondition(
                description=post_data.get("description", ""),
                expression=post_data.get("expression"),
            )
        
        for inv_data in data.get("invariants", []):
            contract.add_invariant(
                description=inv_data.get("description", ""),
                expression=inv_data.get("expression"),
            )
        
        for throws_data in data.get("throws", []):
            contract.add_throws(
                exception_type=throws_data.get("exception_type", ""),
                condition=throws_data.get("condition", ""),
            )
        
        return contract
    
    @classmethod
    def from_docstring(cls, name: str, docstring: str) -> "Contract":
        """
        从 docstring 解析契约
        
        支持的标记:
        - @precondition: 前置条件
        - @postcondition: 后置条件
        - @invariant: 不变量
        - @throws: 异常规范
        """
        contract = cls(name=name)
        
        if not docstring:
            return contract
        
        # 提取描述（第一行）
        lines = docstring.strip().split("\n")
        if lines:
            contract.description = lines[0].strip()
        
        # 解析标记
        precondition_pattern = r"@precondition\s+(.+)"
        postcondition_pattern = r"@postcondition\s+(.+)"
        invariant_pattern = r"@invariant\s+(.+)"
        throws_pattern = r"@throws\s+(\w+)\s+(?:if\s+)?(.+)"
        
        for line in lines:
            line = line.strip()
            
            match = re.search(precondition_pattern, line, re.IGNORECASE)
            if match:
                contract.add_precondition(match.group(1))
                continue
            
            match = re.search(postcondition_pattern, line, re.IGNORECASE)
            if match:
                contract.add_postcondition(match.group(1))
                continue
            
            match = re.search(invariant_pattern, line, re.IGNORECASE)
            if match:
                contract.add_invariant(match.group(1))
                continue
            
            match = re.search(throws_pattern, line, re.IGNORECASE)
            if match:
                contract.add_throws(match.group(1), match.group(2))
        
        return contract


def contract(
    preconditions: Optional[List[str]] = None,
    postconditions: Optional[List[str]] = None,
    invariants: Optional[List[str]] = None,
):
    """
    契约装饰器
    
    用于为函数添加契约验证。
    
    Example:
        @contract(
            preconditions=["x > 0", "y is not None"],
            postconditions=["result >= 0"]
        )
        def my_function(x, y):
            ...
    """
    def decorator(func):
        func._contract = Contract(
            name=func.__name__,
            description=func.__doc__ or "",
        )
        
        for desc in (preconditions or []):
            func._contract.add_precondition(desc)
        
        for desc in (postconditions or []):
            func._contract.add_postcondition(desc)
        
        for desc in (invariants or []):
            func._contract.add_invariant(desc)
        
        return func
    
    return decorator
