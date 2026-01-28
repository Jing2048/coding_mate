"""
图查询引擎

提供高级的图查询功能。
"""

from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass
from enum import Enum

from .knowledge_graph import KnowledgeGraph, GraphNode, GraphRelation, NodeLabel, RelationType


class QueryOperator(Enum):
    """查询操作符"""
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"


@dataclass
class QueryCondition:
    """查询条件"""
    field: str
    operator: QueryOperator
    value: Any
    
    def matches(self, properties: Dict[str, Any]) -> bool:
        """检查属性是否匹配条件"""
        actual = properties.get(self.field)
        
        if self.operator == QueryOperator.EQUALS:
            return actual == self.value
        elif self.operator == QueryOperator.NOT_EQUALS:
            return actual != self.value
        elif self.operator == QueryOperator.CONTAINS:
            return self.value in str(actual) if actual else False
        elif self.operator == QueryOperator.STARTS_WITH:
            return str(actual).startswith(self.value) if actual else False
        elif self.operator == QueryOperator.ENDS_WITH:
            return str(actual).endswith(self.value) if actual else False
        elif self.operator == QueryOperator.IN:
            return actual in self.value
        elif self.operator == QueryOperator.NOT_IN:
            return actual not in self.value
        elif self.operator == QueryOperator.GREATER_THAN:
            return actual > self.value if actual else False
        elif self.operator == QueryOperator.LESS_THAN:
            return actual < self.value if actual else False
        
        return False


