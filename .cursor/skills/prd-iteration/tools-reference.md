# AI CodeGen MCP 工具参考 (V2)

MCP Server: `user-ai-codegen`

**版本**: V2.0  
**最后更新**: 2026-01-28

---

## V2 新工具（接口和 RAG）

### extract_interfaces - 提取接口定义

从代码文件自动提取接口定义（类、函数、方法），构建 CodeEntity 并存储到 SQLite。

**参数**:
```json
{
  "paths": ["src/services", "src/models"],  // 文件路径列表（支持目录）
  "force": true                              // 是否强制重新提取
}
```

**返回**:
```json
{
  "extracted": 25,
  "entities": ["module.Class", "module.function"],
  "total_entities": 47,
  "total_dependencies": 54,
  "errors": []
}
```

**使用场景**:
- 初始化时提取整个代码库的接口
- 修改代码后重新提取接口
- 增量提取新增或修改的文件

---

### get_interface - 获取接口详情

获取接口的完整信息，包括签名、契约、依赖关系。

**参数**:
```json
{
  "interface_id": "module.Class",           // 接口 ID
  "include_contracts": true,                 // 包含契约信息
  "include_dependencies": true              // 包含依赖关系
}
```

**返回**:
```json
{
  "id": "module.Class",
  "name": "UserService",
  "type": "class",
  "module": "services.user",
  "signature": {...},
  "contract": {
    "preconditions": [...],
    "postconditions": [...],
    "throws": [...]
  },
  "dependencies": [...],
  "dependents": [...],
  "llm_format": "格式化的 LLM 提示文本"
}
```

**使用场景**:
- 理解接口的完整规范
- 查看接口的契约要求
- 分析接口的依赖关系

---

### list_interfaces - 列出接口

列出所有已提取的接口，支持多种过滤条件。

**参数**:
```json
{
  "module": "services.user",                // 按模块过滤
  "entity_type": "class",                   // class | function | method | module
  "domain": "authentication",              // 按领域过滤
  "limit": 50                               // 返回数量限制
}
```

**返回**:
```json
{
  "total": 47,
  "interfaces": [
    {
      "id": "module.Class",
      "name": "UserService",
      "type": "class",
      "module": "services.user",
      "description": "用户服务类",
      "domain": "authentication",
      "methods_count": 5
    }
  ]
}
```

**使用场景**:
- 浏览代码库中的接口
- 按模块或类型过滤接口
- 了解代码库的接口概览

---

### search_interfaces - 语义搜索接口

使用 RAG 进行语义搜索，找到与查询相关的接口。

**参数**:
```json
{
  "query": "用户认证服务",                  // 搜索查询
  "entity_type": "class",                   // 实体类型过滤
  "domain": "authentication",              // 领域过滤
  "limit": 10,                              // 返回数量
  "use_hybrid": true                        // 混合搜索（关键词+语义）
}
```

**返回**:
```json
{
  "total": 5,
  "results": [
    {
      "id": "services.user:UserService",
      "type": "class",
      "name": "UserService",
      "module": "services.user",
      "description": "用户服务类",
      "score": 0.85,                        // 相关性分数
      "source_snippet": "class UserService:...",
      "contract": {...},
      "dependencies": [...]
    }
  ],
  "mode": "rag_semantic"                    // 搜索模式
}
```

**使用场景**:
- 根据需求描述搜索相关接口
- 发现相似功能的接口
- 理解代码库的接口组织

---

### sync_rag - 同步到向量数据库

将 SQLite 中的接口定义同步到 Chroma 向量数据库，启用语义搜索。

**参数**:
```json
{
  "force": false                            // 是否强制重新同步（增量同步）
}
```

**返回**:
```json
{
  "success": true,
  "stats": {
    "vector_store": {
      "total_entities": 47,
      "collection_name": "code_entities"
    },
    "sqlite": {
      "total_entities": 47,
      "total_dependencies": 54,
      "total_modules": 14
    },
    "embedding_dimension": 384
  }
}
```

**使用场景**:
- 首次使用 RAG 功能前同步
- 提取新接口后同步
- 定期同步保持数据一致

---

### context (增强) - 获取实现上下文

获取实现任务的智能上下文，支持 RAG 模式和依赖图模式。

