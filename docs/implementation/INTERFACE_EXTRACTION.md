# 接口自动提取 - 实施文档

## 🎯 目标

从代码自动提取接口定义，构建接口注册表，为 RAG 系统和编码辅助提供基础。

---

## 📋 任务清单

### Task 1.1: 接口提取器基础架构

#### 1.1.1 创建 InterfaceExtractor 类

**文件**: `ai_codegen/extractor/interface_extractor.py`

**功能**：
- 从类定义提取接口
- 从模块提取所有接口
- 支持多种语言（Python 优先）

**API 设计**：
```python
class InterfaceExtractor:
    def __init__(self, parser: TreeSitterParser):
        self.parser = parser
    
    def extract_from_class(
        self,
        class_node: Node,
        source_code: str,
        file_path: str
    ) -> Optional[InterfaceSchema]:
        """从类定义提取接口"""
        pass
    
    def extract_from_module(
        self,
        module_path: str
    ) -> List[InterfaceSchema]:
        """从模块提取所有接口"""
        pass
    
    def extract_from_file(
        self,
        file_path: str
    ) -> List[InterfaceSchema]:
        """从文件提取所有接口"""
        pass
```

**实现步骤**：
1. [ ] 创建基础类结构
2. [ ] 实现类节点识别
3. [ ] 实现方法提取
4. [ ] 实现类型解析
5. [ ] 编写单元测试

**测试用例**：
```python
def test_extract_simple_class():
    code = """
    class UserService:
        def get_user(self, user_id: int) -> User:
            pass
    """
    extractor = InterfaceExtractor(parser)
    interfaces = extractor.extract_from_source(code, "test.py")
    assert len(interfaces) == 1
    assert interfaces[0].name == "UserService"
    assert len(interfaces[0].methods) == 1
```

---

#### 1.1.2 方法签名提取

**功能**：
- 提取方法名
- 提取参数（名称、类型、默认值）
- 提取返回类型
- 识别异步方法

**实现**：
```python
def _extract_method(
    self,
    method_node: Node,
    source_code: str
) -> Optional[MethodSchema]:
    """提取方法定义"""
    # 1. 提取方法名
    name = self._extract_method_name(method_node)
    
    # 2. 提取参数
    parameters = self._extract_parameters(method_node, source_code)
    
    # 3. 提取返回类型
    return_type = self._extract_return_type(method_node, source_code)
    
    # 4. 识别异步
    is_async = self._is_async_method(method_node)
    
    # 5. 提取文档字符串
    docstring = self._extract_docstring(method_node, source_code)
    
    return MethodSchema(
        name=name,
        parameters=parameters,
        return_type=return_type,
        is_async=is_async,
        description=docstring
    )
```

**测试用例**：
```python
def test_extract_method_signature():
    code = """
    async def get_user(self, user_id: int, include_profile: bool = False) -> Optional[User]:
        pass
    """
    method = extractor._extract_method(method_node, code)
    assert method.name == "get_user"
    assert method.is_async == True
    assert len(method.parameters) == 2
    assert method.return_type.name == "Optional[User]"
```

---

#### 1.1.3 类型系统集成

**功能**：
- 解析类型注解
- 支持基础类型（int, str, bool）
- 支持复合类型（List, Dict, Optional）
- 支持自定义类型

**实现**：
```python
class TypeExtractor:
    def extract_type(
        self,
        type_node: Node,
        source_code: str
    ) -> TypeSchema:
        """提取类型定义"""
        type_text = source_code[type_node.start_byte:type_node.end_byte]
        
        # 解析类型
        if type_text.startswith("Optional"):
            return self._parse_optional(type_text)
        elif type_text.startswith("List"):
            return self._parse_list(type_text)
        elif type_text.startswith("Dict"):
            return self._parse_dict(type_text)
        else:
            return TypeSchema(name=type_text)
```

---

### Task 1.2: 契约推断

#### 1.2.1 前置条件推断

**功能**：
- 分析参数验证逻辑
- 识别类型检查
- 识别 None 检查
- 识别范围检查

