"""
代码实体数据模型

统一的数据模型，用于表示代码知识，支持 RAG 存储和 LLM 利用。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import json


class EntityType(Enum):
    """实体类型"""
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"


class RelationType(Enum):
    """关系类型"""
    CALLS = "calls"
    IMPORTS = "imports"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    INSTANTIATES = "instantiates"
    USES = "uses"


@dataclass
class TypeInfo:
    """类型信息"""
    name: str
    is_optional: bool = False
    is_generic: bool = False
    generic_args: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        # 如果名称已经包含 Optional，不再重复添加
        if "Optional" in self.name:
            return self.name
        if self.is_optional:
            return f"Optional[{self.name}]"
        if self.is_generic and self.generic_args:
            return f"{self.name}[{', '.join(self.generic_args)}]"
        return self.name


@dataclass
class Parameter:
    """参数定义"""
    name: str
    type: TypeInfo
    default: Optional[str] = None
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": str(self.type),
            "default": self.default,
            "description": self.description
        }


@dataclass
class Signature:
    """方法签名"""
    name: str
    parameters: List[Parameter]
    return_type: Optional[TypeInfo] = None
    is_async: bool = False
    is_static: bool = False
    is_abstract: bool = False
    
    def format(self) -> str:
        """格式化为字符串"""
        params = ", ".join(f"{p.name}: {p.type}" for p in self.parameters)
        ret = f" -> {self.return_type}" if self.return_type else ""
        async_prefix = "async " if self.is_async else ""
        static_prefix = "static " if self.is_static else ""
        return f"{async_prefix}{static_prefix}{self.name}({params}){ret}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "parameters": [p.to_dict() for p in self.parameters],
            "return_type": str(self.return_type) if self.return_type else None,
            "is_async": self.is_async,
            "is_static": self.is_static,
            "is_abstract": self.is_abstract
        }


@dataclass
class ThrowSpec:
    """异常规范"""
    exception_type: str
    condition: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exception_type": self.exception_type,
            "condition": self.condition
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThrowSpec":
        return cls(
            exception_type=data["exception_type"],
            condition=data["condition"]
        )


@dataclass
class Contract:
    """契约定义"""
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    throws: List[ThrowSpec] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "throws": [t.to_dict() for t in self.throws],
            "invariants": self.invariants
        }


@dataclass
class Boundary:
    """模块边界"""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "inputs": self.inputs,
            "outputs": self.outputs,
            "side_effects": self.side_effects
        }


@dataclass
class Dependency:
    """依赖关系"""
    target_id: str
    relation_type: RelationType
    context: str = ""
    line: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "context": self.context,
            "line": self.line
        }


@dataclass
class CodeEntity:
    """
    代码实体 - 统一的数据模型
    
    用于表示代码知识，支持 RAG 存储和 LLM 利用。
    """
    
    # ========== 标识信息 ==========
    id: str                    # 唯一标识: "module:Class.method" 或 "module:function"
    type: EntityType           # 实体类型
    name: str                  # 名称
    module: str                # 模块路径
    file_path: str             # 文件路径
    
    # ========== 语义信息 ==========
    description: str = ""      # 描述（从文档字符串提取）
    purpose: str = ""          # 用途（推断或标注）
    domain: str = ""           # 领域（如: "authentication", "data_access"）
    
    # ========== 接口定义 ==========
    signature: Optional[Signature] = None  # 方法签名（如果是函数/方法）
    contract: Contract = field(default_factory=Contract)  # 契约
    boundary: Boundary = field(default_factory=Boundary)  # 边界
    
    # ========== 依赖关系 ==========
    dependencies: List[Dependency] = field(default_factory=list)  # 依赖的其他实体
    dependents: List[str] = field(default_factory=list)  # 依赖此实体的实体 ID 列表
    
    # ========== 代码片段 ==========
    source_snippet: str = ""   # 关键代码片段（不是完整源码）
    examples: List[str] = field(default_factory=list)  # 使用示例
    
    # ========== 元数据 ==========
    tags: List[str] = field(default_factory=list)  # 标签
    complexity: int = 1        # 复杂度评分 (1-10)
    last_modified: float = 0.0  # 最后修改时间戳
    
    # ========== 向量化字段 ==========
    embedding_text: str = ""   # 用于向量化的文本（自动生成）
    
    def generate_embedding_text(self) -> str:
        """生成用于向量化的文本"""
        parts = []
        
        # 1. 核心标识
        parts.append(self.name)
        if self.type in (EntityType.METHOD, EntityType.FUNCTION):
            parts.append(f"{self.module}.{self.name}")
        
        # 2. 描述信息
        if self.description:
            parts.append(self.description)
        if self.purpose:
            parts.append(self.purpose)
        
        # 3. 领域信息
        if self.domain:
            parts.append(self.domain)
        
        # 4. 签名信息（方法/函数）
        if self.signature:
            params_str = ", ".join(f"{p.name}: {p.type}" for p in self.signature.parameters)
            parts.append(f"参数: {params_str}")
            if self.signature.return_type:
                parts.append(f"返回: {self.signature.return_type}")
            if self.signature.is_async:
                parts.append("异步方法")
        
        # 5. 契约信息（关键约束）
        if self.contract:
            if self.contract.preconditions:
                parts.append(f"前置条件: {' '.join(self.contract.preconditions)}")
            if self.contract.postconditions:
                parts.append(f"后置条件: {' '.join(self.contract.postconditions)}")
        
        # 6. 边界信息
        if self.boundary:
            if self.boundary.inputs:
                parts.append(f"依赖: {', '.join(self.boundary.inputs)}")
            if self.boundary.outputs:
                parts.append(f"输出: {', '.join(self.boundary.outputs)}")
        
        # 7. 标签
        if self.tags:
            parts.extend(self.tags)
        
        self.embedding_text = " ".join(parts)
        return self.embedding_text
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "module": self.module,
            "file_path": self.file_path,
            "description": self.description,
            "purpose": self.purpose,
            "domain": self.domain,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "dependents": self.dependents,
            "source_snippet": self.source_snippet,
            "examples": self.examples,
            "tags": self.tags,
            "complexity": self.complexity,
            "last_modified": self.last_modified,
            "embedding_text": self.embedding_text or self.generate_embedding_text()
        }
        
        if self.signature:
            result["signature"] = self.signature.to_dict()
        
        result["contract"] = self.contract.to_dict()
        result["boundary"] = self.boundary.to_dict()
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeEntity":
        """从字典创建"""
        # 基础字段
        entity = cls(
            id=data["id"],
            type=EntityType(data["type"]),
            name=data["name"],
            module=data["module"],
            file_path=data["file_path"],
            description=data.get("description", ""),
            purpose=data.get("purpose", ""),
            domain=data.get("domain", ""),
            source_snippet=data.get("source_snippet", ""),
            examples=data.get("examples", []),
            tags=data.get("tags", []),
            complexity=data.get("complexity", 1),
            last_modified=data.get("last_modified", 0.0),
            embedding_text=data.get("embedding_text", "")
        )
        
        # 签名
        if "signature" in data:
            sig_data = data["signature"]
            entity.signature = Signature(
                name=sig_data["name"],
                parameters=[
                    Parameter(
                        name=p["name"],
                        type=TypeInfo(name=p["type"]),
                        default=p.get("default"),
                        description=p.get("description", "")
                    )
                    for p in sig_data.get("parameters", [])
                ],
                return_type=TypeInfo(name=sig_data["return_type"]) if sig_data.get("return_type") else None,
                is_async=sig_data.get("is_async", False),
                is_static=sig_data.get("is_static", False),
                is_abstract=sig_data.get("is_abstract", False)
            )
        
        # 契约
        if "contract" in data:
            contract_data = data["contract"]
            throws_list = []
            for t in contract_data.get("throws", []):
                if isinstance(t, dict):
                    throws_list.append(ThrowSpec.from_dict(t))
                else:
                    throws_list.append(ThrowSpec(exception_type=str(t), condition=""))
            entity.contract = Contract(
                preconditions=contract_data.get("preconditions", []),
                postconditions=contract_data.get("postconditions", []),
                throws=throws_list,
                invariants=contract_data.get("invariants", [])
            )
        
        # 边界
        if "boundary" in data:
            boundary_data = data["boundary"]
            entity.boundary = Boundary(
                inputs=boundary_data.get("inputs", []),
                outputs=boundary_data.get("outputs", []),
                side_effects=boundary_data.get("side_effects", [])
            )
        
        # 依赖
        if "dependencies" in data:
            entity.dependencies = [
                Dependency(
                    target_id=d["target_id"],
                    relation_type=RelationType(d["relation_type"]),
                    context=d.get("context", ""),
                    line=d.get("line", 0)
                )
                for d in data["dependencies"]
            ]
        
        entity.dependents = data.get("dependents", [])
        
        return entity
    
    def format_for_llm(self, include_dependencies: bool = True, include_examples: bool = True) -> str:
        """格式化为 LLM 可读的文本"""
        parts = []
        
        # 1. 实体定义
        parts.append(f"## {self.name}")
        if self.description:
            parts.append(f"\n{self.description}\n")
        
        # 2. 签名（如果是方法）
        if self.signature:
            parts.append("```python")
            parts.append(self.signature.format())
            parts.append("```\n")
        
        # 3. 契约
        if self.contract and (self.contract.preconditions or self.contract.postconditions):
            parts.append("### 契约要求")
            for pre in self.contract.preconditions:
                parts.append(f"- 前置条件: {pre}")
            for post in self.contract.postconditions:
                parts.append(f"- 后置条件: {post}")
            if self.contract.throws:
                for throw in self.contract.throws:
                    parts.append(f"- 异常: {throw.exception_type} ({throw.condition})")
            parts.append("")
        
        # 4. 依赖关系
        if include_dependencies and self.dependencies:
            parts.append("### 依赖关系")
            for dep in self.dependencies[:5]:  # 限制数量
                parts.append(f"- {dep.relation_type.value}: {dep.target_id} ({dep.context})")
            parts.append("")
        
        # 5. 使用示例
        if include_examples and self.examples:
            parts.append("### 使用示例")
            for example in self.examples[:3]:
                parts.append(f"```python\n{example}\n```")
        
        return "\n".join(parts)
