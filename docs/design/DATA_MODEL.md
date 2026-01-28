# 数据模型设计 - RAG 存储与 LLM 利用

## 🎯 设计目标

### 核心原则

1. **简洁性** - 避免冗余，只存储必要信息
2. **语义丰富** - 包含足够的上下文和语义信息
3. **LLM 友好** - 易于 LLM 理解和利用
4. **向量化友好** - 适合嵌入和语义搜索

---

## 📊 统一数据模型

### 核心实体：CodeEntity

所有代码知识统一表示为 `CodeEntity`，包含：

```python
@dataclass
class CodeEntity:
    """代码实体 - 统一的数据模型"""
    
    # ========== 标识信息 ==========
    id: str                    # 唯一标识: "module:Class.method" 或 "module:function"
    type: EntityType           # 实体类型: CLASS, FUNCTION, MODULE, INTERFACE
    name: str                  # 名称: "UserService", "get_user"
    module: str                # 模块路径: "services.user"
    file_path: str             # 文件路径: "src/services/user.py"
    
    # ========== 语义信息 ==========
    description: str           # 描述（从文档字符串提取）
    purpose: str               # 用途（推断或标注）
    domain: str                # 领域（如: "authentication", "data_access"）
    
    # ========== 接口定义 ==========
    signature: Signature        # 方法签名（如果是函数/方法）
    contract: Contract         # 契约（前置/后置条件）
    boundary: Boundary         # 边界（输入/输出）
    
    # ========== 依赖关系 ==========
    dependencies: List[Dependency]  # 依赖的其他实体
    dependents: List[str]            # 依赖此实体的实体 ID 列表
    
    # ========== 代码片段 ==========
    source_snippet: str         # 关键代码片段（不是完整源码）
    examples: List[str]         # 使用示例
    
    # ========== 元数据 ==========
    tags: List[str]            # 标签: ["async", "public", "core"]
    complexity: int             # 复杂度评分 (1-10)
    last_modified: float        # 最后修改时间戳
    
    # ========== 向量化字段 ==========
    embedding_text: str         # 用于向量化的文本（自动生成）
```

---

## 🔍 详细字段定义

### EntityType

```python
class EntityType(Enum):
    """实体类型"""
    MODULE = "module"           # 模块
    CLASS = "class"             # 类
    INTERFACE = "interface"     # 接口
    FUNCTION = "function"        # 函数
    METHOD = "method"           # 方法
    PROPERTY = "property"       # 属性
```

### Signature

```python
@dataclass
class Signature:
    """方法签名"""
    name: str
    parameters: List[Parameter]
    return_type: Optional[TypeInfo]
    is_async: bool = False
    is_static: bool = False
    is_abstract: bool = False

@dataclass
class Parameter:
    """参数定义"""
    name: str
    type: TypeInfo
    default: Optional[str] = None
    description: str = ""

@dataclass
class TypeInfo:
    """类型信息"""
    name: str                   # "int", "User", "List[User]"
    is_optional: bool = False
    is_generic: bool = False
    generic_args: List[str] = field(default_factory=list)
```

### Contract

```python
@dataclass
class Contract:
    """契约定义"""
    preconditions: List[str]    # 前置条件描述
    postconditions: List[str]  # 后置条件描述
    throws: List[ThrowSpec]    # 异常规范
    invariants: List[str]       # 不变量

@dataclass
class ThrowSpec:
    """异常规范"""
    exception_type: str        # "ValueError"
    condition: str             # "当 user_id <= 0 时"
```

### Boundary

```python
@dataclass
class Boundary:
    """模块边界"""
    inputs: List[str]          # 输入依赖: ["Database", "Cache"]
    outputs: List[str]         # 输出接口: ["User", "UserList"]
    side_effects: List[str]    # 副作用: ["file_write", "network_request"]
```

### Dependency

```python
@dataclass
class Dependency:
    """依赖关系"""
    target_id: str             # 目标实体 ID
    relation_type: RelationType  # 关系类型
    context: str               # 依赖上下文（调用位置、用途）
    line: int                  # 代码行号

class RelationType(Enum):
    """关系类型"""
    CALLS = "calls"            # 调用
    IMPORTS = "imports"        # 导入
    EXTENDS = "extends"        # 继承
    IMPLEMENTS = "implements"  # 实现
    INSTANTIATES = "instantiates"  # 实例化
    USES = "uses"              # 使用（属性访问等）
```

