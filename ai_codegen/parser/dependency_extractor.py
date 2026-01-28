"""
依赖提取器

从解析结果中提取模块间的依赖关系。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from enum import Enum
from pathlib import Path

from .tree_sitter_parser import ParseResult, CodeSymbol, NodeType


class DependencyType(Enum):
    """依赖关系类型"""
    IMPORTS = "imports"
    EXPORTS = "exports"
    CALLS = "calls"
    CALLED_BY = "called_by"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    DEPENDS_ON = "depends_on"
    RETURNS = "returns"
    ACCEPTS = "accepts"


@dataclass
class Dependency:
    """依赖关系"""
    source: str  # 源符号/模块
    target: str  # 目标符号/模块
    dep_type: DependencyType
    location: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.dep_type.value,
            "location": self.location,
            "metadata": self.metadata,
        }


@dataclass
class ModuleInfo:
    """模块信息"""
    path: str
    name: str
    language: str
    symbols: List[CodeSymbol]
    imports: List[Dict[str, Any]]
    exports: List[str]
    dependencies: List[Dependency] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "language": self.language,
            "symbols": [s.to_dict() for s in self.symbols],
            "imports": self.imports,
            "exports": self.exports,
            "dependencies": [d.to_dict() for d in self.dependencies],
        }


class DependencyExtractor:
    """
    依赖提取器
    
    从代码解析结果中提取模块间和符号间的依赖关系。
    """
    
    def __init__(self):
        self._module_cache: Dict[str, ModuleInfo] = {}
        self._symbol_index: Dict[str, CodeSymbol] = {}
        
    def extract_from_parse_results(
        self,
        parse_results: Dict[str, ParseResult],
        base_path: Optional[str] = None
    ) -> Dict[str, ModuleInfo]:
        """
        从多个解析结果中提取依赖
        
        Args:
            parse_results: 文件路径到解析结果的映射
            base_path: 基础路径，用于计算相对模块名
            
        Returns:
            Dict[str, ModuleInfo]: 模块信息映射
        """
        # 第一遍：构建模块信息和符号索引
        for file_path, result in parse_results.items():
            module_name = self._path_to_module_name(file_path, base_path)
            
            module_info = ModuleInfo(
                path=file_path,
                name=module_name,
                language=result.language,
                symbols=result.symbols,
                imports=result.imports,
                exports=result.exports,
            )
            
            self._module_cache[file_path] = module_info
            
            # 索引符号
            for symbol in result.symbols:
                full_name = f"{module_name}.{symbol.name}"
                self._symbol_index[full_name] = symbol
                
                # 也用短名称索引
                self._symbol_index[symbol.name] = symbol
        
        # 第二遍：解析依赖关系
        for file_path, module_info in self._module_cache.items():
            dependencies = self._extract_module_dependencies(module_info)
            module_info.dependencies = dependencies
        
        return self._module_cache
    
    def _path_to_module_name(
        self,
        file_path: str,
        base_path: Optional[str] = None
    ) -> str:
        """将文件路径转换为模块名"""
        path = Path(file_path)
        
        if base_path:
            try:
                path = path.relative_to(base_path)
            except ValueError:
                pass
        
        # 移除扩展名并转换为点分隔
        module_name = str(path.with_suffix(""))
        module_name = module_name.replace("/", ".").replace("\\", ".")
        
        # 清理开头的点
        while module_name.startswith("."):
            module_name = module_name[1:]
            
        return module_name
    
    def _extract_module_dependencies(
        self,
        module_info: ModuleInfo
    ) -> List[Dependency]:
        """提取单个模块的依赖关系"""
        dependencies = []
        
        # 从 import 语句提取依赖
        for imp in module_info.imports:
            target = imp.get("module", "")
            if not target:
                continue
                
            dep = Dependency(
                source=module_info.name,
                target=target,
                dep_type=DependencyType.IMPORTS,
                metadata={"import_info": imp},
            )
            dependencies.append(dep)
        
        # 从类继承提取依赖
        for symbol in module_info.symbols:
            if symbol.node_type == NodeType.CLASS and symbol.signature:
                # 检查是否有继承
                if "(" in symbol.signature:
                    parents = self._extract_class_parents(symbol.signature)
                    for parent in parents:
                        dep = Dependency(
                            source=f"{module_info.name}.{symbol.name}",
                            target=parent,
                            dep_type=DependencyType.EXTENDS,
                            location=symbol.location.to_dict(),
                        )
                        dependencies.append(dep)
        
        return dependencies
    
    def _extract_class_parents(self, signature: str) -> List[str]:
        """从类签名中提取父类"""
        parents = []
        
        # 简单解析 class Foo(Bar, Baz):
        if "(" in signature and ")" in signature:
            start = signature.index("(") + 1
            end = signature.index(")")
            parent_str = signature[start:end]
            
            for parent in parent_str.split(","):
                parent = parent.strip()
                if parent and parent not in ("object", "ABC"):
                    parents.append(parent)
        
        return parents
    
    def get_dependency_graph(self) -> Dict[str, Any]:
        """
        获取完整的依赖图
        
        Returns:
            Dict: 包含节点和边的依赖图
        """
        nodes = []
        edges = []
        
        for module_name, module_info in self._module_cache.items():
            # 添加模块节点
            nodes.append({
                "id": module_info.name,
                "type": "module",
                "path": module_info.path,
                "language": module_info.language,
            })
            
            # 添加符号节点
            for symbol in module_info.symbols:
                full_name = f"{module_info.name}.{symbol.name}"
                nodes.append({
                    "id": full_name,
                    "type": symbol.node_type.value,
                    "name": symbol.name,
                    "module": module_info.name,
                    "signature": symbol.signature,
                    "docstring": symbol.docstring,
                })
            
            # 添加依赖边
            for dep in module_info.dependencies:
                edges.append({
                    "source": dep.source,
                    "target": dep.target,
                    "type": dep.dep_type.value,
                    "metadata": dep.metadata,
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
        }
    
    def find_dependencies(
        self,
        symbol_name: str,
        direction: str = "both"
    ) -> List[Dependency]:
        """
        查找符号的依赖关系
        
        Args:
            symbol_name: 符号名称
            direction: "incoming" | "outgoing" | "both"
            
        Returns:
            List[Dependency]: 依赖列表
        """
        results = []
        
        for module_info in self._module_cache.values():
            for dep in module_info.dependencies:
                if direction in ("outgoing", "both"):
                    if dep.source == symbol_name or dep.source.endswith(f".{symbol_name}"):
                        results.append(dep)
                        
                if direction in ("incoming", "both"):
                    if dep.target == symbol_name or dep.target.endswith(f".{symbol_name}"):
                        results.append(dep)
        
        return results
    
    def get_module_dependencies(
        self,
        module_name: str,
        transitive: bool = False
    ) -> Set[str]:
        """
        获取模块的所有依赖
        
        Args:
            module_name: 模块名
            transitive: 是否包含传递依赖
            
        Returns:
            Set[str]: 依赖的模块集合
        """
        deps = set()
        visited = set()
        
        def collect(name: str):
            if name in visited:
                return
            visited.add(name)
            
            for module_info in self._module_cache.values():
                if module_info.name == name:
                    for dep in module_info.dependencies:
                        if dep.dep_type == DependencyType.IMPORTS:
                            deps.add(dep.target)
                            if transitive:
                                collect(dep.target)
        
        collect(module_name)
        return deps
    
    def export_to_json(self) -> str:
        """导出依赖图为 JSON"""
        import json
        return json.dumps(self.get_dependency_graph(), indent=2)
