"""
AI CodeGen MCP Server

一个专注于代码分析、PRD 管理和验证的 MCP 服务。
编码工作交给 MCP 客户端（如 Cursor/Claude）完成。
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .persistence import PersistenceManager


# ============================================================================
# Data Types
# ============================================================================

class PRDStatus(Enum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass
class SearchResult:
    file: str
    symbol: Optional[str]
    type: str
    line: int
    preview: str
    score: float = 1.0


# ============================================================================
# MCP Server
# ============================================================================

class AICodeGenServer:
    """
    AI CodeGen MCP 服务器
    
    核心工具：
    - index:   索引代码库，构建知识图谱
    - search:  搜索符号、文件、内容
    - inspect: 查看符号或文件的详细信息
    - prd:     PRD 生命周期管理
    - task:    任务规划和追踪
    - verify:  验证代码
    - context: 获取实现任务的上下文
    """
    
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
        self.db = PersistenceManager(workspace_path)
        
        # 延迟加载的组件
        self._parser = None
        self._verifier = None
    
    @property
    def parser(self):
        if self._parser is None:
            from ai_codegen.parser import TreeSitterParser
            self._parser = TreeSitterParser()
        return self._parser
    
    @property
    def verifier(self):
        if self._verifier is None:
            from ai_codegen.verifier import Verifier, VerificationConfig
            self._verifier = Verifier(config=VerificationConfig())
        return self._verifier

    # ========================================================================
    # Tool: index
    # ========================================================================
    
    async def tool_index(
        self,
        paths: List[str] = None,
        extensions: List[str] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        索引代码库
        
        Args:
            paths: 要索引的路径列表（相对于 workspace）
            extensions: 文件扩展名过滤
            force: 是否强制重新索引
        
        Returns:
            索引统计信息
        """
        paths = paths or ["."]
        extensions = extensions or [".py"]
        
        indexed_files = []
        indexed_symbols = []
        errors = []
        
        for rel_path in paths:
            target = self.workspace_path / rel_path
            if not target.exists():
                errors.append(f"Path not found: {rel_path}")
                continue
            
            files = self._collect_files(target, extensions)
            
            for file_path in files:
                try:
                    rel_file = str(file_path.relative_to(self.workspace_path))
                    
                    # 检查是否需要更新
                    if not force:
                        content_hash = self._file_hash(file_path)
                        stored = self.db.get_parse_result(rel_file)
                        if stored and stored.content_hash == content_hash:
                            continue
                    
                    # 解析文件
                    content = file_path.read_text(encoding='utf-8')
                    # 获取语言
                    ext = file_path.suffix
                    lang_map = {'.py': 'python', '.js': 'javascript', '.ts': 'typescript'}
                    language = lang_map.get(ext, 'python')
                    result = self.parser.parse_source(content, str(file_path), language)
                    
                    if result:
                        # 保存解析结果
                        self.db.save_parse_result(
                            file_path=rel_file,
                            content_hash=self._file_hash(file_path),
                            symbols=[s.to_dict() for s in result.symbols],
                            imports=[self._import_to_dict(i) for i in result.imports]
                        )
                        
                        # 保存到知识图谱
                        self._save_to_graph(rel_file, result)
                        
                        indexed_files.append(rel_file)
                        indexed_symbols.extend([s.name for s in result.symbols])
                
                except Exception as e:
                    errors.append(f"{rel_file}: {str(e)[:50]}")
        
        # 提取依赖关系
        if indexed_files:
            self._extract_dependencies()
        
        stats = self.db.get_statistics()
        
        return {
            "indexed": len(indexed_files),
            "symbols": len(indexed_symbols),
            "total_files": stats['parsed_files'],
            "total_nodes": stats['graph_nodes'],
            "total_edges": stats['graph_edges'],
            "errors": errors[:5] if errors else []
        }

    # ========================================================================
    # Tool: search
    # ========================================================================
    
    async def tool_search(
        self,
        query: str,
        type: str = "symbol",
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索代码
        
        Args:
            query: 搜索关键词
            type: 搜索类型 - symbol/file/content/dependency
            limit: 结果数量限制
        
        Returns:
            搜索结果列表
        """
        if type == "symbol":
            return self._search_symbols(query, limit)
        elif type == "file":
            return self._search_files(query, limit)
        elif type == "content":
            return self._search_content(query, limit)
        elif type == "dependency":
            return self._search_dependencies(query, limit)
        else:
            raise ValueError(f"Unknown search type: {type}")
    
    def _search_symbols(self, query: str, limit: int) -> List[Dict]:
        """搜索符号（支持模糊匹配）"""
        results = []
        query_lower = query.lower()
        query_normalized = self._normalize_name(query)
        
        nodes = self.db.query_graph_nodes(node_type=None, limit=500)
        
        for node in nodes:
            name = node.get('name', '')
            name_lower = name.lower()
            name_normalized = self._normalize_name(name)
            
            # 计算匹配分数
            score = self._calculate_match_score(query_lower, query_normalized, name_lower, name_normalized)
            
            if score > 0:
                results.append({
                    "file": node.get('file_path', ''),
                    "symbol": name,
                    "type": node.get('node_type', ''),
                    "line": node.get('properties', {}).get('line', 0),
                    "score": score
                })
        
        results.sort(key=lambda x: (-x['score'], x['symbol']))
        return results[:limit]
    
    def _normalize_name(self, name: str) -> str:
        """将驼峰/下划线命名统一为小写下划线形式"""
        import re
        # 驼峰转下划线: UserService -> user_service
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        normalized = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        # 移除多余下划线
        normalized = re.sub('_+', '_', normalized).strip('_')
        return normalized
    
    def _calculate_match_score(self, query_lower: str, query_norm: str, name_lower: str, name_norm: str) -> float:
        """计算匹配分数"""
        # 精确匹配
        if name_lower == query_lower:
            return 1.0
        # 标准化后精确匹配 (user_service == UserService)
        if name_norm == query_norm:
            return 0.95
        # 子串匹配（原始）
        if query_lower in name_lower:
            return 0.7
        # 子串匹配（标准化）
        if query_norm in name_norm:
            return 0.6
        # 单词级匹配
        query_words = set(query_norm.split('_'))
        name_words = set(name_norm.split('_'))
        if query_words and query_words.issubset(name_words):
            return 0.5
        # 部分单词匹配
        if query_words & name_words:
            overlap = len(query_words & name_words) / len(query_words)
            return 0.3 * overlap
        return 0
    
    def _search_files(self, query: str, limit: int) -> List[Dict]:
        """搜索文件"""
        results = []
        query_lower = query.lower()
        
        for pr in self.db.get_all_parse_results():
            if query_lower in pr.file_path.lower():
                score = 1.0 if query_lower in pr.file_path.split('/')[-1].lower() else 0.5
                results.append({
                    "file": pr.file_path,
                    "symbols": len(pr.symbols),
                    "score": score
                })
        
        results.sort(key=lambda x: (-x['score'], x['file']))
        return results[:limit]
    
    def _search_content(self, query: str, limit: int) -> List[Dict]:
        """搜索文件内容"""
        results = []
        query_lower = query.lower()
        
        for pr in self.db.get_all_parse_results():
            file_path = self.workspace_path / pr.file_path
            if not file_path.exists():
                continue
            
            try:
                lines = file_path.read_text(encoding='utf-8').split('\n')
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        results.append({
                            "file": pr.file_path,
                            "line": i + 1,
                            "content": line.strip()[:100]
                        })
                        if len(results) >= limit:
                            return results
            except:
                pass
        
        return results
    
    def _search_dependencies(self, query: str, limit: int) -> List[Dict]:
        """搜索依赖关系"""
        results = []
        
        # 查找引用此符号的代码
        edges = self.db.query_graph_edges(limit=500)
        
        for edge in edges:
            source = edge.get('source_id', '')
            target = edge.get('target_id', '')
            
            if query.lower() in source.lower() or query.lower() in target.lower():
                results.append({
                    "source": source,
                    "target": target,
                    "type": edge.get('edge_type', ''),
                })
        
        return results[:limit]

    # ========================================================================
    # Tool: inspect
    # ========================================================================
    
    async def tool_inspect(
        self,
        target: str,
        include_source: bool = True,
        include_deps: bool = True
    ) -> Dict[str, Any]:
        """
        查看符号或文件的详细信息
        
        Args:
            target: 文件路径或 "file:symbol" 格式
            include_source: 是否包含源码
            include_deps: 是否包含依赖信息
        
        Returns:
            详细信息
        """
        if ':' in target:
            file_path, symbol_name = target.split(':', 1)
            return self._inspect_symbol(file_path, symbol_name, include_source, include_deps)
        else:
            return self._inspect_file(target, include_source, include_deps)
    
    def _inspect_file(self, file_path: str, include_source: bool, include_deps: bool) -> Dict:
        """查看文件详情"""
        pr = self.db.get_parse_result(file_path)
        if not pr:
            raise ValueError(f"File not indexed: {file_path}")
        
        result = {
            "file": file_path,
            "symbols": pr.symbols,
            "imports": pr.imports,
        }
        
        if include_source:
            full_path = self.workspace_path / file_path
            if full_path.exists():
                result["source"] = full_path.read_text(encoding='utf-8')
        
        if include_deps:
            edges = self.db.query_graph_edges(limit=200)
            deps_in = [e for e in edges if file_path in e.get('target_id', '')]
            deps_out = [e for e in edges if file_path in e.get('source_id', '')]
            result["dependencies"] = {
                "imports": [e['target_id'] for e in deps_out if e['edge_type'] == 'imports'],
                "imported_by": [e['source_id'] for e in deps_in if e['edge_type'] == 'imports'],
            }
        
        return result
    
    def _inspect_symbol(self, file_path: str, symbol_name: str, include_source: bool, include_deps: bool) -> Dict:
        """查看符号详情"""
        pr = self.db.get_parse_result(file_path)
        if not pr:
            raise ValueError(f"File not indexed: {file_path}")
        
        symbol = None
        for s in pr.symbols:
            if s.get('name') == symbol_name:
                symbol = s
                break
        
        if not symbol:
            raise ValueError(f"Symbol not found: {symbol_name} in {file_path}")
        
        result = {
            "file": file_path,
            "symbol": symbol_name,
            "type": symbol.get('symbol_type'),
            "line": symbol.get('start_line'),
            "docstring": symbol.get('docstring'),
        }
        
        if include_source:
            full_path = self.workspace_path / file_path
            if full_path.exists():
                lines = full_path.read_text(encoding='utf-8').split('\n')
                start = symbol.get('start_line', 1) - 1
                end = symbol.get('end_line', start + 10)
                result["source"] = '\n'.join(lines[start:end])
        
        if include_deps:
            node_id = f"{file_path}:{symbol_name}"
            edges = self.db.query_graph_edges(limit=200)
            result["dependencies"] = {
                "uses": [e['target_id'] for e in edges if e.get('source_id') == node_id],
                "used_by": [e['source_id'] for e in edges if e.get('target_id') == node_id],
            }
        
        return result

    # ========================================================================
    # Tool: prd
    # ========================================================================
    
    async def tool_prd(
        self,
        action: str,
        prd_id: str = None,
        content: str = None,
        title: str = None,
        status: str = None
    ) -> Dict[str, Any]:
        """
        PRD 生命周期管理
        
        Args:
            action: create/analyze/list/get/update
            prd_id: PRD ID
            content: PRD 内容 (create/analyze)
            title: PRD 标题 (create)
            status: PRD 状态 (update)
        
        Returns:
            操作结果
        """
        if action == "create":
            return self._prd_create(prd_id or self._generate_id(), title, content)
        elif action == "analyze":
            return await self._prd_analyze(prd_id, content)
        elif action == "list":
            return self._prd_list()
        elif action == "get":
            return self._prd_get(prd_id)
        elif action == "update":
            return self._prd_update(prd_id, status)
        else:
            raise ValueError(f"Unknown PRD action: {action}")
    
    def _prd_create(self, prd_id: str, title: str, content: str) -> Dict:
        """创建 PRD"""
        self.db.save_prd_analysis(
            prd_id=prd_id,
            content=content or "",
            analysis={
                "title": title or prd_id,
                "status": PRDStatus.DRAFT.value,
                "change_points": [],
                "impacted_files": [],
            }
        )
        return {"prd_id": prd_id, "status": "created"}
    
    async def _prd_analyze(self, prd_id: str, content: str = None) -> Dict:
        """分析 PRD，识别影响的代码"""
        stored = self.db.get_prd_analysis(prd_id)
        if not stored and not content:
            raise ValueError(f"PRD not found: {prd_id}")
        
        prd_content = content or stored.content
        
        # 提取关键词
        keywords = self._extract_keywords(prd_content)
        
        # 搜索相关代码
        impacted_files = set()
        impacted_symbols = []
        
        for keyword in keywords:
            # 搜索符号
            for result in self._search_symbols(keyword, 10):
                impacted_files.add(result['file'])
                impacted_symbols.append({
                    "keyword": keyword,
                    "file": result['file'],
                    "symbol": result['symbol'],
                    "type": result['type']
                })
        
        analysis = {
            "title": stored.analysis.get('title', prd_id) if stored else prd_id,
            "status": PRDStatus.ANALYZING.value,
            "keywords": keywords,
            "impacted_files": list(impacted_files),
            "impacted_symbols": impacted_symbols[:20],
            "change_points": self._identify_change_points(impacted_symbols),
        }
        
        self.db.save_prd_analysis(prd_id, prd_content, analysis)
        
        return {
            "prd_id": prd_id,
            "keywords": keywords,
            "impacted_files": len(impacted_files),
            "change_points": analysis['change_points']
        }
    
    def _prd_list(self) -> Dict:
        """列出所有 PRD"""
        prds = []
        for stored in self.db.get_all_prd_analyses():
            prds.append({
                "prd_id": stored.prd_id,
                "title": stored.analysis.get('title', stored.prd_id),
                "status": stored.analysis.get('status', 'unknown'),
            })
        return {"prds": prds, "total": len(prds)}
    
    def _prd_get(self, prd_id: str) -> Dict:
        """获取 PRD 详情"""
        stored = self.db.get_prd_analysis(prd_id)
        if not stored:
            raise ValueError(f"PRD not found: {prd_id}")
        
        return {
            "prd_id": prd_id,
            "content": stored.content,
            "analysis": stored.analysis,
        }
    
    def _prd_update(self, prd_id: str, status: str) -> Dict:
        """更新 PRD 状态"""
        stored = self.db.get_prd_analysis(prd_id)
        if not stored:
            raise ValueError(f"PRD not found: {prd_id}")
        
        analysis = stored.analysis
        analysis['status'] = status
        
        self.db.save_prd_analysis(prd_id, stored.content, analysis)
        
        return {"prd_id": prd_id, "status": status}

    # ========================================================================
    # Tool: task
    # ========================================================================
    
    async def tool_task(
        self,
        action: str,
        prd_id: str = None,
        task_id: str = None,
        title: str = None,
        description: str = None,
        status: str = None,
        files: List[str] = None
    ) -> Dict[str, Any]:
        """
        任务管理
        
        Args:
            action: create/list/get/update
            prd_id: 关联的 PRD ID
            task_id: 任务 ID
            title: 任务标题
            description: 任务描述
            status: 任务状态
            files: 涉及的文件
        
        Returns:
            操作结果
        """
        if action == "create":
            return self._task_create(prd_id, task_id or self._generate_id(), title, description, files)
        elif action == "list":
            return self._task_list(prd_id)
        elif action == "get":
            return self._task_get(task_id)
        elif action == "update":
            return self._task_update(task_id, status)
        elif action == "plan":
            return await self._task_plan(prd_id)
        else:
            raise ValueError(f"Unknown task action: {action}")
    
    def _task_create(self, prd_id: str, task_id: str, title: str, description: str, files: List[str]) -> Dict:
        """创建任务"""
        self.db.save_task(
            task_id=task_id,
            prd_id=prd_id,
            title=title or task_id,
            description=description or "",
            status=TaskStatus.PENDING.value,
            files=files or []
        )
        return {"task_id": task_id, "prd_id": prd_id, "status": "created"}
    
    def _task_list(self, prd_id: str = None) -> Dict:
        """列出任务"""
        tasks = self.db.get_tasks_by_prd(prd_id) if prd_id else self.db.get_all_tasks()
        return {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "prd_id": t.prd_id,
                    "title": t.title,
                    "status": t.status,
                }
                for t in tasks
            ],
            "total": len(tasks)
        }
    
    def _task_get(self, task_id: str) -> Dict:
        """获取任务详情"""
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        
        return {
            "task_id": task.task_id,
            "prd_id": task.prd_id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "files": task.files,
        }
    
    def _task_update(self, task_id: str, status: str) -> Dict:
        """更新任务状态"""
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        
        self.db.update_task_status(task_id, status)
        
        return {"task_id": task_id, "status": status}
    
    async def _task_plan(self, prd_id: str) -> Dict:
        """从 PRD 自动创建任务"""
        prd = self.db.get_prd_analysis(prd_id)
        if not prd:
            raise ValueError(f"PRD not found: {prd_id}")
        
        change_points = prd.analysis.get('change_points', [])
        created_tasks = []
        
        for i, cp in enumerate(change_points):
            task_id = f"{prd_id}_task_{i+1}"
            self._task_create(
                prd_id=prd_id,
                task_id=task_id,
                title=cp.get('description', f"Task {i+1}"),
                description=cp.get('details', ''),
                files=cp.get('files', [])
            )
            created_tasks.append(task_id)
        
        # 更新 PRD 状态
        self._prd_update(prd_id, PRDStatus.PLANNED.value)
        
        return {"prd_id": prd_id, "tasks_created": len(created_tasks), "task_ids": created_tasks}

    # ========================================================================
    # Tool: verify
    # ========================================================================
    
    async def tool_verify(
        self,
        file: str = None,
        checks: List[str] = None
    ) -> Dict[str, Any]:
        """
        验证代码
        
        Args:
            file: 要验证的文件路径
            checks: 验证类型列表 [syntax, type, test]
        
        Returns:
            验证结果
        """
        checks = checks or ["syntax"]
        results = {"file": file, "passed": True, "details": {}}
        
        full_path = self.workspace_path / file if file else None
        
        if "syntax" in checks:
            if full_path and full_path.exists():
                try:
                    code = full_path.read_text(encoding='utf-8')
                    compile(code, file, 'exec')
                    results["details"]["syntax"] = {"passed": True}
                except SyntaxError as e:
                    results["passed"] = False
                    results["details"]["syntax"] = {
                        "passed": False,
                        "error": str(e),
                        "line": e.lineno
                    }
            else:
                results["details"]["syntax"] = {"passed": False, "error": "File not found"}
                results["passed"] = False
        
        if "type" in checks:
            # 调用 mypy 检查
            import subprocess
            try:
                proc = subprocess.run(
                    ["python", "-m", "mypy", "--ignore-missing-imports", str(full_path)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                passed = proc.returncode == 0
                results["details"]["type"] = {
                    "passed": passed,
                    "output": proc.stdout[:500] if proc.stdout else None,
                    "errors": proc.stderr[:500] if proc.stderr else None
                }
                if not passed:
                    results["passed"] = False
            except Exception as e:
                results["details"]["type"] = {"passed": False, "error": str(e)}
        
        if "test" in checks:
            # 运行相关测试
            import subprocess
            try:
                proc = subprocess.run(
                    ["python", "-m", "pytest", "-x", "-v", str(full_path.parent)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(self.workspace_path)
                )
                passed = proc.returncode == 0
                results["details"]["test"] = {
                    "passed": passed,
                    "output": proc.stdout[:1000] if proc.stdout else None,
                }
                if not passed:
                    results["passed"] = False
            except Exception as e:
                results["details"]["test"] = {"passed": False, "error": str(e)}
        
        return results

    # ========================================================================
    # Tool: context
    # ========================================================================
    
    async def tool_context(
        self,
        task_id: str = None,
        files: List[str] = None,
        symbols: List[str] = None,
        max_tokens: int = 8000,
        format: str = "structured",  # structured / prompt
        depth: int = 1  # 依赖遍历深度
    ) -> Dict[str, Any]:
        """
        获取实现任务的上下文
        
        Args:
            task_id: 任务 ID
            files: 指定文件列表
            symbols: 指定符号列表
            max_tokens: 最大 token 数
            format: 输出格式 - structured(结构化) / prompt(可直接用于prompt)
            depth: 依赖遍历深度
        
        Returns:
            上下文信息
        """
        # Token 预算分配
        budget = {
            "task": int(max_tokens * 0.1),       # 10% 任务描述
            "target": int(max_tokens * 0.4),     # 40% 目标文件
            "deps": int(max_tokens * 0.3),       # 30% 依赖代码
            "related": int(max_tokens * 0.2),    # 20% 相关代码
        }
        
        context = {
            "task": None,
            "target_files": [],
            "dependencies": [],
            "related_code": [],
            "summary": {
                "total_files": 0,
                "total_symbols": 0,
                "tokens_used": 0,
            }
        }
        
        tokens_used = 0
        
        # 1. 获取任务信息
        if task_id:
            task = self.db.get_task(task_id)
            if task:
                context["task"] = {
                    "id": task.task_id,
                    "title": task.title,
                    "description": task.description,
                    "files": task.files,
                    "status": task.status,
                }
                files = files or task.files
                tokens_used += self._estimate_tokens(str(context["task"]))
        
        target_files = files or []
        
        # 2. 收集目标文件（主要上下文）
        for file_path in target_files[:5]:
            file_context = self._gather_file_context(file_path, budget["target"] // max(len(target_files), 1))
            if file_context:
                context["target_files"].append(file_context)
                tokens_used += file_context.get("tokens", 0)
        
        # 3. 收集依赖上下文（基于依赖图遍历）
        dep_context = self._gather_dependency_context(target_files, depth, budget["deps"])
        context["dependencies"] = dep_context["items"]
        tokens_used += dep_context["tokens"]
        
        # 4. 收集相关代码（基于符号引用）
        if symbols:
            for sym in symbols[:5]:
                related = self._gather_symbol_context(sym, budget["related"] // max(len(symbols), 1))
                if related:
                    context["related_code"].append(related)
                    tokens_used += related.get("tokens", 0)
        
        # 更新统计
        context["summary"]["total_files"] = len(context["target_files"]) + len(context["dependencies"])
        context["summary"]["total_symbols"] = sum(
            len(f.get("symbols", [])) for f in context["target_files"]
        )
        context["summary"]["tokens_used"] = tokens_used
        context["summary"]["budget"] = budget
        
        # 根据格式返回
        if format == "prompt":
            return self._format_context_for_prompt(context)
        
        return context
    
    def _gather_file_context(self, file_path: str, max_tokens: int) -> Optional[Dict]:
        """收集单个文件的上下文"""
        try:
            pr = self.db.get_parse_result(file_path)
            if not pr:
                return None
            
            full_path = self.workspace_path / file_path
            source = ""
            if full_path.exists():
                source = full_path.read_text(encoding='utf-8')
            
            # 提取关键符号信息
            key_symbols = []
            for s in pr.symbols[:20]:  # 限制符号数量
                sym_info = {
                    "name": s.get("name"),
                    "type": s.get("node_type") or s.get("symbol_type"),
                    "line": s.get("start_line") or (s.get("location", {}).get("start_line")),
                    "docstring": (s.get("docstring") or "")[:100],
                }
                key_symbols.append(sym_info)
            
            # 截断源码到预算
            max_chars = max_tokens * 4
            if len(source) > max_chars:
                source = source[:max_chars] + "\n# ... (truncated)"
            
            return {
                "path": file_path,
                "symbols": key_symbols,
                "imports": pr.imports,
                "source": source,
                "tokens": self._estimate_tokens(source),
            }
        except Exception as e:
            return {"path": file_path, "error": str(e), "tokens": 0}
    
    def _gather_dependency_context(self, files: List[str], depth: int, max_tokens: int) -> Dict:
        """收集依赖上下文"""
        items = []
        tokens_used = 0
        visited = set(files)
        
        # BFS 遍历依赖图
        current_level = files.copy()
        
        for d in range(depth):
            if tokens_used >= max_tokens:
                break
            
            next_level = []
            edges = self.db.query_graph_edges(limit=500)
            
            for file_path in current_level:
                # 找到这个文件的所有导入
                for e in edges:
                    source = e.get('source_id', '')
                    target = e.get('target_id', '')
                    
                    # 文件级导入关系
                    if source == file_path and target not in visited:
                        # 获取被导入文件的摘要
                        dep_info = self._get_file_summary(target)
                        if dep_info:
                            dep_info["imported_by"] = file_path
                            dep_info["depth"] = d + 1
                            items.append(dep_info)
                            tokens_used += dep_info.get("tokens", 0)
                            visited.add(target)
                            next_level.append(target)
                        
                        if tokens_used >= max_tokens:
                            break
            
            current_level = next_level
        
        return {"items": items, "tokens": tokens_used}
    
    def _get_file_summary(self, file_path: str) -> Optional[Dict]:
        """获取文件摘要（用于依赖上下文）"""
        try:
            pr = self.db.get_parse_result(file_path)
            if not pr:
                return None
            
            # 只提取公共符号的签名
            public_symbols = []
            for s in pr.symbols:
                name = s.get("name", "")
                if not name.startswith("_"):  # 只包含公共符号
                    public_symbols.append({
                        "name": name,
                        "type": s.get("node_type") or s.get("symbol_type"),
                        "docstring": (s.get("docstring") or "")[:50],
                    })
            
            summary = f"# {file_path}\n"
            for sym in public_symbols[:10]:
                summary += f"- {sym['type']}: {sym['name']}"
                if sym.get('docstring'):
                    summary += f" - {sym['docstring']}"
                summary += "\n"
            
            return {
                "path": file_path,
                "symbols": public_symbols[:10],
                "summary": summary,
                "tokens": self._estimate_tokens(summary),
            }
        except:
            return None
    
    def _gather_symbol_context(self, symbol_ref: str, max_tokens: int) -> Optional[Dict]:
        """收集符号上下文"""
        if ':' not in symbol_ref:
            return None
        
        try:
            file_path, symbol_name = symbol_ref.split(':', 1)
            info = self._inspect_symbol(file_path, symbol_name, include_source=True, include_deps=True)
            
            source = info.get("source", "")
            if len(source) > max_tokens * 4:
                source = source[:max_tokens * 4] + "\n# ... (truncated)"
            
            return {
                "ref": symbol_ref,
                "file": file_path,
                "symbol": symbol_name,
                "type": info.get("type"),
                "source": source,
                "dependencies": info.get("dependencies", {}),
                "tokens": self._estimate_tokens(source),
            }
        except:
            return None
    
    def _format_context_for_prompt(self, context: Dict) -> Dict:
        """格式化上下文为可直接用于 prompt 的格式"""
        sections = []
        
        # 1. 任务信息
        if context.get("task"):
            task = context["task"]
            sections.append(f"""## Task
**{task.get('title', 'No title')}**

{task.get('description', '')}

Target files: {', '.join(task.get('files', []))}
""")
        
        # 2. 目标文件代码
        if context.get("target_files"):
            sections.append("## Target Files\n")
            for f in context["target_files"]:
                if f.get("source"):
                    sections.append(f"### {f['path']}\n```python\n{f['source']}\n```\n")
        
        # 3. 依赖概览
        if context.get("dependencies"):
            sections.append("## Dependencies\n")
            for dep in context["dependencies"]:
                sections.append(f"### {dep['path']} (depth: {dep.get('depth', 1)})\n")
                sections.append(f"{dep.get('summary', '')}\n")
        
        # 4. 相关代码
        if context.get("related_code"):
            sections.append("## Related Code\n")
            for rel in context["related_code"]:
                if rel.get("source"):
                    sections.append(f"### {rel['ref']}\n```python\n{rel['source']}\n```\n")
        
        prompt_text = "\n".join(sections)
        
        return {
            "prompt": prompt_text,
            "tokens": self._estimate_tokens(prompt_text),
            "summary": context.get("summary", {}),
        }
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数量"""
        if not text:
            return 0
        return len(text) // 4

    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _collect_files(self, path: Path, extensions: List[str]) -> List[Path]:
        """收集指定扩展名的文件"""
        if path.is_file():
            return [path] if path.suffix in extensions else []
        
        files = []
        for ext in extensions:
            files.extend(path.rglob(f"*{ext}"))
        
        # 过滤
        return [
            f for f in files
            if not any(p in str(f) for p in ['.venv', '__pycache__', 'node_modules', '.git'])
        ]
    
    def _file_hash(self, path: Path) -> str:
        """计算文件哈希"""
        content = path.read_bytes()
        return hashlib.md5(content).hexdigest()
    
    def _import_to_dict(self, imp) -> Dict:
        """转换 import 为字典"""
        if isinstance(imp, dict):
            return {"module": imp.get('module', ''), "names": imp.get('names', [])}
        return {"module": getattr(imp, 'module', ''), "names": getattr(imp, 'names', [])}
    
    def _save_to_graph(self, file_path: str, result):
        """保存解析结果到知识图谱"""
        # 保存文件节点
        self.db.save_graph_node(
            node_id=file_path,
            node_type="file",
            name=Path(file_path).name,
            file_path=file_path,
            properties={"symbols": len(result.symbols)}
        )
        
        # 保存符号节点
        for symbol in result.symbols:
            node_id = f"{file_path}:{symbol.name}"
            # 获取符号类型（处理 NodeType enum）
            sym_type = symbol.node_type.value if hasattr(symbol.node_type, 'value') else str(symbol.node_type)
            # 获取行号（从 location 或直接属性）
            line = symbol.location.start_line if hasattr(symbol, 'location') else getattr(symbol, 'start_line', 0)
            self.db.save_graph_node(
                node_id=node_id,
                node_type=sym_type,
                name=symbol.name,
                file_path=file_path,
                properties={
                    "line": line,
                    "docstring": symbol.docstring[:200] if symbol.docstring else None
                }
            )
    
    def _extract_dependencies(self):
        """提取并保存所有代码关系（导入、调用、继承等）"""
        # 获取所有文件
        files = {pr.file_path: pr for pr in self.db.get_all_parse_results()}
        
        # 构建模块映射
        module_map = {}
        for fp in files:
            parts = fp.replace('/', '.').replace('.py', '')
            if parts.endswith('.__init__'):
                parts = parts[:-9]
            module_map[parts] = fp
            module_map[parts.split('.')[-1]] = fp
        
        # 1. 提取 import 关系
        for file_path, pr in files.items():
            for imp in pr.imports:
                module = imp.get('module', '') if isinstance(imp, dict) else ''
                if not module:
                    continue
                
                target = self._resolve_module(module, file_path, module_map)
                if target and target != file_path:
                    self.db.save_graph_edge(
                        source_id=file_path,
                        target_id=target,
                        edge_type="imports",
                        properties={"module": module}
                    )
        
        # 2. 提取调用关系（使用 RelationshipExtractor）
        self._extract_call_relationships(files, module_map)
    
    def _extract_call_relationships(self, files: Dict, module_map: Dict):
        """提取调用关系"""
        try:
            from ai_codegen.parser.relationship_extractor import RelationshipExtractor, RelationType
            
            extractor = RelationshipExtractor()
            
            # 构建符号到文件的映射
            symbol_to_file = {}
            for file_path, pr in files.items():
                for sym in pr.symbols:
                    name = sym.get('name', '')
                    if name:
                        symbol_to_file[name] = file_path
            
            # 对每个文件提取关系
            for file_path in files:
                full_path = self.workspace_path / file_path
                if not full_path.exists():
                    continue
                
                try:
                    source_code = full_path.read_text(encoding='utf-8')
                    ext = full_path.suffix
                    lang_map = {'.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.go': 'go'}
                    language = lang_map.get(ext, 'python')
                    
                    relationships = extractor.extract_relationships(source_code, file_path, language)
                    
                    for rel in relationships:
                        # 尝试解析目标到具体文件
                        target = rel.target
                        target_file = symbol_to_file.get(target)
                        
                        if target_file:
                            target = f"{target_file}:{target}"
                        
                        self.db.save_graph_edge(
                            source_id=rel.source,
                            target_id=target,
                            edge_type=rel.rel_type.value,
                            properties={
                                "line": rel.line,
                                "context": rel.context
                            }
                        )
                except Exception:
                    pass
        except ImportError:
            pass  # 如果 relationship_extractor 不可用，跳过
    
    def _resolve_module(self, module: str, source_file: str, module_map: Dict[str, str]) -> Optional[str]:
        """解析模块名到文件路径"""
        # 直接匹配
        if module in module_map:
            return module_map[module]
        
        # 处理相对导入
        if module.startswith('.'):
            source_dir = str(Path(source_file).parent)
            levels = len(module) - len(module.lstrip('.'))
            base = source_dir
            for _ in range(levels - 1):
                base = str(Path(base).parent)
            
            rel_module = module.lstrip('.')
            if rel_module:
                candidates = [
                    f"{base}/{rel_module.replace('.', '/')}.py",
                    f"{base}/{rel_module.replace('.', '/')}/__init__.py"
                ]
                for c in candidates:
                    if c in module_map.values():
                        return c
        
        # 处理包导入
        parts = module.split('.')
        for i in range(len(parts), 0, -1):
            partial = '.'.join(parts[:i])
            if partial in module_map:
                return module_map[partial]
        
        return None
    
    def _extract_keywords(self, content: str) -> List[str]:
        """从 PRD 内容提取关键词"""
        import re
        
        # 提取代码相关词汇
        words = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b', content)  # CamelCase
        words += re.findall(r'\b[a-z]+_[a-z_]+\b', content)  # snake_case
        words += re.findall(r'`([^`]+)`', content)  # 代码引用
        
        # 去重并过滤
        keywords = list(set(words))
        keywords = [k for k in keywords if len(k) > 2 and k.lower() not in {
            'the', 'and', 'for', 'with', 'this', 'that', 'from', 'import'
        }]
        
        return keywords[:20]
    
    def _identify_change_points(self, symbols: List[Dict]) -> List[Dict]:
        """识别改动点"""
        change_points = []
        files_seen = set()
        
        for sym in symbols:
            file = sym.get('file', '')
            if file not in files_seen:
                files_seen.add(file)
                change_points.append({
                    "file": file,
                    "description": f"修改 {file}",
                    "symbols": [s['symbol'] for s in symbols if s.get('file') == file],
                    "files": [file]
                })
        
        return change_points[:10]
    
    def _generate_id(self) -> str:
        """生成唯一 ID"""
        import time
        return f"{int(time.time() * 1000)}"


# ============================================================================
# MCP Server Setup
# ============================================================================

def create_server(workspace_path: str) -> Server:
    """创建 MCP 服务器"""
    server = Server("ai-codegen")
    ai_server = AICodeGenServer(workspace_path)
    
    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="index",
                description="索引代码库，构建知识图谱。支持增量索引。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要索引的路径列表（相对于 workspace）"
                        },
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "文件扩展名，如 [\".py\", \".js\"]"
                        },
                        "force": {
                            "type": "boolean",
                            "description": "是否强制重新索引"
                        }
                    }
                }
            ),
            Tool(
                name="search",
                description="搜索代码。支持符号、文件、内容、依赖搜索。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词"
                        },
                        "type": {
                            "type": "string",
                            "enum": ["symbol", "file", "content", "dependency"],
                            "description": "搜索类型"
                        },
                        "limit": {
                            "type": "number",
                            "description": "结果数量限制"
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="inspect",
                description="查看文件或符号的详细信息，包括源码和依赖。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "文件路径或 'file:symbol' 格式"
                        },
                        "include_source": {
                            "type": "boolean",
                            "description": "是否包含源码"
                        },
                        "include_deps": {
                            "type": "boolean",
                            "description": "是否包含依赖信息"
                        }
                    },
                    "required": ["target"]
                }
            ),
            Tool(
                name="prd",
                description="PRD 生命周期管理：创建、分析、查询、更新状态。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "analyze", "list", "get", "update"],
                            "description": "操作类型"
                        },
                        "prd_id": {
                            "type": "string",
                            "description": "PRD ID"
                        },
                        "content": {
                            "type": "string",
                            "description": "PRD 内容（create/analyze 时使用）"
                        },
                        "title": {
                            "type": "string",
                            "description": "PRD 标题"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["draft", "analyzing", "planned", "in_progress", "completed", "archived"],
                            "description": "PRD 状态（update 时使用）"
                        }
                    },
                    "required": ["action"]
                }
            ),
            Tool(
                name="task",
                description="任务管理：创建、列表、更新、从 PRD 自动规划。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "list", "get", "update", "plan"],
                            "description": "操作类型"
                        },
                        "prd_id": {
                            "type": "string",
                            "description": "关联的 PRD ID"
                        },
                        "task_id": {
                            "type": "string",
                            "description": "任务 ID"
                        },
                        "title": {
                            "type": "string",
                            "description": "任务标题"
                        },
                        "description": {
                            "type": "string",
                            "description": "任务描述"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "blocked", "cancelled"],
                            "description": "任务状态"
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "涉及的文件"
                        }
                    },
                    "required": ["action"]
                }
            ),
            Tool(
                name="verify",
                description="验证代码：语法检查、类型检查、测试运行。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "要验证的文件路径"
                        },
                        "checks": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["syntax", "type", "test"]
                            },
                            "description": "验证类型列表"
                        }
                    },
                    "required": ["file"]
                }
            ),
            Tool(
                name="context",
                description="获取实现任务的智能上下文，基于依赖图收集相关代码，支持 prompt-ready 格式输出。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务 ID"
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "指定文件列表"
                        },
                        "symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "指定符号列表（file:symbol 格式）"
                        },
                        "max_tokens": {
                            "type": "number",
                            "description": "最大 token 数（默认 8000）"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["structured", "prompt"],
                            "description": "输出格式：structured(结构化) / prompt(可直接用于prompt)"
                        },
                        "depth": {
                            "type": "number",
                            "description": "依赖遍历深度（默认 1）"
                        }
                    }
                }
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            if name == "index":
                result = await ai_server.tool_index(**arguments)
            elif name == "search":
                result = await ai_server.tool_search(**arguments)
            elif name == "inspect":
                result = await ai_server.tool_inspect(**arguments)
            elif name == "prd":
                result = await ai_server.tool_prd(**arguments)
            elif name == "task":
                result = await ai_server.tool_task(**arguments)
            elif name == "verify":
                result = await ai_server.tool_verify(**arguments)
            elif name == "context":
                result = await ai_server.tool_context(**arguments)
            else:
                result = {"error": f"Unknown tool: {name}"}
            
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]
    
    return server


async def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI CodeGen MCP Server')
    parser.add_argument('--workspace', type=str, default='.', help='Workspace path')
    args = parser.parse_args()
    
    workspace = os.path.abspath(args.workspace)
    server = create_server(workspace)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
