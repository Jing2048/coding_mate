"""
接口提取器模块

从代码自动提取接口定义，构建 CodeEntity。
"""

from .interface_extractor import InterfaceExtractor
from .contract_inferencer import ContractInferencer
from .boundary_detector import ModuleBoundaryDetector

__all__ = [
    "InterfaceExtractor",
    "ContractInferencer",
    "ModuleBoundaryDetector",
]
