"""
代码知识图谱

存储和管理代码结构、依赖关系的知识图谱。
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
from enum import Enum
import hashlib


class NodeLabel(Enum):
    """图节点标签"""
    MODULE = "Module"
    CLASS = "Class"
    FUNCTION = "Function"
    METHOD = "Method"
    INTERFACE = "Interface"
    TYPE = "Type"
    VARIABLE = "Variable"


class RelationType(Enum):
    """图关系类型"""
    IMPORTS = "IMPORTS"
    EXPORTS = "EXPORTS"
    CALLS = "CALLS"
    CALLED_BY = "CALLED_BY"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"
    CONTAINS = "CONTAINS"
    DEPENDS_ON = "DEPENDS_ON"
    RETURNS = "RETURNS"
    ACCEPTS = "ACCEPTS"


@dataclass
class GraphNode:
    """图节点"""
    id: str
    label: NodeLabel
    properties: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label.value,
            "properties": self.properties,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        return cls(
            id=data["id"],
            label=NodeLabel(data["label"]),
            properties=data.get("properties", {}),
        )


@dataclass
class GraphRelation:
    """图关系"""
    source_id: str
    target_id: str
    rel_type: RelationType
    properties: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.rel_type.value,
            "properties": self.properties,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphRelation":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            rel_type=RelationType(data["type"]),
            properties=data.get("properties", {}),
        )


class KnowledgeGraph:
    """
    代码知识图谱
    
    支持内存存储和 Neo4j 持久化。
    提供代码结构和依赖关系的图存储和查询能力。
    """
    
    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
    ):
        """
        初始化知识图谱
        
        Args:
            neo4j_uri: Neo4j 连接 URI (可选)
            neo4j_user: Neo4j 用户名
            neo4j_password: Neo4j 密码
        """
        self._nodes: Dict[str, GraphNode] = {}
        self._relations: List[GraphRelation] = []
        self._adjacency: Dict[str, Set[str]] = {}  # 出边
        self._reverse_adjacency: Dict[str, Set[str]] = {}  # 入边
        
        # Neo4j 连接（可选）
        self._driver = None
        if neo4j_uri:
            self._init_neo4j(neo4j_uri, neo4j_user, neo4j_password)
    
    def _init_neo4j(self, uri: str, user: str, password: str):
        """初始化 Neo4j 连接"""
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
            print(f"Connected to Neo4j at {uri}")
        except ImportError:
            print("Neo4j driver not available, using in-memory storage only")
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
    
    def close(self):
        """关闭数据库连接"""
        if self._driver:
            self._driver.close()
    
    def add_node(self, node: GraphNode) -> str:
        """
        添加节点
        
        Args:
            node: 图节点
            
        Returns:
            str: 节点 ID
        """
        self._nodes[node.id] = node
        
        if node.id not in self._adjacency:
            self._adjacency[node.id] = set()
        if node.id not in self._reverse_adjacency:
            self._reverse_adjacency[node.id] = set()
        
        # 同步到 Neo4j
        if self._driver:
            self._sync_node_to_neo4j(node)
        
        return node.id
    
    def add_relation(self, relation: GraphRelation):
        """
        添加关系
        
        Args:
            relation: 图关系
        """
        self._relations.append(relation)
        
        # 更新邻接表
        if relation.source_id not in self._adjacency:
            self._adjacency[relation.source_id] = set()
        self._adjacency[relation.source_id].add(relation.target_id)
        
        if relation.target_id not in self._reverse_adjacency:
            self._reverse_adjacency[relation.target_id] = set()
        self._reverse_adjacency[relation.target_id].add(relation.source_id)
        
        # 同步到 Neo4j
        if self._driver:
            self._sync_relation_to_neo4j(relation)
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """获取节点"""
        return self._nodes.get(node_id)
    
    def get_nodes_by_label(self, label: NodeLabel) -> List[GraphNode]:
        """按标签获取节点"""
        return [n for n in self._nodes.values() if n.label == label]
    
    def get_relations(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        rel_type: Optional[RelationType] = None
    ) -> List[GraphRelation]:
        """
        获取关系
        
        Args:
            source_id: 源节点 ID（可选）
            target_id: 目标节点 ID（可选）
            rel_type: 关系类型（可选）
        """
        results = []
        
        for rel in self._relations:
            if source_id and rel.source_id != source_id:
                continue
            if target_id and rel.target_id != target_id:
                continue
            if rel_type and rel.rel_type != rel_type:
                continue
            results.append(rel)
        
        return results
    
    def find_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 10
    ) -> Optional[List[str]]:
        """
        查找两个节点之间的路径
        
        Args:
            start_id: 起始节点 ID
            end_id: 结束节点 ID
            max_depth: 最大搜索深度
            
        Returns:
            Optional[List[str]]: 路径节点列表，如果不存在则返回 None
        """
        if start_id not in self._nodes or end_id not in self._nodes:
            return None
        
        # BFS
        from collections import deque
        
        queue = deque([(start_id, [start_id])])
        visited = {start_id}
        
        while queue:
            current, path = queue.popleft()
            
            if current == end_id:
                return path
            
            if len(path) >= max_depth:
                continue
            
            for neighbor in self._adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return None
    
    def get_subgraph(
        self,
        center_id: str,
        depth: int = 2,
        direction: str = "both"
    ) -> Tuple[List[GraphNode], List[GraphRelation]]:
        """
        获取以某节点为中心的子图
        
        Args:
            center_id: 中心节点 ID
            depth: 深度
            direction: "outgoing" | "incoming" | "both"
            
        Returns:
            Tuple: (节点列表, 关系列表)
        """
        nodes = set()
        relations = []
        
        def expand(node_id: str, current_depth: int):
            if current_depth > depth or node_id in nodes:
                return
            
            nodes.add(node_id)
            
            if direction in ("outgoing", "both"):
                for target in self._adjacency.get(node_id, set()):
                    expand(target, current_depth + 1)
                    
            if direction in ("incoming", "both"):
                for source in self._reverse_adjacency.get(node_id, set()):
                    expand(source, current_depth + 1)
        
        expand(center_id, 0)
        
        # 收集相关的关系
        for rel in self._relations:
            if rel.source_id in nodes and rel.target_id in nodes:
                relations.append(rel)
        
        node_list = [self._nodes[nid] for nid in nodes if nid in self._nodes]
        
        return node_list, relations
    
    def query(self, cypher: str, **params) -> List[Dict[str, Any]]:
        """
        执行 Cypher 查询（需要 Neo4j）
        
        Args:
            cypher: Cypher 查询语句
            **params: 查询参数
            
        Returns:
            List[Dict]: 查询结果
        """
        if not self._driver:
            raise RuntimeError("Neo4j connection not available")
        
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]
    
    def _sync_node_to_neo4j(self, node: GraphNode):
        """同步节点到 Neo4j"""
        if not self._driver:
            return
            
        cypher = f"""
        MERGE (n:{node.label.value} {{id: $id}})
        SET n += $properties
        """
        
        with self._driver.session() as session:
            session.run(cypher, id=node.id, properties=node.properties)
    
    def _sync_relation_to_neo4j(self, relation: GraphRelation):
        """同步关系到 Neo4j"""
        if not self._driver:
            return
            
        cypher = f"""
        MATCH (a {{id: $source_id}})
        MATCH (b {{id: $target_id}})
        MERGE (a)-[r:{relation.rel_type.value}]->(b)
        SET r += $properties
        """
        
        with self._driver.session() as session:
            session.run(
                cypher,
                source_id=relation.source_id,
                target_id=relation.target_id,
                properties=relation.properties
            )
    
    def save_to_file(self, file_path: str):
        """
        保存图到 JSON 文件
        
        Args:
            file_path: 文件路径
        """
        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "relations": [r.to_dict() for r in self._relations],
        }
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load_from_file(self, file_path: str):
        """
        从 JSON 文件加载图
        
        Args:
            file_path: 文件路径
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self._nodes.clear()
        self._relations.clear()
        self._adjacency.clear()
        self._reverse_adjacency.clear()
        
        for node_data in data.get("nodes", []):
            node = GraphNode.from_dict(node_data)
            self.add_node(node)
        
        for rel_data in data.get("relations", []):
            relation = GraphRelation.from_dict(rel_data)
            self.add_relation(relation)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取图统计信息"""
        label_counts = {}
        for node in self._nodes.values():
            label = node.label.value
            label_counts[label] = label_counts.get(label, 0) + 1
        
        rel_type_counts = {}
        for rel in self._relations:
            rel_type = rel.rel_type.value
            rel_type_counts[rel_type] = rel_type_counts.get(rel_type, 0) + 1
        
        return {
            "total_nodes": len(self._nodes),
            "total_relations": len(self._relations),
            "nodes_by_label": label_counts,
            "relations_by_type": rel_type_counts,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "relations": [r.to_dict() for r in self._relations],
            "statistics": self.get_statistics(),
        }
