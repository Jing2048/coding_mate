"""
接口 Schema 定义

定义接口的结构化描述，用于 LLM 代码生成。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import json

from .contract import Contract


class TypeKind(Enum):
    """类型种类"""
    PRIMITIVE = "primitive"
    ARRAY = "array"
    OBJECT = "object"
    UNION = "union"
    GENERIC = "generic"
    REFERENCE = "reference"
    ANY = "any"
    VOID = "void"


@dataclass
class TypeSchema:
    """
    类型 Schema
    
    描述类型的结构。
    """
    kind: TypeKind
    name: str
    description: Optional[str] = None
    # 数组元素类型
    element_type: Optional["TypeSchema"] = None
    # 对象属性
    properties: Dict[str, "TypeSchema"] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    # 联合类型成员
    union_types: List["TypeSchema"] = field(default_factory=list)
    # 泛型参数
    type_parameters: List["TypeSchema"] = field(default_factory=list)
    # 引用的类型名称
    reference: Optional[str] = None
    # 约束条件
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "kind": self.kind.value,
            "name": self.name,
        }
        
        if self.description:
            result["description"] = self.description
        
        if self.element_type:
            result["element_type"] = self.element_type.to_dict()
        
        if self.properties:
            result["properties"] = {k: v.to_dict() for k, v in self.properties.items()}
        
        if self.required:
            result["required"] = self.required
        
        if self.union_types:
            result["union_types"] = [t.to_dict() for t in self.union_types]
        
        if self.type_parameters:
            result["type_parameters"] = [t.to_dict() for t in self.type_parameters]
        
        if self.reference:
            result["reference"] = self.reference
        
        if self.constraints:
            result["constraints"] = self.constraints
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TypeSchema":
        """从字典创建类型 Schema"""
        return cls(
            kind=TypeKind(data.get("kind", "any")),
            name=data.get("name", ""),
            description=data.get("description"),
            element_type=cls.from_dict(data["element_type"]) if data.get("element_type") else None,
            properties={k: cls.from_dict(v) for k, v in data.get("properties", {}).items()},
            required=data.get("required", []),
            union_types=[cls.from_dict(t) for t in data.get("union_types", [])],
            type_parameters=[cls.from_dict(t) for t in data.get("type_parameters", [])],
            reference=data.get("reference"),
            constraints=data.get("constraints", {}),
        )
    
    @classmethod
    def primitive(cls, name: str, description: Optional[str] = None) -> "TypeSchema":
        """创建基本类型"""
        return cls(kind=TypeKind.PRIMITIVE, name=name, description=description)
    
    @classmethod
    def array(cls, element_type: "TypeSchema", description: Optional[str] = None) -> "TypeSchema":
        """创建数组类型"""
        return cls(
            kind=TypeKind.ARRAY,
            name=f"Array<{element_type.name}>",
            element_type=element_type,
            description=description,
        )
    
    @classmethod
    def object(
        cls,
        name: str,
        properties: Dict[str, "TypeSchema"],
        required: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> "TypeSchema":
        """创建对象类型"""
        return cls(
            kind=TypeKind.OBJECT,
            name=name,
            properties=properties,
            required=required or [],
            description=description,
        )
    
    @classmethod
    def union(cls, types: List["TypeSchema"], description: Optional[str] = None) -> "TypeSchema":
        """创建联合类型"""
        name = " | ".join(t.name for t in types)
        return cls(
            kind=TypeKind.UNION,
            name=name,
            union_types=types,
            description=description,
        )
    
    @classmethod
    def reference(cls, type_name: str, description: Optional[str] = None) -> "TypeSchema":
        """创建类型引用"""
        return cls(
            kind=TypeKind.REFERENCE,
            name=type_name,
            reference=type_name,
            description=description,
        )


@dataclass
class ParameterSchema:
    """
    参数 Schema
    
    描述方法参数。
    """
    name: str
    type_schema: TypeSchema
    description: Optional[str] = None
    default_value: Optional[Any] = None
    required: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type_schema.to_dict(),
            "required": self.required,
        }
        
        if self.description:
            result["description"] = self.description
        
        if self.default_value is not None:
            result["default"] = self.default_value
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParameterSchema":
        """从字典创建参数 Schema"""
        return cls(
            name=data.get("name", ""),
            type_schema=TypeSchema.from_dict(data.get("type", {})),
            description=data.get("description"),
            default_value=data.get("default"),
            required=data.get("required", True),
        )


@dataclass
class MethodSchema:
    """
    方法 Schema
    
    描述接口方法。
    """
    name: str
    description: str = ""
    parameters: List[ParameterSchema] = field(default_factory=list)
    return_type: Optional[TypeSchema] = None
    is_async: bool = False
    is_static: bool = False
    visibility: str = "public"  # public, private, protected
    contract: Optional[Contract] = None
    examples: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "is_async": self.is_async,
            "is_static": self.is_static,
            "visibility": self.visibility,
        }
        
        if self.return_type:
            result["return_type"] = self.return_type.to_dict()
        
        if self.contract:
            result["contract"] = self.contract.to_dict()
        
        if self.examples:
            result["examples"] = self.examples
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MethodSchema":
        """从字典创建方法 Schema"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            parameters=[ParameterSchema.from_dict(p) for p in data.get("parameters", [])],
            return_type=TypeSchema.from_dict(data["return_type"]) if data.get("return_type") else None,
            is_async=data.get("is_async", False),
            is_static=data.get("is_static", False),
            visibility=data.get("visibility", "public"),
            contract=Contract.from_dict(data["contract"]) if data.get("contract") else None,
            examples=data.get("examples", []),
        )
    
    def add_parameter(
        self,
        name: str,
        type_schema: TypeSchema,
        description: Optional[str] = None,
        default_value: Optional[Any] = None,
        required: bool = True
    ) -> "MethodSchema":
        """添加参数"""
        self.parameters.append(ParameterSchema(
            name=name,
            type_schema=type_schema,
            description=description,
            default_value=default_value,
            required=required,
        ))
        return self
    
    def set_return_type(self, type_schema: TypeSchema) -> "MethodSchema":
        """设置返回类型"""
        self.return_type = type_schema
        return self
    
    def set_contract(self, contract: Contract) -> "MethodSchema":
        """设置契约"""
        self.contract = contract
        return self
    
    def add_example(
        self,
        inputs: Dict[str, Any],
        output: Any,
        description: Optional[str] = None
    ) -> "MethodSchema":
        """添加示例"""
        self.examples.append({
            "inputs": inputs,
            "output": output,
            "description": description,
        })
        return self