**参数**:
```json
{
  "task_id": "task_001",                    // 任务 ID（可选）
  "files": ["src/user.py"],                 // 指定文件（可选）
  "symbols": ["file.py:Symbol"],           // 指定符号（可选）
  "mode": "rag",                            // rag | dependency | full
  "max_tokens": 4000,                       // 最大 token 数
  "format": "prompt",                       // prompt | structured
  "depth": 2                                // 依赖遍历深度
}
```

**返回** (RAG 模式):
```json
{
  "text": "## 相关接口\n\n### UserService\n...",
  "mode": "rag",
  "interfaces": [
    {
      "id": "services.user:UserService",
      "name": "UserService",
      "description": "...",
      "relevance": 0.85
    }
  ],
  "suggestions": [
    "建议使用 UserService 进行用户认证",
    "可以参考 AuthService 的实现模式"
  ],
  "total_tokens": 3500
}
```

**返回** (依赖模式):
```json
{
  "task": {...},
  "target_files": [...],
  "dependencies": [...],
  "related_code": [...],
  "summary": {
    "total_files": 4,
    "total_tokens": 3500
  }
}
```

**使用场景**:
- RAG 模式：基于任务描述智能推荐相关接口
- 依赖模式：基于依赖图收集相关代码
- 完整模式：结合 RAG 和依赖图

---

## V1 工具（代码分析）

## index - 索引代码库

构建知识图谱，支持增量索引。

```json
{
  "paths": ["src", "lib"],      // 路径列表（相对于 workspace）
  "extensions": [".py", ".ts"], // 文件扩展名
  "force": false                // 强制重新索引
}
```

**返回**:
```json
{
  "indexed": 10,          // 本次索引的文件数
  "symbols": 45,          // 本次索引的符号数
  "total_files": 100,     // 总文件数
  "total_nodes": 350,     // 知识图谱节点数
  "total_edges": 200      // 知识图谱边数
}
```

---

## search - 搜索代码

四种搜索类型: symbol / file / content / dependency

```json
{
  "query": "UserService",
  "type": "symbol",     // symbol | file | content | dependency
  "limit": 20
}
```

**返回 (symbol)**:
```json
[
  {"file": "src/user.py", "symbol": "UserService", "type": "class", "line": 10},
  {"file": "src/api.py", "symbol": "UserServiceAPI", "type": "class", "line": 25}
]
```

**返回 (dependency)**:
```json
[
  {"source": "src/api.py", "target": "src/user.py", "type": "imports"}
]
```

---

## inspect - 查看详情

查看文件或符号的详细信息。

```json
// 查看文件
{"target": "src/user.py", "include_source": true, "include_deps": true}

// 查看符号 (file:symbol 格式)
{"target": "src/user.py:UserService", "include_source": true}
```

**返回 (文件)**:
```json
{
  "file": "src/user.py",
  "symbols": [...],
  "imports": [...],
  "source": "...",
  "dependencies": {
    "imports": ["src/base.py"],
    "imported_by": ["src/api.py"]
  }
}
```

**返回 (符号)**:
```json
{
  "file": "src/user.py",
  "symbol": "UserService",
  "type": "class",
  "line": 10,
  "docstring": "用户服务类",
  "source": "class UserService:\n    ...",
  "dependencies": {
    "uses": ["src/db.py:Database"],
    "used_by": ["src/api.py:create_user"]
  }
}
```

---

## prd - PRD 管理

完整的 PRD 生命周期管理。

### 创建

```json
{
  "action": "create",
  "prd_id": "feat_001",
  "title": "新功能标题",
  "content": "PRD 完整内容..."
}
```

### 分析

```json
{
  "action": "analyze",
  "prd_id": "feat_001"
}
```

**返回**:
```json
{
  "prd_id": "feat_001",
  "keywords": ["User", "login"],
  "impacted_files": 3,
  "change_points": [...]
}
```

### 列表

```json
{"action": "list"}
```

**返回**:
```json
{
  "prds": [
    {"prd_id": "feat_001", "title": "...", "status": "planned"}
  ],
  "total": 1
}
```

### 获取详情

```json
{"action": "get", "prd_id": "feat_001"}
```

### 更新状态

```json
{
  "action": "update",
  "prd_id": "feat_001",
  "status": "in_progress"  // draft | analyzing | planned | in_progress | completed | archived
}
```

---

## task - 任务管理

### 从 PRD 自动创建任务

```json
{
  "action": "plan",
  "prd_id": "feat_001"
}
```

