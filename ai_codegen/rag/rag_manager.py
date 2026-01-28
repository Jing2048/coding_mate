"""
RAG 管理器

统一管理 RAG 系统的所有组件。
"""

from typing import List, Dict, Any, Optional
from pathlib import Path

from ai_codegen.models import CodeEntity
from ai_codegen.rag.vector_store import VectorStore
from ai_codegen.rag.embedder import Embedder
from ai_codegen.rag.semantic_searcher import SemanticSearcher, SearchResult
from ai_codegen.rag.context_retriever import ContextRetriever
from ai_codegen.mcp_server.persistence_v2 import PersistenceManagerV2


class RAGManager:
    """
    RAG 管理器
    
    统一管理向量存储、嵌入模型、搜索和检索。
    """
    
    def __init__(self, workspace_path: str):
        """
        初始化 RAG 管理器
        
        Args:
            workspace_path: 工作空间路径
        """
        self.workspace_path = Path(workspace_path)
        
        # 初始化组件
        self.vector_store = VectorStore(workspace_path)
        self.embedder = Embedder()
        self.persistence = PersistenceManagerV2(workspace_path)
        self.searcher = SemanticSearcher(
            self.vector_store,
            self.embedder,
            self.persistence
        )
        self.retriever = ContextRetriever(
            self.searcher,
            self.persistence
        )
    
    def index_entity(self, entity: CodeEntity):
        """
        索引实体（同步到 Vector DB）
        
        Args:
            entity: CodeEntity 对象
        """
        # 确保有 embedding_text
        if not entity.embedding_text:
            entity.generate_embedding_text()
        
        # 向量化
        embedding = self.embedder.embed(entity.embedding_text)
        
        # 存储到向量数据库
        self.vector_store.add_entity(entity, embedding)
    
    def index_entities_batch(self, entities: List[CodeEntity], batch_size: int = 100):
        """
        批量索引实体
        
        Args:
            entities: CodeEntity 列表
            batch_size: 批次大小
        """
        # 准备 embedding_text
        for entity in entities:
            if not entity.embedding_text:
                entity.generate_embedding_text()
        
        # 批量向量化
        texts = [e.embedding_text for e in entities]
        embeddings = self.embedder.embed_batch(texts, batch_size=batch_size)
        
        # 批量存储
        self.vector_store.add_entities_batch(entities, embeddings, batch_size=batch_size)
    
    def search(
        self,
        query: str,
        limit: int = 10,
        entity_type: Optional[str] = None,
        module: Optional[str] = None,
        domain: Optional[str] = None,
        use_hybrid: bool = False
    ) -> List[CodeEntity]:
        """
        搜索接口
        
        Args:
            query: 搜索查询
            limit: 返回数量限制
            entity_type: 实体类型过滤
            module: 模块过滤
            domain: 领域过滤
            use_hybrid: 是否使用混合搜索
        
        Returns:
            实体列表
        """
        if use_hybrid:
            results = self.searcher.hybrid_search(query, limit=limit)
        else:
            results = self.searcher.search_entities(
                query=query,
                limit=limit,
                entity_type=entity_type,
                module=module,
                domain=domain
            )
        
        return [r.entity for r in results]
    
    def retrieve_context(
        self,
        task_description: str,
        max_interfaces: int = 5,
        max_dependencies: int = 10,
        include_examples: bool = True
    ) -> Dict[str, Any]:
        """
        检索上下文
        
        Args:
            task_description: 任务描述
            max_interfaces: 最大接口数量
            max_dependencies: 最大依赖数量
            include_examples: 是否包含示例
        
        Returns:
            上下文字典
        """
        return self.retriever.retrieve_for_task(
            task_description=task_description,
            max_interfaces=max_interfaces,
            max_dependencies=max_dependencies,
            include_examples=include_examples
        )
    
    def sync_from_persistence(self, force: bool = False):
        """
        从 SQLite 同步到 Vector DB
        
        Args:
            force: 是否强制重新同步（清空后重建）
        """
        if force:
            self.vector_store.clear_collection()
        
        # 获取所有实体
        all_entities = self.persistence.get_all_entities(limit=None)
        
        if not all_entities:
            return
        
        # 检查哪些实体已经在向量数据库中
        existing_ids = set()
        if not force:
            try:
                # 获取现有 ID（通过查询所有）
                existing = self.vector_store.collection.get()
                if existing and existing.get('ids'):
                    existing_ids = set(existing['ids'])
            except Exception:
                pass
        
        # 过滤出需要同步的实体
        entities_to_sync = [e for e in all_entities if e.id not in existing_ids]
        
        if not entities_to_sync:
            return
        
        # 批量向量化和存储
        print(f"同步 {len(entities_to_sync)} 个实体到向量数据库...")
        self.index_entities_batch(entities_to_sync, batch_size=100)
        print(f"同步完成，共 {len(entities_to_sync)} 个实体")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        vector_stats = self.vector_store.get_collection_stats()
        sqlite_stats = self.persistence.get_statistics()
        
        return {
            "vector_store": vector_stats,
            "sqlite": sqlite_stats,
            "embedding_dimension": self.embedder.get_embedding_dimension()
        }