@dataclass
class InterfaceSchema:
    """
    接口 Schema
    
    描述完整的接口定义。
    """
    name: str
    description: str = ""
    module: str = ""  # 所属模块
    methods: List[MethodSchema] = field(default_factory=list)
    properties: Dict[str, TypeSchema] = field(default_factory=dict)
    extends: List[str] = field(default_factory=list)  # 继承的接口
    type_parameters: List[str] = field(default_factory=list)  # 泛型参数
    invariants: List[str] = field(default_factory=list)  # 类不变量
    
    # 元数据
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    deprecated: bool = False
    deprecation_message: Optional[str] = None
    
    # 边界定义
    boundary: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "module": self.module,
            "methods": [m.to_dict() for m in self.methods],
            "properties": {k: v.to_dict() for k, v in self.properties.items()},
            "extends": self.extends,
            "type_parameters": self.type_parameters,
            "invariants": self.invariants,
            "tags": self.tags,
            "version": self.version,
            "deprecated": self.deprecated,
        }
        
        if self.deprecation_message:
            result["deprecation_message"] = self.deprecation_message
        
        if self.boundary:
            result["boundary"] = self.boundary
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterfaceSchema":
        """从字典创建接口 Schema"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            module=data.get("module", ""),
            methods=[MethodSchema.from_dict(m) for m in data.get("methods", [])],
            properties={k: TypeSchema.from_dict(v) for k, v in data.get("properties", {}).items()},
            extends=data.get("extends", []),
            type_parameters=data.get("type_parameters", []),
            invariants=data.get("invariants", []),
            tags=data.get("tags", []),
            version=data.get("version", "1.0.0"),
            deprecated=data.get("deprecated", False),
            deprecation_message=data.get("deprecation_message"),
            boundary=data.get("boundary", {}),
        )
    
    def add_method(self, method: MethodSchema) -> "InterfaceSchema":
        """添加方法"""
        self.methods.append(method)
        return self
    
    def add_property(self, name: str, type_schema: TypeSchema) -> "InterfaceSchema":
        """添加属性"""
        self.properties[name] = type_schema
        return self
    
    def set_boundary(
        self,
        inputs: List[str],
        outputs: List[str],
        side_effects: Optional[List[str]] = None
    ) -> "InterfaceSchema":
        """设置边界定义"""
        self.boundary = {
            "inputs": inputs,
            "outputs": outputs,
            "side_effects": side_effects or [],
        }
        return self
    
    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> "InterfaceSchema":
        """从 JSON 字符串创建"""
        return cls.from_dict(json.loads(json_str))
    
    def generate_typescript(self) -> str:
        """生成 TypeScript 接口定义"""
        lines = []
        
        # 添加文档注释
        lines.append("/**")
        lines.append(f" * {self.description}")
        if self.boundary:
            lines.append(" * ")
            lines.append(" * @boundary")
            if self.boundary.get("inputs"):
                lines.append(f" *   - 输入: {', '.join(self.boundary['inputs'])}")
            if self.boundary.get("outputs"):
                lines.append(f" *   - 输出: {', '.join(self.boundary['outputs'])}")
            if self.boundary.get("side_effects"):
                lines.append(f" *   - 副作用: {', '.join(self.boundary['side_effects'])}")
        lines.append(" */")
        
        # 接口声明
        type_params = ""
        if self.type_parameters:
            type_params = f"<{', '.join(self.type_parameters)}>"
        
        extends_clause = ""
        if self.extends:
            extends_clause = f" extends {', '.join(self.extends)}"
        
        lines.append(f"export interface {self.name}{type_params}{extends_clause} {{")
        
        # 属性
        for prop_name, prop_type in self.properties.items():
            lines.append(f"  {prop_name}: {self._type_to_ts(prop_type)};")
        
        # 方法
        for method in self.methods:
            lines.append("")
            lines.append(self._method_to_ts(method))
        
        lines.append("}")
        
        return "\n".join(lines)
    
    def _type_to_ts(self, type_schema: TypeSchema) -> str:
        """将类型 Schema 转换为 TypeScript 类型字符串"""
        if type_schema.kind == TypeKind.PRIMITIVE:
            type_map = {
                "string": "string",
                "number": "number",
                "boolean": "boolean",
                "int": "number",
                "float": "number",
                "str": "string",
                "bool": "boolean",
            }
            return type_map.get(type_schema.name.lower(), type_schema.name)
        
        elif type_schema.kind == TypeKind.ARRAY:
            if type_schema.element_type:
                return f"{self._type_to_ts(type_schema.element_type)}[]"
            return "any[]"
        
        elif type_schema.kind == TypeKind.OBJECT:
            if type_schema.properties:
                props = ", ".join(
                    f"{k}: {self._type_to_ts(v)}"
                    for k, v in type_schema.properties.items()
                )
                return f"{{ {props} }}"
            return type_schema.name
        
        elif type_schema.kind == TypeKind.UNION:
            return " | ".join(self._type_to_ts(t) for t in type_schema.union_types)
        
        elif type_schema.kind == TypeKind.REFERENCE:
            return type_schema.reference or type_schema.name
        
        elif type_schema.kind == TypeKind.VOID:
            return "void"
        
        elif type_schema.kind == TypeKind.ANY:
            return "any"
        
        return type_schema.name
    
    def _method_to_ts(self, method: MethodSchema) -> str:
        """将方法 Schema 转换为 TypeScript 方法签名"""
        lines = []
        
        # 文档注释
        lines.append("  /**")
        lines.append(f"   * {method.description}")
        
        # 参数文档
        for param in method.parameters:
            lines.append(f"   * @param {param.name} {param.description or ''}")
        
        # 契约
        if method.contract:
            for pre in method.contract.preconditions:
                lines.append(f"   * @precondition {pre.description}")
            for post in method.contract.postconditions:
                lines.append(f"   * @postcondition {post.description}")
            for throws in method.contract.throws:
                lines.append(f"   * @throws {throws.exception_type} if {throws.condition}")
        
        lines.append("   */")
        
        # 方法签名
        params = ", ".join(
            f"{p.name}{'?' if not p.required else ''}: {self._type_to_ts(p.type_schema)}"
            for p in method.parameters
        )
        
        return_type = self._type_to_ts(method.return_type) if method.return_type else "void"
        
        if method.is_async:
            return_type = f"Promise<{return_type}>"
        
        lines.append(f"  {method.name}({params}): {return_type};")
        
        return "\n".join(lines)
