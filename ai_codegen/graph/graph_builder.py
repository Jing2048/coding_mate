"""
图构建器

从代码解析结果构建知识图谱。
"""

from typing import Dict, List, Optional, Any
from pathlib import Path

from .knowledge_graph import (
    KnowledgeGraph, 
    GraphNode, 
    GraphRelation, 
    NodeLabel, 
    RelationType
)
from ..parser.tree_sitter_parser import ParseResult, CodeSymbol, NodeType
from ..parser.dependency_extractor import DependencyExtractor, ModuleInfo, DependencyType


class GraphBuilder:
    """
    图构建器
    
    将代码解析结果转换为知识图谱。
    """
    
    def __init__(self, graph: Optional[KnowledgeGraph] = None):
        """
        初始化图构建器
        
        Args:
            graph: 现有的知识图谱（可选）
        """
        self.graph = graph or KnowledgeGraph()
        self._module_id_map: Dict[str, str] = {}
        self._symbol_id_map: Dict[str, str] = {}
    
    def build_from_parse_results(
        self,
        parse_results: Dict[str, ParseResult],
        base_path: Optional[str] = None
    ) -> KnowledgeGraph:
        """
        从解析结果构建图
        
        Args:
            parse_results: 文件路径到解析结果的映射
            base_path: 基础路径
            
        Returns:
            KnowledgeGraph: 构建的知识图谱
        """
        # 提取依赖关系
        extractor = DependencyExtractor()
        modules = extractor.extract_from_parse_results(parse_results, base_path)
        
        # 第一遍：创建所有节点
        for file_path, module_info in modules.items():
            self._create_module_node(module_info)
            
            for symbol in module_info.symbols:
                self._create_symbol_node(symbol, module_info.name)
        
        # 第二遍：创建关系
        for file_path, module_info in modules.items():
            self._create_module_relations(module_info)
        
        return self.graph
    
    def _create_module_node(self, module_info: ModuleInfo) -> str:
        """创建模块节点"""
        node_id = f"module:{module_info.name}"
        
        node = GraphNode(
            id=node_id,
            label=NodeLabel.MODULE,
            properties={
                "name": module_info.name,
                "path": module_info.path,
                "language": module_info.language,
                "exports": module_info.exports,
            }
        )
        
        self.graph.add_node(node)
        self._module_id_map[module_info.name] = node_id
        
        return node_id
    
    def _create_symbol_node(self, symbol: CodeSymbol, module_name: str) -> str:
        """创建符号节点"""
        full_name = f"{module_name}.{symbol.name}"
        node_id = f"symbol:{full_name}"
        
        # 映射 NodeType 到 NodeLabel
        label_map = {
            NodeType.CLASS: NodeLabel.CLASS,
            NodeType.FUNCTION: NodeLabel.FUNCTION,
            NodeType.METHOD: NodeLabel.METHOD,
            NodeType.INTERFACE: NodeLabel.INTERFACE,
            NodeType.TYPE: NodeLabel.TYPE,
            NodeType.VARIABLE: NodeLabel.VARIABLE,
        }
        
        label = label_map.get(symbol.node_type, NodeLabel.FUNCTION)
        
        node = GraphNode(
            id=node_id,
            label=label,
            properties={
                "name": symbol.name,
                "full_name": full_name,
                "module": module_name,
                "signature": symbol.signature,
                "docstring": symbol.docstring,
                "location": symbol.location.to_dict(),
            }
        )
        
        self.graph.add_node(node)
        self._symbol_id_map[full_name] = node_id
        self._symbol_id_map[symbol.name] = node_id  # 短名称也索引
        
        # 创建 CONTAINS 关系
        module_id = self._module_id_map.get(module_name)
        if module_id:
            self.graph.add_relation(GraphRelation(
                source_id=module_id,
                target_id=node_id,
                rel_type=RelationType.CONTAINS,
            ))
        
        # 如果有父级（类的方法），创建关系
        if symbol.parent:
            parent_full_name = f"{module_name}.{symbol.parent}"
            parent_id = self._symbol_id_map.get(parent_full_name)
            if parent_id:
                self.graph.add_relation(GraphRelation(
                    source_id=parent_id,
                    target_id=node_id,
                    rel_type=RelationType.CONTAINS,
                ))
        
        return node_id
    
    def _create_module_relations(self, module_info: ModuleInfo):
        """创建模块关系"""
        source_module_id = self._module_id_map.get(module_info.name)
        if not source_module_id:
            return
        
        for dep in module_info.dependencies:
            # 映射依赖类型到关系类型
            rel_type_map = {
                DependencyType.IMPORTS: RelationType.IMPORTS,
                DependencyType.EXPORTS: RelationType.EXPORTS,
                DependencyType.CALLS: RelationType.CALLS,
                DependencyType.CALLED_BY: RelationType.CALLED_BY,
                DependencyType.IMPLEMENTS: RelationType.IMPLEMENTS,
                DependencyType.EXTENDS: RelationType.EXTENDS,
                DependencyType.DEPENDS_ON: RelationType.DEPENDS_ON,
            }
            
            rel_type = rel_type_map.get(dep.dep_type, RelationType.DEPENDS_ON)
            
            # 查找目标节点
            target_id = (
                self._module_id_map.get(dep.target) or
                self._symbol_id_map.get(dep.target) or
                f"external:{dep.target}"  # 外部依赖
            )
            
            # 查找源节点
            source_id = (
                self._symbol_id_map.get(dep.source) or
                self._module_id_map.get(dep.source) or
                source_module_id
            )
            
            self.graph.add_relation(GraphRelation(
                source_id=source_id,
                target_id=target_id,
                rel_type=rel_type,
                properties=dep.metadata,
            ))
    
    def add_external_dependency(
        self,
        module_name: str,
        dependency_name: str,
        dep_type: RelationType = RelationType.IMPORTS
    ):
        """
        添加外部依赖
        
        Args:
            module_name: 模块名
            dependency_name: 依赖名
            dep_type: 依赖类型
        """
        # 创建外部依赖节点
        ext_id = f"external:{dependency_name}"
        
        if not self.graph.get_node(ext_id):
            self.graph.add_node(GraphNode(
                id=ext_id,
                label=NodeLabel.MODULE,
                properties={
                    "name": dependency_name,
                    "external": True,
                }
            ))
        
        # 创建依赖关系
        source_id = self._module_id_map.get(module_name)
        if source_id:
            self.graph.add_relation(GraphRelation(
                source_id=source_id,
                target_id=ext_id,
                rel_type=dep_type,
            ))
    
    def get_module_hierarchy(self) -> Dict[str, Any]:
        """
        获取模块层次结构
        
        Returns:
            Dict: 模块层次结构
        """
        modules = self.graph.get_nodes_by_label(NodeLabel.MODULE)
        
        hierarchy = {}
        
        for module in modules:
            if module.properties.get("external"):
                continue
                
            name = module.properties.get("name", "")
            parts = name.split(".")
            
            current = hierarchy
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        return hierarchy
    
    def export_to_dot(self) -> str:
        """
        导出为 DOT 格式（可用于 Graphviz 可视化）
        
        Returns:
            str: DOT 格式字符串
        """
        lines = ["digraph CodeGraph {"]
        lines.append("  rankdir=LR;")
        lines.append("  node [shape=box];")
        
        # 添加节点
        for node in self.graph._nodes.values():
            label = node.properties.get("name", node.id)
            color = {
                NodeLabel.MODULE: "lightblue",
                NodeLabel.CLASS: "lightyellow",
                NodeLabel.FUNCTION: "lightgreen",
                NodeLabel.METHOD: "lightgreen",
                NodeLabel.INTERFACE: "lightpink",
            }.get(node.label, "white")
            
            lines.append(f'  "{node.id}" [label="{label}", fillcolor="{color}", style="filled"];')
        
        # 添加边
        for rel in self.graph._relations:
            style = {
                RelationType.IMPORTS: "dashed",
                RelationType.EXTENDS: "bold",
                RelationType.IMPLEMENTS: "dotted",
            }.get(rel.rel_type, "solid")
            
            lines.append(f'  "{rel.source_id}" -> "{rel.target_id}" [label="{rel.rel_type.value}", style="{style}"];')
        
        lines.append("}")
        
        return "\n".join(lines)