---

## 📝 数据模型示例

### 示例 1: 类实体

```python
CodeEntity(
    id="services.user:UserService",
    type=EntityType.CLASS,
    name="UserService",
    module="services.user",
    file_path="src/services/user.py",
    
    description="用户服务类，提供用户相关的业务逻辑",
    purpose="管理用户数据的增删改查操作",
    domain="user_management",
    
    signature=None,  # 类没有签名
    contract=Contract(
        preconditions=[],
        postconditions=[],
        throws=[],
        invariants=["数据库连接必须有效"]
    ),
    boundary=Boundary(
        inputs=["Database", "Cache", "Logger"],
        outputs=["User", "UserList"],
        side_effects=["database_query", "cache_write"]
    ),
    
    dependencies=[
        Dependency(
            target_id="db:Database",
            relation_type=RelationType.USES,
            context="用于查询用户数据",
            line=15
        ),
        Dependency(
            target_id="models.user:User",
            relation_type=RelationType.USES,
            context="返回用户对象",
            line=20
        )
    ],
    dependents=["controllers.user:UserController"],
    
    source_snippet="""
    class UserService:
        def __init__(self, db: Database):
            self.db = db
        
        async def get_user(self, user_id: int) -> Optional[User]:
            return await self.db.query(User, id=user_id)
    """,
    examples=[
        "service = UserService(db)\nuser = await service.get_user(123)"
    ],
    
    tags=["service", "async", "public"],
    complexity=3,
    last_modified=1706457600.0,
    
    embedding_text="UserService 用户服务类 提供用户相关的业务逻辑 管理用户数据的增删改查操作 user_management"
)
```

### 示例 2: 方法实体

```python
CodeEntity(
    id="services.user:UserService.get_user",
    type=EntityType.METHOD,
    name="get_user",
    module="services.user",
    file_path="src/services/user.py",
    
    description="根据用户 ID 获取用户信息",
    purpose="查询单个用户数据",
    domain="user_management",
    
    signature=Signature(
        name="get_user",
        parameters=[
            Parameter(
                name="user_id",
                type=TypeInfo(name="int", is_optional=False),
                description="用户 ID，必须大于 0"
            )
        ],
        return_type=TypeInfo(name="Optional[User]", is_optional=True),
        is_async=True
    ),
    contract=Contract(
        preconditions=[
            "user_id > 0",
            "user_id is not None"
        ],
        postconditions=[
            "如果用户存在，返回 User 对象",
            "如果用户不存在，返回 None"
        ],
        throws=[
            ThrowSpec(
                exception_type="ValueError",
                condition="当 user_id <= 0 时"
            )
        ],
        invariants=[]
    ),
    boundary=Boundary(
        inputs=["Database"],
        outputs=["User"],
        side_effects=["database_query"]
    ),
    
    dependencies=[
        Dependency(
            target_id="db:Database.query",
            relation_type=RelationType.CALLS,
            context="查询用户数据",
            line=25
        )
    ],
    dependents=["controllers.user:UserController.get"],
    
    source_snippet="""
    async def get_user(self, user_id: int) -> Optional[User]:
        if user_id <= 0:
            raise ValueError("user_id must be positive")
        return await self.db.query(User, id=user_id)
    """,
    examples=[
        "user = await service.get_user(123)"
    ],
    
    tags=["async", "public", "query"],
    complexity=2,
    last_modified=1706457600.0,
    
    embedding_text="get_user 根据用户 ID 获取用户信息 查询单个用户数据 user_management async 返回 Optional[User] user_id > 0"
)
```

---

## 🔄 数据流转

### 1. 提取阶段

```
源代码
  ↓
[代码解析器]
  ↓
AST + 符号信息
  ↓
[实体提取器]
  ↓
CodeEntity 列表
```

### 2. 增强阶段

```
CodeEntity (基础)
  ↓
[语义增强]
  - 推断 purpose
  - 识别 domain
  - 提取 contract
  - 分析 boundary
  ↓
CodeEntity (完整)
```

### 3. 向量化阶段