**实现**：
```python
class ContractInferencer:
    def infer_preconditions(
        self,
        method_node: Node,
        source_code: str
    ) -> List[Precondition]:
        """推断前置条件"""
        preconditions = []
        
        # 分析方法体
        body = method_node.child_by_field_name("body")
        
        # 查找参数检查
        for statement in body.children:
            # 类型检查: isinstance(x, int)
            if self._is_type_check(statement):
                preconditions.append(
                    Precondition(description=self._extract_check_description(statement))
                )
            
            # None 检查: if x is None
            if self._is_none_check(statement):
                preconditions.append(
                    Precondition(description="参数不能为 None")
                )
            
            # 范围检查: if x < 0
            if self._is_range_check(statement):
                preconditions.append(
                    Precondition(description=self._extract_range_description(statement))
                )
        
        return preconditions
```

**示例**：
```python
def get_user(self, user_id: int) -> User:
    if user_id <= 0:  # 推断: user_id > 0
        raise ValueError("user_id must be positive")
    if user_id is None:  # 推断: user_id is not None
        raise ValueError("user_id cannot be None")
    ...
```

推断结果：
```python
preconditions = [
    Precondition(description="user_id > 0"),
    Precondition(description="user_id is not None")
]
```

---

#### 1.2.2 后置条件推断

**功能**：
- 分析返回值类型
- 识别状态变化
- 识别副作用

**实现**：
```python
def infer_postconditions(
    self,
    method_node: Node,
    source_code: str
) -> List[Postcondition]:
    """推断后置条件"""
    postconditions = []
    
    # 分析返回语句
    return_statements = self._find_return_statements(method_node)
    
    for ret in return_statements:
        # 返回值类型约束
        if self._returns_not_none(ret):
            postconditions.append(
                Postcondition(description="返回值不为 None")
            )
        
        # 返回值范围约束
        if self._has_range_constraint(ret):
            postconditions.append(
                Postcondition(description=self._extract_range_constraint(ret))
            )
    
    return postconditions
```

---

#### 1.2.3 异常规范推断

**功能**：
- 识别 raise 语句
- 提取异常类型
- 提取异常条件

**实现**：
```python
def infer_throws(
    self,
    method_node: Node,
    source_code: str
) -> List[ThrowsSpec]:
    """推断异常规范"""
    throws = []
    
    # 查找所有 raise 语句
    raise_statements = self._find_raise_statements(method_node)
    
    for raise_stmt in raise_statements:
        exception_type = self._extract_exception_type(raise_stmt)
        condition = self._extract_raise_condition(raise_stmt)
        
        throws.append(ThrowsSpec(
            exception_type=exception_type,
            condition=condition
        ))
    
    return throws
```

---

### Task 1.3: 模块边界识别

#### 1.3.1 公共 API 识别

**功能**：
- 识别模块的公共接口
- 区分公共和私有方法
- 识别模块入口点

**实现**：
```python
class ModuleBoundaryDetector:
    def detect_public_api(
        self,
        module_path: str
    ) -> Dict[str, List[str]]:
        """识别公共 API"""
        # 1. 解析模块
        parse_result = self.parser.parse_file(module_path)
        
        # 2. 识别公共类
        public_classes = [
            cls for cls in parse_result.classes
            if not cls.name.startswith("_")
        ]
        
        # 3. 识别公共函数
        public_functions = [
            func for func in parse_result.functions
            if not func.name.startswith("_")
        ]
        
        return {
            "classes": [cls.name for cls in public_classes],
            "functions": [func.name for func in public_functions]
        }
```

---

#### 1.3.2 依赖分析

**功能**：
- 分析模块的外部依赖（输入）
- 分析模块对外暴露的接口（输出）
- 识别副作用

**实现**：
```python
def detect_boundary(
    self,
    module_path: str
) -> Dict:
    """识别模块边界"""
    # 1. 分析导入（输入）
    imports = self._analyze_imports(module_path)
    
    # 2. 分析导出（输出）
    exports = self._analyze_exports(module_path)
    
    # 3. 识别副作用
    side_effects = self._detect_side_effects(module_path)
    
    return {
        "inputs": imports,  # 外部依赖
        "outputs": exports,  # 对外接口
        "side_effects": side_effects  # 副作用（文件操作、网络请求等）
    }
```

---

### Task 1.4: MCP 工具集成

#### 1.4.1 extract_interfaces 工具

**功能**：从代码提取接口定义

