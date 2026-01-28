"""
上下文管理器

管理 LLM 代码生成所需的上下文。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
import re


@dataclass
class ContextChunk:
    """
    上下文块
    
    表示一段可用于 LLM 的代码或文本上下文。
    """
    id: str
    content: str
    source: str  # 来源文件或类型
    chunk_type: str  # code, interface, dependency, documentation
    relevance_score: float = 0.0
    tokens_estimate: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "chunk_type": self.chunk_type,
            "relevance_score": self.relevance_score,
            "tokens_estimate": self.tokens_estimate,
            "metadata": self.metadata,
        }


@dataclass
class ContextBudget:
    """
    上下文预算
    
    定义上下文各部分的 token 分配。
    """
    total: int = 128000
    system_prompt: int = 2000
    interfaces: int = 5000
    dependencies: int = 3000
    code_snippets: int = 20000
    task_context: int = 10000
    reserved_output: int = 88000
    
    def remaining(self) -> int:
        """计算剩余可用 token"""
        used = (
            self.system_prompt +
            self.interfaces +
            self.dependencies +
            self.task_context
        )
        return self.total - self.reserved_output - used


class ContextManager:
    """
    上下文管理器
    
    管理代码生成任务的上下文，包括：
    - 接口定义
    - 依赖图
    - 相关代码片段
    - 任务上下文
    """
    
    def __init__(
        self,
        knowledge_graph: Optional[Any] = None,
        interface_registry: Optional[Any] = None,
        budget: Optional[ContextBudget] = None
    ):
        """
        初始化上下文管理器
        
        Args:
            knowledge_graph: 代码知识图谱
            interface_registry: 接口注册表
            budget: 上下文预算配置
        """
        self._knowledge_graph = knowledge_graph
        self._interface_registry = interface_registry
        self._budget = budget or ContextBudget()
        
        self._chunks: List[ContextChunk] = []
        self._used_tokens = 0
    
    def build_context(
        self,
        task: Any,
        related_modules: Optional[List[str]] = None,
        related_interfaces: Optional[List[str]] = None
    ) -> str:
        """
        为任务构建上下文
        
        Args:
            task: 当前任务
            related_modules: 相关模块列表
            related_interfaces: 相关接口列表
            
        Returns:
            str: 格式化的上下文字符串
        """
        self._chunks.clear()
        self._used_tokens = 0
        
        sections = []
        
        # 1. 添加接口定义
        if related_interfaces and self._interface_registry:
            interface_context = self._build_interface_context(related_interfaces)
            if interface_context:
                sections.append(("Interfaces", interface_context))
        
        # 2. 添加依赖图摘要
        if related_modules and self._knowledge_graph:
            dep_context = self._build_dependency_context(related_modules)
            if dep_context:
                sections.append(("Dependencies", dep_context))
        
        # 3. 添加相关代码片段
        if related_modules:
            code_context = self._build_code_context(
                related_modules,
                task.target if hasattr(task, 'target') else ""
            )
            if code_context:
                sections.append(("Related Code", code_context))
        
        # 4. 添加任务特定上下文
        task_context = self._build_task_context(task)
        if task_context:
            sections.append(("Task Context", task_context))
        
        # 格式化输出
        output_parts = []
        for title, content in sections:
            output_parts.append(f"## {title}\n\n{content}")
        
        return "\n\n---\n\n".join(output_parts)
    
    def _build_interface_context(
        self,
        interface_names: List[str]
    ) -> str:
        """构建接口上下文"""
        if not self._interface_registry:
            return ""
        
        context = self._interface_registry.get_context_for_llm(
            interface_names=interface_names,
            include_contracts=True,
            include_examples=False
        )
        
        # 估算 token
        tokens = self._estimate_tokens(context)
        
        if tokens > self._budget.interfaces:
            # 截断
            context = self._truncate_to_tokens(context, self._budget.interfaces)
        
        self._used_tokens += tokens
        
        self._chunks.append(ContextChunk(
            id="interfaces",
            content=context,
            source="interface_registry",
            chunk_type="interface",
            tokens_estimate=tokens,
        ))
        
        return context
    
    def _build_dependency_context(
        self,
        module_names: List[str]
    ) -> str:
        """构建依赖上下文"""
        if not self._knowledge_graph:
            return ""
        
        lines = ["Module dependency graph:\n"]
        
        for module in module_names:
            # 获取模块的依赖
            try:
                nodes, relations = self._knowledge_graph.get_subgraph(
                    f"module:{module}",
                    depth=1,
                    direction="both"
                )
                
                imports = []
                imported_by = []
                
                for rel in relations:
                    if rel.rel_type.value == "IMPORTS":
                        if rel.source_id.endswith(module):
                            imports.append(rel.target_id.split(":")[-1])
                        else:
                            imported_by.append(rel.source_id.split(":")[-1])
                
                lines.append(f"### {module}")
                if imports:
                    lines.append(f"  Imports: {', '.join(imports[:10])}")
                if imported_by:
                    lines.append(f"  Imported by: {', '.join(imported_by[:10])}")
                lines.append("")
            except Exception:
                lines.append(f"### {module}\n  (No dependency info available)\n")
        
        context = "\n".join(lines)
        tokens = self._estimate_tokens(context)
        
        if tokens > self._budget.dependencies:
            context = self._truncate_to_tokens(context, self._budget.dependencies)
        
        self._used_tokens += tokens
        
        self._chunks.append(ContextChunk(
            id="dependencies",
            content=context,
            source="knowledge_graph",
            chunk_type="dependency",
            tokens_estimate=tokens,
        ))
        
        return context
    
    def _build_code_context(
        self,
        module_names: List[str],
        target: str
    ) -> str:
        """构建代码上下文"""
        # 这里应该使用 BM25 或语义搜索来获取相关代码
        # 简化实现：直接列出模块中的主要符号
        
        if not self._knowledge_graph:
            return ""
        
        lines = ["Relevant code symbols:\n"]
        
        for module in module_names:
            try:
                nodes, _ = self._knowledge_graph.get_subgraph(
                    f"module:{module}",
                    depth=1,
                    direction="outgoing"
                )
                
                lines.append(f"### {module}")
                
                for node in nodes:
                    if node.label.value in ("Function", "Method", "Class"):
                        name = node.properties.get("name", "")
                        signature = node.properties.get("signature", "")
                        docstring = node.properties.get("docstring", "")
                        
                        lines.append(f"\n**{name}**")
                        if signature:
                            lines.append(f"```\n{signature}\n```")
                        if docstring:
                            lines.append(f"{docstring[:200]}...")
                
                lines.append("")
            except Exception:
                pass
        
        context = "\n".join(lines)
        tokens = self._estimate_tokens(context)
        
        if tokens > self._budget.code_snippets:
            context = self._truncate_to_tokens(context, self._budget.code_snippets)
        
        self._used_tokens += tokens
        
        self._chunks.append(ContextChunk(
            id="code_snippets",
            content=context,
            source="knowledge_graph",
            chunk_type="code",
            tokens_estimate=tokens,
        ))
        
        return context
    
    def _build_task_context(self, task: Any) -> str:
        """构建任务上下文"""
        lines = []
        
        # 任务基本信息
        if hasattr(task, 'title'):
            lines.append(f"**Task:** {task.title}")
        
        if hasattr(task, 'description'):
            lines.append(f"\n**Description:**\n{task.description}")
        
        if hasattr(task, 'task_type'):
            lines.append(f"\n**Type:** {task.task_type.value}")
        
        if hasattr(task, 'target'):
            lines.append(f"\n**Target:** {task.target}")
        
        # 任务上下文
        if hasattr(task, 'context') and task.context:
            lines.append("\n**Additional Context:**")
            for key, value in task.context.items():
                if isinstance(value, list):
                    lines.append(f"- {key}:")
                    for item in value:
                        lines.append(f"  - {item}")
                else:
                    lines.append(f"- {key}: {value}")
        
        # 输入
        if hasattr(task, 'inputs') and task.inputs:
            lines.append("\n**Inputs:**")
            for key, value in task.inputs.items():
                lines.append(f"- {key}: {value}")
        
        context = "\n".join(lines)
        tokens = self._estimate_tokens(context)
        
        self._used_tokens += tokens
        
        self._chunks.append(ContextChunk(
            id="task_context",
            content=context,
            source="task",
            chunk_type="task",
            tokens_estimate=tokens,
        ))
        
        return context
    
    def _estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数量"""
        # 简单估算：平均每 4 个字符约 1 个 token
        return len(text) // 4
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """截断文本到指定 token 数量"""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        
        # 尝试在段落边界截断
        truncated = text[:max_chars]
        last_newline = truncated.rfind("\n\n")
        
        if last_newline > max_chars * 0.8:
            return truncated[:last_newline] + "\n\n... (truncated)"
        
        return truncated + "\n\n... (truncated)"
    
    def add_chunk(
        self,
        content: str,
        source: str,
        chunk_type: str,
        relevance_score: float = 0.0,
        metadata: Optional[Dict] = None
    ):
        """
        手动添加上下文块
        
        Args:
            content: 内容
            source: 来源
            chunk_type: 类型
            relevance_score: 相关性分数
            metadata: 元数据
        """
        tokens = self._estimate_tokens(content)
        
        self._chunks.append(ContextChunk(
            id=f"chunk-{len(self._chunks)}",
            content=content,
            source=source,
            chunk_type=chunk_type,
            relevance_score=relevance_score,
            tokens_estimate=tokens,
            metadata=metadata or {},
        ))
        
        self._used_tokens += tokens
    
    def get_chunks(self) -> List[ContextChunk]:
        """获取所有上下文块"""
        return self._chunks.copy()
    
    def get_used_tokens(self) -> int:
        """获取已使用的 token 数"""
        return self._used_tokens
    
    def get_remaining_tokens(self) -> int:
        """获取剩余可用 token 数"""
        return self._budget.total - self._budget.reserved_output - self._used_tokens
    
    def search_code(
        self,
        query: str,
        top_k: int = 5
    ) -> List[ContextChunk]:
        """
        搜索相关代码
        
        使用 BM25 或语义搜索找到与查询最相关的代码片段。
        
        Args:
            query: 搜索查询
            top_k: 返回数量
            
        Returns:
            List[ContextChunk]: 相关代码块列表
        """
        if not self._knowledge_graph:
            return []
        
        # 简化实现：使用知识图谱的搜索功能
        from ..graph.query_engine import GraphQueryEngine
        
        try:
            engine = GraphQueryEngine(self._knowledge_graph)
            nodes = engine.search(query)[:top_k]
            
            chunks = []
            for node in nodes:
                content = []
                if node.properties.get("signature"):
                    content.append(node.properties["signature"])
                if node.properties.get("docstring"):
                    content.append(node.properties["docstring"])
                
                if content:
                    chunks.append(ContextChunk(
                        id=node.id,
                        content="\n".join(content),
                        source=node.properties.get("module", "unknown"),
                        chunk_type="code",
                        metadata={"label": node.label.value},
                    ))
            
            return chunks
        except Exception:
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取上下文统计信息"""
        by_type = {}
        for chunk in self._chunks:
            by_type[chunk.chunk_type] = by_type.get(chunk.chunk_type, 0) + chunk.tokens_estimate
        
        return {
            "total_chunks": len(self._chunks),
            "used_tokens": self._used_tokens,
            "remaining_tokens": self.get_remaining_tokens(),
            "tokens_by_type": by_type,
            "budget": {
                "total": self._budget.total,
                "reserved_output": self._budget.reserved_output,
            },
        }