```
CodeEntity
  ↓
[生成 embedding_text]
  - 组合 description + purpose + domain + signature
  - 包含关键语义信息
  ↓
embedding_text
  ↓
[向量化]
  ↓
向量嵌入
```

### 4. 存储阶段

```
CodeEntity
  ↓
[分离存储]
  ├─ 结构化数据 (SQLite)
  │   - 基础信息
  │   - 关系数据
  │
  └─ 向量数据 (Vector DB)
      - embedding_text
      - 向量嵌入
```

---

## 📦 存储策略

### 结构化存储 (SQLite)

**表结构**：

```sql
-- 实体表
CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    module TEXT,
    file_path TEXT,
    description TEXT,
    purpose TEXT,
    domain TEXT,
    tags TEXT,  -- JSON array
    complexity INTEGER,
    last_modified REAL,
    embedding_text TEXT
);

-- 签名表（方法/函数）
CREATE TABLE signatures (
    entity_id TEXT PRIMARY KEY,
    name TEXT,
    parameters TEXT,  -- JSON
    return_type TEXT,
    is_async BOOLEAN,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- 契约表
CREATE TABLE contracts (
    entity_id TEXT PRIMARY KEY,
    preconditions TEXT,  -- JSON array
    postconditions TEXT,  -- JSON array
    throws TEXT,  -- JSON array
    invariants TEXT,  -- JSON array
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- 边界表
CREATE TABLE boundaries (
    entity_id TEXT PRIMARY KEY,
    inputs TEXT,  -- JSON array
    outputs TEXT,  -- JSON array
    side_effects TEXT,  -- JSON array
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- 依赖关系表
CREATE TABLE dependencies (
    source_id TEXT,
    target_id TEXT,
    relation_type TEXT,
    context TEXT,
    line INTEGER,
    PRIMARY KEY (source_id, target_id, relation_type),
    FOREIGN KEY (source_id) REFERENCES entities(id),
    FOREIGN KEY (target_id) REFERENCES entities(id)
);
```

### 向量存储 (Vector DB)

**集合结构**：

```python
# Chroma 集合
collection = {
    "name": "code_entities",
    "metadata": {
        "description": "代码实体向量集合"
    }
}

# 文档结构
document = {
    "id": "services.user:UserService.get_user",
    "embedding": [0.123, 0.456, ...],  # 向量
    "metadata": {
        "type": "method",
        "module": "services.user",
        "domain": "user_management",
        "tags": ["async", "public"],
        "complexity": 2
    },
    "text": "get_user 根据用户 ID 获取用户信息 查询单个用户数据..."
}
```

---

## 🎯 embedding_text 生成策略

### 生成规则

```python
def generate_embedding_text(entity: CodeEntity) -> str:
    """生成用于向量化的文本"""
    parts = []
    
    # 1. 核心标识
    parts.append(entity.name)
    if entity.type == EntityType.METHOD:
        parts.append(f"{entity.module}.{entity.name}")
    
    # 2. 描述信息
    if entity.description:
        parts.append(entity.description)
    if entity.purpose:
        parts.append(entity.purpose)
    
    # 3. 领域信息
    if entity.domain:
        parts.append(entity.domain)
    
    # 4. 签名信息（方法/函数）
    if entity.signature:
        parts.append(f"参数: {format_parameters(entity.signature.parameters)}")
        if entity.signature.return_type:
            parts.append(f"返回: {entity.signature.return_type.name}")
        if entity.signature.is_async:
            parts.append("异步方法")
    
    # 5. 契约信息（关键约束）
    if entity.contract:
        if entity.contract.preconditions:
            parts.append(f"前置条件: {' '.join(entity.contract.preconditions)}")
        if entity.contract.postconditions:
            parts.append(f"后置条件: {' '.join(entity.contract.postconditions)}")
    
    # 6. 边界信息
    if entity.boundary:
        if entity.boundary.inputs:
            parts.append(f"依赖: {', '.join(entity.boundary.inputs)}")
        if entity.boundary.outputs:
            parts.append(f"输出: {', '.join(entity.boundary.outputs)}")
    
    # 7. 标签
    if entity.tags:
        parts.extend(entity.tags)
    
    return " ".join(parts)
```

