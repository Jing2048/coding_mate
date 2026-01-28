"""
上下文检索模块

为任务和接口检索相关上下文。
"""

from typing import Dict, List, Any, Optional
import re

from ai_codegen.models import CodeEntity
from ai_codegen.rag.semantic_searcher import SemanticSearcher
from ai_codegen.mcp_server.persistence_v2 import PersistenceManagerV2


class ContextRetriever:
    """
    上下文检索器
    
    基于任务描述和接口需求检索相关上下文。
    """
    
    def __init__(
        self,
        searcher: SemanticSearcher,
        persistence: PersistenceManagerV2
    ):
        """
        初始化上下文检索器
        
        Args:
            searcher: 语义搜索器
            persistence: 持久化管理器
        """
        self.searcher = searcher
        self.persistence = persistence
    
    def retrieve_for_task(
        self,
        task_description: str,
        max_interfaces: int = 5,
        max_dependencies: int = 10,
        include_examples: bool = True
    ) -> Dict[str, Any]:
        """
        为任务检索上下文
        
        Args:
            task_description: 任务描述
            max_interfaces: 最大接口数量
            max_dependencies: 最大依赖数量
            include_examples: 是否包含示例
        
        Returns:
            上下文字典
        """
        # 1. 理解任务意图
        intent = self._understand_intent(task_description)
        
        # 2. 搜索相关接口
        search_results = self.searcher.search_by_intent(intent, limit=max_interfaces)
        interfaces = [r.entity for r in search_results]
        
        # 3. 检索依赖关系
        dependencies = self._get_related_dependencies(interfaces, max_dependencies)
        
        # 4. 组装上下文
        context = {
            "task_description": task_description,
            "intent": intent,
            "interfaces": interfaces,
            "dependencies": dependencies,
            "suggestions": self._generate_suggestions(interfaces),
            "formatted_context": self._format_context(interfaces, dependencies, include_examples)
        }
        
        return context
    
    def retrieve_for_interface(
        self,
        interface_id: str,
        depth: int = 2,
        include_contracts: bool = True
    ) -> Dict[str, Any]:
        """
        为接口检索完整上下文
        
        Args:
            interface_id: 接口 ID
            depth: 依赖遍历深度
            include_contracts: 是否包含契约
        
        Returns:
            上下文字典
        """
        # 获取主接口
        main_entity = self.persistence.get_entity(interface_id)
        if not main_entity:
            return {"error": f"Interface '{interface_id}' not found"}
        
        # 获取直接依赖
        direct_deps = self.persistence.get_dependencies(interface_id)
        dependent_entities = []
        
        for dep in direct_deps[:depth * 5]:  # 限制数量
            dep_entity = self.persistence.get_entity(dep["target_id"])
            if dep_entity:
                dependent_entities.append(dep_entity)
        
        # 获取依赖此接口的实体
        dependents = self.persistence.get_dependents(interface_id)
        dependent_entities_ids = [self.persistence.get_entity(did) for did in dependents[:5]]
        dependent_entities_ids = [e for e in dependent_entities_ids if e]
        
        # 格式化上下文
        context = {
            "main_interface": main_entity,
            "dependencies": dependent_entities,
            "dependents": dependent_entities_ids,
            "formatted_context": main_entity.format_for_llm(
                include_dependencies=True,
                include_examples=True
            )
        }
        
        return context
    
    def retrieve_related_interfaces(
        self,
        interface_id: str,
        relation_types: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[CodeEntity]:
        """
        检索相关接口（基于依赖关系）
        
        Args:
            interface_id: 接口 ID
            relation_types: 关系类型过滤
            limit: 返回数量限制
        
        Returns:
            相关实体列表
        """
        # 获取依赖关系
        deps = self.persistence.get_dependencies(interface_id)
        
        if relation_types:
            deps = [d for d in deps if d["relation_type"] in relation_types]
        
        # 获取相关实体
        related = []
        for dep in deps[:limit]:
            entity = self.persistence.get_entity(dep["target_id"])
            if entity:
                related.append(entity)
        
        return related
    
    def _understand_intent(self, task_description: str) -> str:
        """理解任务意图"""
        # 提取关键词
        keywords = self._extract_keywords(task_description)
        
        # 构建意图描述
        intent = task_description
        
        # 如果关键词明确，可以增强意图
        if keywords:
            intent += " " + " ".join(keywords[:5])
        
        return intent
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 提取 CamelCase 和 snake_case
        camel_case = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b', text)
        snake_case = re.findall(r'\b[a-z]+_[a-z_]+\b', text)
        code_refs = re.findall(r'`([^`]+)`', text)
        
        keywords = list(set(camel_case + snake_case + code_refs))
        keywords = [k for k in keywords if len(k) > 2]
        
        return keywords[:10]
    
    def _get_related_dependencies(
        self,
        interfaces: List[CodeEntity],
        max_dependencies: int
    ) -> List[Dict]:
        """获取相关依赖关系"""
        all_deps = []
        seen = set()
        
        for interface in interfaces:
            deps = self.persistence.get_dependencies(interface.id)
            for dep in deps:
                dep_key = (dep["source_id"], dep["target_id"], dep["relation_type"])
                if dep_key not in seen:
                    seen.add(dep_key)
                    all_deps.append(dep)
                    if len(all_deps) >= max_dependencies:
                        break
            if len(all_deps) >= max_dependencies:
                break
        
        return all_deps
    
    def _generate_suggestions(self, interfaces: List[CodeEntity]) -> List[str]:
        """生成编码建议"""
        suggestions = []
        
        if not interfaces:
            return suggestions
        
        # 基于接口类型生成建议
        for interface in interfaces[:3]:
            if interface.type.value == "class":
                suggestions.append(f"考虑使用 {interface.name} 类来实现相关功能")
            elif interface.type.value in ("function", "method"):
                suggestions.append(f"可以参考 {interface.name} 方法的实现方式")
        
        # 基于领域生成建议
        domains = set(i.domain for i in interfaces if i.domain)
        if domains:
            suggestions.append(f"涉及领域: {', '.join(domains)}")
        
        return suggestions
    
    def _format_context(
        self,
        interfaces: List[CodeEntity],
        dependencies: List[Dict],
        include_examples: bool
    ) -> str:
        """格式化上下文为 LLM 可读格式"""
        parts = []
        
        parts.append("# 相关接口和依赖\n")
        
        # 接口部分
        if interfaces:
            parts.append("## 相关接口\n")
            for interface in interfaces:
                parts.append(interface.format_for_llm(
                    include_dependencies=False,
                    include_examples=include_examples
                ))
                parts.append("\n---\n")
        
        # 依赖关系部分
        if dependencies:
            parts.append("## 依赖关系\n")
            for dep in dependencies[:10]:
                target = self.persistence.get_entity(dep["target_id"])
                if target:
                    parts.append(f"- **{dep['relation_type']}**: {target.name}")
                    if dep.get("context"):
                        parts.append(f"  ({dep['context']})")
                    parts.append("\n")
        
        return "\n".join(parts)