**MCP 工具定义**：
```python
async def tool_extract_interfaces(
    self,
    paths: List[str] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    从代码提取接口定义
    
    Args:
        paths: 要提取的路径列表
        force: 是否强制重新提取
    
    Returns:
        提取统计信息
    """
    extractor = InterfaceExtractor(self.parser)
    registry = InterfaceRegistry()
    
    extracted = []
    for path in paths:
        interfaces = extractor.extract_from_file(path)
        for interface in interfaces:
            registry.register(interface, file_path=path)
            extracted.append(interface.name)
    
    # 保存到数据库
    self.db.save_interfaces(registry.get_all())
    
    return {
        "extracted": len(extracted),
        "interfaces": extracted
    }
```

---

#### 1.4.2 get_interface 工具

**功能**：获取接口详情

**MCP 工具定义**：
```python
async def tool_get_interface(
    self,
    interface_name: str,
    include_contracts: bool = True,
    include_implementations: bool = False
) -> Dict[str, Any]:
    """
    获取接口详情
    
    Args:
        interface_name: 接口名称
        include_contracts: 是否包含契约
        include_implementations: 是否包含实现列表
    
    Returns:
        接口详情
    """
    interface = self.db.get_interface(interface_name)
    if not interface:
        return {"error": f"Interface '{interface_name}' not found"}
    
    result = interface.to_dict()
    
    if include_contracts:
        result["contracts"] = self._get_contracts(interface)
    
    if include_implementations:
        result["implementations"] = self.registry.find_implementations(interface_name)
    
    return result
```

---

#### 1.4.3 list_interfaces 工具

**功能**：列出所有接口

**MCP 工具定义**：
```python
async def tool_list_interfaces(
    self,
    module: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    列出接口
    
    Args:
        module: 按模块过滤
        tag: 按标签过滤
        limit: 返回数量限制
    
    Returns:
        接口列表
    """
    if module:
        interfaces = self.registry.get_by_module(module)
    elif tag:
        interfaces = self.registry.get_by_tag(tag)
    else:
        interfaces = self.registry.get_all()
    
    return {
        "total": len(interfaces),
        "interfaces": [
            {
                "name": i.name,
                "module": i.module,
                "description": i.description,
                "methods_count": len(i.methods)
            }
            for i in interfaces[:limit]
        ]
    }
```

---

## 🧪 测试策略

### 单元测试

1. **接口提取测试**
   - 简单类提取
   - 复杂类提取（继承、泛型）
   - 模块提取

2. **契约推断测试**
   - 前置条件推断
   - 后置条件推断
   - 异常规范推断

3. **边界识别测试**
   - 公共 API 识别
   - 依赖分析
   - 副作用检测

### 集成测试

1. **端到端测试**
   - 从代码到接口定义
   - 接口注册表更新
   - MCP 工具调用

2. **性能测试**
   - 大文件提取速度
   - 批量提取性能
   - 内存使用

---

## 📊 验收标准

### 功能标准

- [ ] 能够从 Python 类自动提取接口定义
- [ ] 能够推断基础的前置/后置条件
- [ ] 能够识别模块边界
- [ ] MCP 工具正常工作

### 质量标准

- [ ] 接口提取准确率 > 80%
- [ ] 契约推断准确率 > 60%
- [ ] 单文件提取时间 < 100ms
- [ ] 单元测试覆盖率 > 80%

---

## 🚀 实施步骤

### Week 1: 基础架构

- [ ] Day 1-2: 创建 InterfaceExtractor 基础类
- [ ] Day 3-4: 实现方法签名提取
- [ ] Day 5: 实现类型系统集成

### Week 2: 契约推断

- [ ] Day 1-2: 实现前置条件推断
- [ ] Day 3-4: 实现后置条件推断
- [ ] Day 5: 实现异常规范推断

### Week 3: 边界识别与集成

- [ ] Day 1-2: 实现模块边界识别
- [ ] Day 3: MCP 工具集成
- [ ] Day 4-5: 测试与优化

---

## 📝 文档要求

1. **API 文档**
   - InterfaceExtractor 使用指南
   - ContractInferencer 使用指南
   - MCP 工具文档

2. **示例代码**
   - 接口提取示例
   - 契约推断示例
   - 完整工作流示例

3. **测试报告**
   - 准确率统计
   - 性能指标
   - 已知限制

---

**状态**: 待开始  
**负责人**: TBD  
**预计完成**: Week 3