### 示例输出

```
# 方法实体
"get_user services.user.UserService.get_user 根据用户 ID 获取用户信息 查询单个用户数据 user_management 参数: user_id: int 返回: Optional[User] 异步方法 前置条件: user_id > 0 后置条件: 如果用户存在返回 User 对象 依赖: Database 输出: User async public query"

# 类实体
"UserService services.user.UserService 用户服务类 提供用户相关的业务逻辑 管理用户数据的增删改查操作 user_management 依赖: Database, Cache, Logger 输出: User, UserList service async public"
```

---

## 🔍 LLM 利用策略

### 1. 语义搜索

```python
# 用户查询
query = "需要验证用户输入的服务"

# 向量搜索
results = vector_store.search(
    query=query,
    n_results=5,
    filter={"type": "class"}  # 可选过滤
)

# 返回相关实体
# 1. UserValidator (相关性: 0.95)
# 2. InputValidator (相关性: 0.87)
# 3. DataValidator (相关性: 0.82)
```

### 2. 上下文组装

```python
def assemble_context_for_llm(
    entity: CodeEntity,
    include_dependencies: bool = True,
    include_examples: bool = True
) -> str:
    """为 LLM 组装上下文"""
    parts = []
    
    # 1. 实体定义
    parts.append(f"## {entity.name}")
    parts.append(f"\n{entity.description}\n")
    
    # 2. 签名（如果是方法）
    if entity.signature:
        parts.append(f"```python")
        parts.append(format_signature(entity.signature))
        parts.append(f"```\n")
    
    # 3. 契约
    if entity.contract:
        parts.append("### 契约要求")
        for pre in entity.contract.preconditions:
            parts.append(f"- 前置条件: {pre}")
        for post in entity.contract.postconditions:
            parts.append(f"- 后置条件: {post}")
        parts.append("")
    
    # 4. 依赖关系
    if include_dependencies and entity.dependencies:
        parts.append("### 依赖关系")
        for dep in entity.dependencies[:5]:  # 限制数量
            target = get_entity(dep.target_id)
            parts.append(f"- {dep.relation_type.value}: {target.name} ({dep.context})")
        parts.append("")
    
    # 5. 使用示例
    if include_examples and entity.examples:
        parts.append("### 使用示例")
        for example in entity.examples[:3]:
            parts.append(f"```python\n{example}\n```")
    
    return "\n".join(parts)
```

### 3. 代码生成 Prompt

```python
def generate_code_prompt(
    task_description: str,
    related_entities: List[CodeEntity]
) -> str:
    """生成代码的 Prompt"""
    return f"""
# 任务
{task_description}

# 相关接口和依赖

{chr(10).join(assemble_context_for_llm(e) for e in related_entities)}

# 实现要求
1. 遵循接口定义的方法签名
2. 满足所有契约条件
3. 保持与依赖模块的兼容性
4. 添加适当的错误处理
"""
```

---

## 📊 数据模型优势

### 1. 简洁性

- **统一模型**：所有代码知识用 `CodeEntity` 表示
- **避免冗余**：只存储必要信息
- **结构化**：清晰的字段定义

### 2. 语义丰富

- **多层次信息**：描述、用途、领域
- **完整契约**：前置/后置条件、异常
- **依赖上下文**：关系类型和调用上下文

### 3. LLM 友好

- **自然语言描述**：易于理解
- **结构化信息**：易于解析
- **上下文完整**：包含依赖和使用示例

### 4. 向量化友好

- **embedding_text**：专门优化的文本
- **关键信息优先**：最重要的语义在前
- **标签支持**：支持元数据过滤

---

## 🚀 实施建议

### Phase 1: 基础模型

1. [ ] 定义 `CodeEntity` 数据类
2. [ ] 实现实体提取器
3. [ ] 实现 `embedding_text` 生成器

### Phase 2: 语义增强

1. [ ] 实现 `purpose` 推断
2. [ ] 实现 `domain` 识别
3. [ ] 实现契约提取

### Phase 3: 存储集成

1. [ ] SQLite 表结构
2. [ ] Vector DB 集合
3. [ ] 数据同步机制

---

**版本**: V2.0  
**状态**: 设计完成  
**最后更新**: 2026-01-28
