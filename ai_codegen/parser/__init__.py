"""
代码解析模块 - 基于Tree-sitter的多语言代码解析器
"""

from .tree_sitter_parser import TreeSitterParser
from .dependency_extractor import DependencyExtractor
from .ast_analyzer import ASTAnalyzer
from .relationship_extractor import RelationshipExtractor, RelationType, Relationship

__all__ = [
    "TreeSitterParser", 
    "DependencyExtractor", 
    "ASTAnalyzer",
    "RelationshipExtractor",
    "RelationType",
    "Relationship",
]

# 便捷别名
CodeParser = TreeSitterParser