### 手动创建任务

```json
{
  "action": "create",
  "prd_id": "feat_001",
  "task_id": "task_001",
  "title": "任务标题",
  "description": "任务描述",
  "files": ["src/user.py", "src/api.py"]
}
```

### 列表

```json
{"action": "list", "prd_id": "feat_001"}
```

### 获取详情

```json
{"action": "get", "task_id": "task_001"}
```

### 更新状态

```json
{
  "action": "update",
  "task_id": "task_001",
  "status": "completed"  // pending | in_progress | completed | blocked | cancelled
}
```

---

## verify - 代码验证

验证代码的语法、类型和测试。

```json
{
  "file": "src/user.py",
  "checks": ["syntax", "type", "test"]
}
```

**返回**:
```json
{
  "file": "src/user.py",
  "passed": true,
  "details": {
    "syntax": {"passed": true},
    "type": {"passed": true, "output": "..."},
    "test": {"passed": true, "output": "..."}
  }
}
```

---

## context - 获取实现上下文

获取实现任务的智能上下文，基于依赖图收集相关代码。

```json
{
  "task_id": "task_001",
  "files": ["src/user.py"],        // 可选：指定文件
  "symbols": ["file.py:Symbol"],   // 可选：指定符号
  "max_tokens": 8000,              // 可选：最大 token（默认 8000）
  "format": "prompt",              // 可选：structured / prompt
  "depth": 2                       // 可选：依赖遍历深度（默认 1）
}
```

**返回 (structured 格式)**:
```json
{
  "task": {
    "id": "task_001",
    "title": "任务标题",
    "description": "任务描述",
    "files": ["src/user.py"],
    "status": "pending"
  },
  "target_files": [
    {
      "path": "src/user.py",
      "symbols": [{"name": "UserService", "type": "class"}],
      "imports": [...],
      "source": "...",
      "tokens": 500
    }
  ],
  "dependencies": [
    {
      "path": "src/db.py",
      "symbols": [{"name": "Database", "type": "class"}],
      "summary": "# src/db.py\n- class: Database...",
      "depth": 1,
      "tokens": 100
    }
  ],
  "related_code": [...],
  "summary": {
    "total_files": 4,
    "total_symbols": 15,
    "tokens_used": 1200,
    "budget": {"task": 800, "target": 3200, "deps": 2400, "related": 1600}
  }
}
```

**返回 (prompt 格式)**:
```json
{
  "prompt": "## Task\n**任务标题**\n...\n## Target Files\n...",
  "tokens": 1200,
  "summary": {...}
}
```

**特性**:
- **Token 预算管理** - 自动分配 token 到各部分
- **依赖图遍历** - 基于 depth 参数收集依赖代码
- **Prompt-ready** - format=prompt 时直接返回可用于 LLM 的文本

---

---

## 常用组合 (V2)

### 快速开始新需求（接口驱动）

```
index → extract_interfaces → sync_rag → prd.create → prd.analyze 
→ search_interfaces → task.plan → [context(mode="rag") → 编码 → verify → task.update]* 
→ extract_interfaces → sync_rag → prd.update
```

### 理解代码（V2 增强）

```
index → extract_interfaces → sync_rag → search_interfaces(query="服务名") 
→ get_interface(include_deps=true) → list_interfaces(module="xxx")
```

### 接口驱动开发

```
extract_interfaces → sync_rag → search_interfaces(query="需求描述") 
→ get_interface → [基于接口规范编码] → verify
```

### 断点续做

```
prd.list → task.list → context(mode="rag") → [继续]
```

---

## 工具选择指南

### 何时使用 V2 工具

- **extract_interfaces**: 初始化、代码修改后、定期更新
- **search_interfaces**: 需要语义搜索、发现相关接口、理解代码组织
- **get_interface**: 需要查看接口详情、理解契约、分析依赖
- **list_interfaces**: 浏览接口、按条件过滤、了解代码库结构
- **sync_rag**: 首次使用 RAG、提取新接口后、定期同步
- **context(mode="rag")**: 需要智能上下文推荐、理解任务意图

### 何时使用 V1 工具

- **index**: 构建知识图谱、分析代码结构
- **search**: 精确关键词搜索、查找符号位置
- **inspect**: 查看文件源码、查看符号定义
- **prd/task**: PRD 和任务管理
- **verify**: 代码验证
