"""
接口定义模块

提供代码接口的定义、注册和验证功能。
"""

from .interface_registry import InterfaceRegistry
from .contract import Contract, Precondition, Postcondition, Invariant
from .interface_schema import InterfaceSchema, MethodSchema, ParameterSchema, TypeSchema

__all__ = [
    "InterfaceRegistry",
    "Contract",
    "Precondition",
    "Postcondition",
    "Invariant",
    "InterfaceSchema",
    "MethodSchema",
    "ParameterSchema",
    "TypeSchema",
]
