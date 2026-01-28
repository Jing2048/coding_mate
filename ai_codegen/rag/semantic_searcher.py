"""
语义搜索模块

基于向量相似度进行语义搜索。
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from ai_codegen.models import CodeEntity
from ai_codegen.rag.vector_store import VectorStore
from ai_codegen.rag.embedder import Embedder
from ai_codegen.mcp_server.persistence_v2 import PersistenceManagerV2


@dataclass
class SearchResult:
    """搜索结果"""
    entity: CodeEntity
    score: float  # 相似度分数 (0-1)
    match_type: str  # "semantic", "keyword", "hybrid"
    highlights: List[str] = None  # 匹配的文本片段


class SemanticSearcher:
    """
    语义搜索器
    
    基于向量相似度搜索 CodeEntity。
    """
    
    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder,
        persistence: PersistenceManagerV2
    ):
        """
        初始化语义搜索器
        
        Args:
            vector_store: 向量存储
            embedder: 嵌入模型
            persistence: 持久化管理器（用于获取完整实体）
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.persistence = persistence
    
    def search_entities(
        self,
        query: str,
        limit: int = 10,
        entity_type: Optional[str] = None,
        module: Optional[str] = None,
        domain: Optional[str] = None,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        语义搜索实体
        
        Args:
            query: 搜索查询
            limit: 返回数量限制
            entity_type: 实体类型过滤
            module: 模块过滤
            domain: 领域过滤
            min_score: 最小相似度分数
        
        Returns:
            搜索结果列表
        """
        # 向量化查询
        query_embedding = self.embedder.embed(query)
        
        # 构建过滤条件
        where = {}
        if entity_type:
            where["type"] = entity_type
        if module:
            where["module"] = module
        if domain:
            where["domain"] = domain
        
        # 查询向量存储
        results = self.vector_store.query(
            query_embedding=query_embedding,
            n_results=limit * 2,  # 多取一些，后续过滤
            where=where if where else None
        )
        
        # 解析结果
        search_results = []
        if results.get('ids') and len(results['ids'][0]) > 0:
            for i, entity_id in enumerate(results['ids'][0]):
                # 计算相似度分数（Chroma 返回距离，转换为相似度）
                distance = results['distances'][0][i]
                score = 1.0 / (1.0 + distance)  # 简单的相似度转换
                
                if score >= min_score:
                    # 从 SQLite 获取完整实体
                    entity = self.persistence.get_entity(entity_id)
                    if entity:
                        search_results.append(SearchResult(
                            entity=entity,
                            score=score,
                            match_type="semantic",
                            highlights=self._extract_highlights(query, entity)
                        ))
        
        # 按分数排序并限制数量
        search_results.sort(key=lambda x: x.score, reverse=True)
        return search_results[:limit]
    
    def search_by_intent(
        self,
        intent: str,
        limit: int = 5
    ) -> List[CodeEntity]:
        """
        基于意图搜索（理解任务需求）
        
        Args:
            intent: 任务意图描述
            limit: 返回数量限制
        
        Returns:
            相关实体列表
        """
        results = self.search_entities(
            query=intent,
            limit=limit,
            min_score=0.3  # 较低的阈值，更宽松
        )
        return [r.entity for r in results]
    
    def hybrid_search(
        self,
        query: str,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        混合搜索（关键词 + 语义）
        
        Args:
            query: 搜索查询
            keyword_weight: 关键词权重
            semantic_weight: 语义权重
            limit: 返回数量限制
        
        Returns:
            搜索结果列表
        """
        # 语义搜索
        semantic_results = self.search_entities(query, limit=limit * 2)
        
        # 关键词搜索（简单实现：在 embedding_text 中搜索）
        keyword_results = self._keyword_search(query, limit=limit * 2)
        
        # 合并和加权
        combined = {}
        for result in semantic_results:
            entity_id = result.entity.id
            combined[entity_id] = {
                "entity": result.entity,
                "semantic_score": result.score * semantic_weight,
                "keyword_score": 0.0
            }
        
        for result in keyword_results:
            entity_id = result.entity.id
            if entity_id in combined:
                combined[entity_id]["keyword_score"] = result.score * keyword_weight
            else:
                combined[entity_id] = {
                    "entity": result.entity,
                    "semantic_score": 0.0,
                    "keyword_score": result.score * keyword_weight
                }
        
        # 计算总分并排序
        final_results = []
        for entity_id, data in combined.items():
            total_score = data["semantic_score"] + data["keyword_score"]
            final_results.append(SearchResult(
                entity=data["entity"],
                score=total_score,
                match_type="hybrid",
                highlights=self._extract_highlights(query, data["entity"])
            ))
        
        final_results.sort(key=lambda x: x.score, reverse=True)
        return final_results[:limit]
    
    def _keyword_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """关键词搜索（简单实现）"""
        # 使用 SQLite 的文本搜索
        entities = self.persistence.search_entities(query, limit=limit * 2)
        
        results = []
        query_lower = query.lower()
        for entity in entities:
            # 计算关键词匹配分数
            text = entity.embedding_text.lower()
            score = 0.0
            
            # 精确匹配
            if query_lower in text:
                score = 0.8
            # 单词匹配
            query_words = query_lower.split()
            matched_words = sum(1 for word in query_words if word in text)
            score = max(score, matched_words / len(query_words) * 0.6)
            
            if score > 0:
                results.append(SearchResult(
                    entity=entity,
                    score=score,
                    match_type="keyword",
                    highlights=self._extract_highlights(query, entity)
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    def _extract_highlights(self, query: str, entity: CodeEntity) -> List[str]:
        """提取匹配的文本片段"""
        highlights = []
        query_lower = query.lower()
        text = entity.embedding_text.lower()
        
        # 查找包含查询词的片段
        words = text.split()
        for i, word in enumerate(words):
            if query_lower in word or any(qw in word for qw in query_lower.split()):
                start = max(0, i - 3)
                end = min(len(words), i + 4)
                snippet = " ".join(words[start:end])
                highlights.append(snippet)
                if len(highlights) >= 3:
                    break
        
        return highlights
