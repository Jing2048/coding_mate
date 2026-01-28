# AI CodeGen MCP 工具参考

MCP Server: `user-ai-codegen`

---

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

## 常用组合

### 快速开始新需求

```
index → prd.create → prd.analyze → task.plan → [context → 编码 → verify → task.update]* → prd.update
```

### 理解代码

```
index → search(symbol) → inspect → search(dependency)
```

### 断点续做

```
prd.list → task.list → context → [继续]
```
