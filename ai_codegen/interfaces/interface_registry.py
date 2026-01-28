"""
接口注册表

管理所有接口定义，提供查询和验证功能。
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

from .interface_schema import InterfaceSchema, MethodSchema, TypeSchema
from .contract import Contract


@dataclass
class RegistryEntry:
    """注册表条目"""
    schema: InterfaceSchema
    file_path: Optional[str] = None
    last_modified: Optional[float] = None


class InterfaceRegistry:
    """
    接口注册表
    
    管理项目中的所有接口定义。
    """
    
    def __init__(self, base_path: Optional[str] = None):
        """
        初始化注册表
        
        Args:
            base_path: 接口定义文件的基础路径
        """
        self._interfaces: Dict[str, RegistryEntry] = {}
        self._module_index: Dict[str, List[str]] = {}  # module -> interface names
        self._tag_index: Dict[str, List[str]] = {}  # tag -> interface names
        self._base_path = base_path
    
    def register(
        self,
        schema: InterfaceSchema,
        file_path: Optional[str] = None
    ) -> str:
        """
        注册接口
        
        Args:
            schema: 接口 Schema
            file_path: 来源文件路径
            
        Returns:
            str: 接口完整名称
        """
        full_name = f"{schema.module}.{schema.name}" if schema.module else schema.name
        
        self._interfaces[full_name] = RegistryEntry(
            schema=schema,
            file_path=file_path,
            last_modified=os.path.getmtime(file_path) if file_path else None,
        )
        
        # 更新模块索引
        if schema.module:
            if schema.module not in self._module_index:
                self._module_index[schema.module] = []
            if full_name not in self._module_index[schema.module]:
                self._module_index[schema.module].append(full_name)
        
        # 更新标签索引
        for tag in schema.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if full_name not in self._tag_index[tag]:
                self._tag_index[tag].append(full_name)
        
        return full_name
    
    def get(self, name: str) -> Optional[InterfaceSchema]:
        """获取接口定义"""
        entry = self._interfaces.get(name)
        return entry.schema if entry else None
    
    def get_all(self) -> List[InterfaceSchema]:
        """获取所有接口定义"""
        return [entry.schema for entry in self._interfaces.values()]
    
    def get_by_module(self, module: str) -> List[InterfaceSchema]:
        """按模块获取接口"""
        names = self._module_index.get(module, [])
        return [self._interfaces[n].schema for n in names if n in self._interfaces]
    
    def get_by_tag(self, tag: str) -> List[InterfaceSchema]:
        """按标签获取接口"""
        names = self._tag_index.get(tag, [])
        return [self._interfaces[n].schema for n in names if n in self._interfaces]
    
    def find_method(
        self,
        method_name: str
    ) -> List[tuple[InterfaceSchema, MethodSchema]]:
        """
        查找方法
        
        Args:
            method_name: 方法名
            
        Returns:
            List[tuple]: (接口, 方法) 对列表
        """
        results = []
        
        for entry in self._interfaces.values():
            for method in entry.schema.methods:
                if method.name == method_name:
                    results.append((entry.schema, method))
        
        return results
    
    def find_implementations(self, interface_name: str) -> List[str]:
        """
        查找实现某接口的所有接口
        
        Args:
            interface_name: 接口名
            
        Returns:
            List[str]: 实现接口的名称列表
        """
        implementations = []
        
        for name, entry in self._interfaces.items():
            if interface_name in entry.schema.extends:
                implementations.append(name)
        
        return implementations
    
    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """
        获取接口依赖图
        
        Returns:
            Dict: 接口名到其依赖接口列表的映射
        """
        graph = {}
        
        for name, entry in self._interfaces.items():
            graph[name] = list(entry.schema.extends)
        
        return graph
    
    def validate_interface(
        self,
        name: str,
        implementation: Any
    ) -> List[str]:
        """
        验证实现是否符合接口定义
        
        Args:
            name: 接口名
            implementation: 实现对象
            
        Returns:
            List[str]: 验证错误列表
        """
        errors = []
        
        schema = self.get(name)
        if not schema:
            return [f"Interface '{name}' not found"]
        
        # 检查方法
        for method in schema.methods:
            if not hasattr(implementation, method.name):
                errors.append(f"Missing method: {method.name}")
                continue
            
            impl_method = getattr(implementation, method.name)
            
            if not callable(impl_method):
                errors.append(f"{method.name} is not callable")
                continue
            
            # 检查是否为异步方法
            import asyncio
            if method.is_async and not asyncio.iscoroutinefunction(impl_method):
                errors.append(f"{method.name} should be async")
        
        # 检查属性
        for prop_name in schema.properties:
            if not hasattr(implementation, prop_name):
                errors.append(f"Missing property: {prop_name}")
        
        return errors
    
    def load_from_directory(
        self,
        directory: str,
        pattern: str = "*.interface.json"
    ):
        """
        从目录加载接口定义
        
        Args:
            directory: 目录路径
            pattern: 文件匹配模式
        """
        import fnmatch
        
        directory = Path(directory)
        
        for file_path in directory.rglob("*"):
            if fnmatch.fnmatch(file_path.name, pattern):
                self.load_from_file(str(file_path))
    
    def load_from_file(self, file_path: str):
        """
        从文件加载接口定义
        
        Args:
            file_path: 文件路径
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 支持单个接口或接口列表
        if isinstance(data, list):
            for item in data:
                schema = InterfaceSchema.from_dict(item)
                self.register(schema, file_path)
        else:
            schema = InterfaceSchema.from_dict(data)
            self.register(schema, file_path)
    
    def save_to_file(self, file_path: str, interface_name: Optional[str] = None):
        """
        保存接口定义到文件
        
        Args:
            file_path: 文件路径
            interface_name: 接口名（可选，为 None 时保存所有）
        """
        if interface_name:
            schema = self.get(interface_name)
            if not schema:
                raise ValueError(f"Interface '{interface_name}' not found")
            data = schema.to_dict()
        else:
            data = [entry.schema.to_dict() for entry in self._interfaces.values()]
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def generate_typescript_definitions(
        self,
        output_path: str,
        module: Optional[str] = None
    ):
        """
        生成 TypeScript 定义文件
        
        Args:
            output_path: 输出路径
            module: 模块名（可选，为 None 时生成所有）
        """
        if module:
            interfaces = self.get_by_module(module)
        else:
            interfaces = self.get_all()
        
        lines = [
            "// Auto-generated TypeScript definitions",
            "// Do not edit manually",
            "",
        ]
        
        for schema in interfaces:
            lines.append(schema.generate_typescript())
            lines.append("")
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        total_methods = sum(
            len(entry.schema.methods) 
            for entry in self._interfaces.values()
        )
        
        total_with_contracts = sum(
            1 for entry in self._interfaces.values()
            for method in entry.schema.methods
            if method.contract
        )
        
        return {
            "total_interfaces": len(self._interfaces),
            "total_methods": total_methods,
            "methods_with_contracts": total_with_contracts,
            "modules": list(self._module_index.keys()),
            "tags": list(self._tag_index.keys()),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return {
            "interfaces": {
                name: entry.schema.to_dict()
                for name, entry in self._interfaces.items()
            },
            "module_index": self._module_index,
            "tag_index": self._tag_index,
        }
    
    def search(
        self,
        query: str,
        fields: Optional[List[str]] = None
    ) -> List[InterfaceSchema]:
        """
        搜索接口
        
        Args:
            query: 搜索关键词
            fields: 要搜索的字段
        """
        fields = fields or ["name", "description", "module"]
        query_lower = query.lower()
        results = []
        
        for entry in self._interfaces.values():
            schema = entry.schema
            for field in fields:
                value = getattr(schema, field, None)
                if value and query_lower in str(value).lower():
                    results.append(schema)
                    break
        
        return results
    
    def get_context_for_llm(
        self,
        interface_names: Optional[List[str]] = None,
        include_contracts: bool = True,
        include_examples: bool = False
    ) -> str:
        """
        获取用于 LLM 的接口上下文
        
        Args:
            interface_names: 要包含的接口名列表
            include_contracts: 是否包含契约
            include_examples: 是否包含示例
            
        Returns:
            str: 格式化的接口定义文本
        """
        if interface_names:
            schemas = [self.get(name) for name in interface_names if self.get(name)]
        else:
            schemas = self.get_all()
        
        lines = ["# Interface Definitions\n"]
        
        for schema in schemas:
            lines.append(f"## {schema.name}")
            lines.append(f"\n{schema.description}\n")
            
            if schema.boundary:
                lines.append("### Boundary")
                lines.append(f"- Inputs: {', '.join(schema.boundary.get('inputs', []))}")
                lines.append(f"- Outputs: {', '.join(schema.boundary.get('outputs', []))}")
                if schema.boundary.get('side_effects'):
                    lines.append(f"- Side Effects: {', '.join(schema.boundary['side_effects'])}")
                lines.append("")
            
            lines.append("### Methods\n")
            
            for method in schema.methods:
                params = ", ".join(
                    f"{p.name}: {p.type_schema.name}" 
                    for p in method.parameters
                )
                return_type = method.return_type.name if method.return_type else "void"
                async_prefix = "async " if method.is_async else ""
                
                lines.append(f"#### `{async_prefix}{method.name}({params}) -> {return_type}`")
                lines.append(f"\n{method.description}\n")
                
                if include_contracts and method.contract:
                    for pre in method.contract.preconditions:
                        lines.append(f"- **Precondition**: {pre.description}")
                    for post in method.contract.postconditions:
                        lines.append(f"- **Postcondition**: {post.description}")
                    for throws in method.contract.throws:
                        lines.append(f"- **Throws**: `{throws.exception_type}` if {throws.condition}")
                    lines.append("")
                
                if include_examples and method.examples:
                    lines.append("**Examples:**")
                    for i, example in enumerate(method.examples):
                        lines.append(f"```")
                        lines.append(f"Input: {example['inputs']}")
                        lines.append(f"Output: {example['output']}")
                        lines.append(f"```")
                    lines.append("")
            
            lines.append("---\n")
        
        return "\n".join(lines)