class GraphQueryEngine:
    """
    图查询引擎
    
    提供流式查询 API 和高级查询功能。
    """
    
    def __init__(self, graph: KnowledgeGraph):
        """
        初始化查询引擎
        
        Args:
            graph: 知识图谱
        """
        self.graph = graph
        self._current_nodes: List[GraphNode] = []
        self._current_relations: List[GraphRelation] = []
    
    def nodes(self, label: Optional[NodeLabel] = None) -> "GraphQueryEngine":
        """
        选择节点
        
        Args:
            label: 节点标签（可选）
        """
        if label:
            self._current_nodes = self.graph.get_nodes_by_label(label)
        else:
            self._current_nodes = list(self.graph._nodes.values())
        return self
    
    def where(self, condition: QueryCondition) -> "GraphQueryEngine":
        """
        添加过滤条件
        
        Args:
            condition: 查询条件
        """
        self._current_nodes = [
            n for n in self._current_nodes
            if condition.matches(n.properties)
        ]
        return self
    
    def filter(self, predicate: Callable[[GraphNode], bool]) -> "GraphQueryEngine":
        """
        使用自定义函数过滤
        
        Args:
            predicate: 过滤函数
        """
        self._current_nodes = [
            n for n in self._current_nodes
            if predicate(n)
        ]
        return self
    
    def outgoing(
        self,
        rel_type: Optional[RelationType] = None
    ) -> "GraphQueryEngine":
        """
        获取出边的目标节点
        
        Args:
            rel_type: 关系类型（可选）
        """
        target_ids = set()
        
        for node in self._current_nodes:
            relations = self.graph.get_relations(source_id=node.id, rel_type=rel_type)
            for rel in relations:
                target_ids.add(rel.target_id)
        
        self._current_nodes = [
            self.graph.get_node(nid)
            for nid in target_ids
            if self.graph.get_node(nid)
        ]
        return self
    
    def incoming(
        self,
        rel_type: Optional[RelationType] = None
    ) -> "GraphQueryEngine":
        """
        获取入边的源节点
        
        Args:
            rel_type: 关系类型（可选）
        """
        source_ids = set()
        
        for node in self._current_nodes:
            relations = self.graph.get_relations(target_id=node.id, rel_type=rel_type)
            for rel in relations:
                source_ids.add(rel.source_id)
        
        self._current_nodes = [
            self.graph.get_node(nid)
            for nid in source_ids
            if self.graph.get_node(nid)
        ]
        return self
    
    def limit(self, n: int) -> "GraphQueryEngine":
        """限制结果数量"""
        self._current_nodes = self._current_nodes[:n]
        return self
    
    def collect(self) -> List[GraphNode]:
        """收集查询结果"""
        return self._current_nodes
    
    def collect_ids(self) -> List[str]:
        """收集节点 ID"""
        return [n.id for n in self._current_nodes]
    
    def collect_properties(self, *fields: str) -> List[Dict[str, Any]]:
        """
        收集节点属性
        
        Args:
            *fields: 要收集的字段名
        """
        results = []
        
        for node in self._current_nodes:
            if fields:
                result = {f: node.properties.get(f) for f in fields}
            else:
                result = node.properties.copy()
            result["_id"] = node.id
            result["_label"] = node.label.value
            results.append(result)
        
        return results
    
    def count(self) -> int:
        """计数"""
        return len(self._current_nodes)
    
    def first(self) -> Optional[GraphNode]:
        """获取第一个结果"""
        return self._current_nodes[0] if self._current_nodes else None
    
    # 高级查询方法
    
    def find_modules_depending_on(self, module_name: str) -> List[GraphNode]:
        """查找依赖某模块的所有模块"""
        return (
            self.nodes(NodeLabel.MODULE)
            .outgoing(RelationType.IMPORTS)
            .where(QueryCondition("name", QueryOperator.EQUALS, module_name))
            .incoming(RelationType.IMPORTS)
            .collect()
        )
    
    def find_class_hierarchy(self, class_name: str) -> Dict[str, Any]:
        """
        查找类继承层次
        
        Args:
            class_name: 类名
            
        Returns:
            Dict: 继承层次结构
        """
        # 查找类节点
        class_nodes = (
            self.nodes(NodeLabel.CLASS)
            .where(QueryCondition("name", QueryOperator.EQUALS, class_name))
            .collect()
        )
        
        if not class_nodes:
            return {}
        
        class_node = class_nodes[0]
        
        # 查找父类
        parents = []
        parent_rels = self.graph.get_relations(
            source_id=class_node.id,
            rel_type=RelationType.EXTENDS
        )
        for rel in parent_rels:
            parent_node = self.graph.get_node(rel.target_id)
            if parent_node:
                parents.append(parent_node.properties.get("name", rel.target_id))
        
        # 查找子类
        children = []
        child_rels = self.graph.get_relations(
            target_id=class_node.id,
            rel_type=RelationType.EXTENDS
        )
        for rel in child_rels:
            child_node = self.graph.get_node(rel.source_id)
            if child_node:
                children.append(child_node.properties.get("name", rel.source_id))
        
        # 查找方法
        methods = []
        method_rels = self.graph.get_relations(
            source_id=class_node.id,
            rel_type=RelationType.CONTAINS
        )
        for rel in method_rels:
            method_node = self.graph.get_node(rel.target_id)
            if method_node and method_node.label == NodeLabel.METHOD:
                methods.append({
                    "name": method_node.properties.get("name"),
                    "signature": method_node.properties.get("signature"),
                })
        
        return {
            "name": class_name,
            "id": class_node.id,
            "parents": parents,
            "children": children,
            "methods": methods,
        }
    
    def find_call_graph(
        self,
        function_name: str,
        depth: int = 3
    ) -> Dict[str, Any]:
        """
        查找函数调用图
        
        Args:
            function_name: 函数名
            depth: 深度
            
        Returns:
            Dict: 调用图
        """
        # 查找函数节点
        func_nodes = (
            self.nodes()
            .filter(lambda n: n.label in (NodeLabel.FUNCTION, NodeLabel.METHOD))
            .where(QueryCondition("name", QueryOperator.EQUALS, function_name))
            .collect()
        )
        
        if not func_nodes:
            return {}
        
        func_node = func_nodes[0]
        
        # 递归构建调用图
        def build_call_tree(node_id: str, current_depth: int, visited: Set[str]) -> Dict:
            if current_depth > depth or node_id in visited:
                return {}
            
            visited.add(node_id)
            node = self.graph.get_node(node_id)
            
            if not node:
                return {}
            
            result = {
                "name": node.properties.get("name", node_id),
                "calls": [],
            }
            
            call_rels = self.graph.get_relations(
                source_id=node_id,
                rel_type=RelationType.CALLS
            )
            
            for rel in call_rels:
                child_tree = build_call_tree(rel.target_id, current_depth + 1, visited)
                if child_tree:
                    result["calls"].append(child_tree)
            
            return result
        
        return build_call_tree(func_node.id, 0, set())
    
    def find_impact_analysis(self, symbol_name: str) -> Dict[str, List[str]]:
        """
        影响分析：查找修改某符号会影响哪些其他符号
        
        Args:
            symbol_name: 符号名
            
        Returns:
            Dict: 影响分析结果
        """
        # 查找符号节点
        symbol_nodes = (
            self.nodes()
            .where(QueryCondition("name", QueryOperator.EQUALS, symbol_name))
            .collect()
        )
        
        if not symbol_nodes:
            return {"direct": [], "indirect": []}
        
        symbol_node = symbol_nodes[0]
        
        # 查找直接依赖
        direct = set()
        
        # 查找谁调用了这个符号
        call_rels = self.graph.get_relations(
            target_id=symbol_node.id,
            rel_type=RelationType.CALLS
        )
        for rel in call_rels:
            caller = self.graph.get_node(rel.source_id)
            if caller:
                direct.add(caller.properties.get("name", rel.source_id))
        
        # 查找谁继承/实现了这个符号
        extend_rels = self.graph.get_relations(
            target_id=symbol_node.id,
            rel_type=RelationType.EXTENDS
        )
        for rel in extend_rels:
            child = self.graph.get_node(rel.source_id)
            if child:
                direct.add(child.properties.get("name", rel.source_id))
        
        impl_rels = self.graph.get_relations(
            target_id=symbol_node.id,
            rel_type=RelationType.IMPLEMENTS
        )
        for rel in impl_rels:
            impl = self.graph.get_node(rel.source_id)
            if impl:
                direct.add(impl.properties.get("name", rel.source_id))
        
        # 查找间接依赖（传递闭包的简化版本）
        indirect = set()
        visited = {symbol_node.id}
        
        for d in list(direct):
            d_nodes = (
                self.nodes()
                .where(QueryCondition("name", QueryOperator.EQUALS, d))
                .collect()
            )
            
            for d_node in d_nodes:
                if d_node.id in visited:
                    continue
                visited.add(d_node.id)
                
                # 查找调用者的调用者
                caller_rels = self.graph.get_relations(
                    target_id=d_node.id,
                    rel_type=RelationType.CALLS
                )
                for rel in caller_rels:
                    caller = self.graph.get_node(rel.source_id)
                    if caller and caller.id not in visited:
                        indirect.add(caller.properties.get("name", rel.source_id))
        
        return {
            "direct": list(direct),
            "indirect": list(indirect),
        }
    
    def search(
        self,
        query: str,
        fields: Optional[List[str]] = None
    ) -> List[GraphNode]:
        """
        全文搜索
        
        Args:
            query: 搜索关键词
            fields: 要搜索的字段
        """
        fields = fields or ["name", "signature", "docstring"]
        query_lower = query.lower()
        
        results = []
        
        for node in self.graph._nodes.values():
            for field in fields:
                value = node.properties.get(field)
                if value and query_lower in str(value).lower():
                    results.append(node)
                    break
        
        return results
