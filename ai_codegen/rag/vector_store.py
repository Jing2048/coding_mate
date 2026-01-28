"""
向量存储模块

使用 Chroma 存储 CodeEntity 的向量表示。
"""

from typing import List, Dict, Optional, Any
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from ai_codegen.models import CodeEntity


class VectorStore:
    """
    向量存储
    
    使用 Chroma 存储和管理 CodeEntity 的向量表示。
    """
    
    COLLECTION_NAME = "code_entities"
    
    def __init__(self, workspace_path: str, persist_directory: str = ".chroma_db"):
        """
        初始化向量存储
        
        Args:
            workspace_path: 工作空间路径
            persist_directory: 持久化目录名
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb not installed. Install with: pip install chromadb"
            )
        
        self.workspace_path = Path(workspace_path)
        self.persist_dir = self.workspace_path / persist_directory
        
        # 初始化 Chroma 客户端
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Code entities vector store"}
        )
    
    def add_entity(
        self,
        entity: CodeEntity,
        embedding: List[float]
    ):
        """
        添加实体到向量存储
        
        Args:
            entity: CodeEntity 对象
            embedding: 向量嵌入（由 Embedder 生成）
        """
        # 确保有 embedding_text
        if not entity.embedding_text:
            entity.generate_embedding_text()
        
        # 准备元数据
        metadata = {
            "type": entity.type.value,
            "name": entity.name,
            "module": entity.module,
            "domain": entity.domain,
            "complexity": str(entity.complexity),
            "file_path": entity.file_path
        }
        
        # 添加标签
        if entity.tags:
            metadata["tags"] = ",".join(entity.tags)
        
        # 添加到集合
        self.collection.add(
            ids=[entity.id],
            embeddings=[embedding],
            documents=[entity.embedding_text],
            metadatas=[metadata]
        )
    
    def add_entities_batch(
        self,
        entities: List[CodeEntity],
        embeddings: List[List[float]],
        batch_size: int = 100
    ):
        """
        批量添加实体
        
        Args:
            entities: CodeEntity 列表
            embeddings: 对应的向量列表
            batch_size: 批次大小
        """
        for i in range(0, len(entities), batch_size):
            batch_entities = entities[i:i+batch_size]
            batch_embeddings = embeddings[i:i+batch_size]
            
            ids = [e.id for e in batch_entities]
            documents = [e.embedding_text or e.generate_embedding_text() for e in batch_entities]
            metadatas = [{
                "type": e.type.value,
                "name": e.name,
                "module": e.module,
                "domain": e.domain,
                "complexity": str(e.complexity),
                "file_path": e.file_path,
                "tags": ",".join(e.tags) if e.tags else ""
            } for e in batch_entities]
            
            self.collection.add(
                ids=ids,
                embeddings=batch_embeddings,
                documents=documents,
                metadatas=metadatas
            )
    
    def update_entity(
        self,
        entity: CodeEntity,
        embedding: List[float]
    ):
        """更新实体（先删除再添加）"""
        self.delete_entity(entity.id)
        self.add_entity(entity, embedding)
    
    def delete_entity(self, entity_id: str):
        """删除实体"""
        try:
            self.collection.delete(ids=[entity_id])
        except Exception:
            pass  # 如果不存在，忽略错误
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        where: Optional[Dict] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        查询向量存储
        
        Args:
            query_embedding: 查询向量
            n_results: 返回结果数量
            where: 元数据过滤条件
            limit: 结果限制（与 n_results 相同）
        
        Returns:
            查询结果字典
        """
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit or n_results,
            where=where
        )
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        count = self.collection.count()
        return {
            "total_entities": count,
            "collection_name": self.COLLECTION_NAME
        }
    
    def clear_collection(self):
        """清空集合（谨慎使用）"""
        self.client.delete_collection(name=self.COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Code entities vector store"}
        )
