"""
代码解析模块 - 基于Tree-sitter的多语言代码解析器
"""

from .tree_sitter_parser import TreeSitterParser, CodeSymbol, NodeType, CodeLocation, ParseResult
from .dependency_extractor import DependencyExtractor
from .ast_analyzer import ASTAnalyzer
from .relationship_extractor import RelationshipExtractor, RelationType, Relationship

__all__ = [
    "TreeSitterParser", 
    "CodeSymbol",
    "NodeType",
    "CodeLocation",
    "ParseResult",
    "DependencyExtractor", 
    "ASTAnalyzer",
    "RelationshipExtractor",
    "RelationType",
    "Relationship",
]

# 便捷别名
CodeParser = TreeSitterParser
