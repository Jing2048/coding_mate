# MCP 工具参考

## V2 新工具

### extract_interfaces

从代码文件提取接口定义。

**参数**:
- `paths` (List[str]): 要提取的文件路径列表
- `force` (bool, 可选): 是否强制重新提取

**返回**:
```json
{
  "extracted": 10,
  "total_entities": 10,
  "files_processed": 3
}
```

**示例**:
```python
await server.tool_extract_interfaces(
    paths=["src/services/user.py"],
    force=True
)
```

---

### get_interface

获取接口的详细信息。

**参数**:
- `interface_id` (str): 接口 ID
- `include_contracts` (bool, 可选): 是否包含契约信息
- `include_dependencies` (bool, 可选): 是否包含依赖关系

**返回**:
```json
{
  "id": "entity_123",
  "name": "UserService",
  "type": "class",
  "signature": {...},
  "contracts": {...},
  "dependencies": [...],
  "llm_format": "..."
}
```

**示例**:
```python
await server.tool_get_interface(
    interface_id="entity_123",
    include_contracts=True,
    include_dependencies=True
)
```

---

### list_interfaces

列出所有接口，支持过滤。

**参数**:
- `module` (str, 可选): 按模块过滤
- `entity_type` (str, 可选): 按实体类型过滤（class/function/method/module）
- `domain` (str, 可选): 按领域过滤
- `limit` (int, 可选): 返回数量限制

**返回**:
```json
{
  "total": 50,
  "interfaces": [
    {
      "id": "entity_123",
      "name": "UserService",
      "type": "class",
      "module": "services.user",
      "description": "...",
      "domain": "authentication"
    }
  ]
}
```

**示例**:
```python
await server.tool_list_interfaces(
    entity_type="class",
    limit=20
)
```

---

### search_interfaces

语义搜索接口（需要 RAG 依赖）。

**参数**:
- `query` (str): 搜索查询
- `entity_type` (str, 可选): 实体类型过滤
- `domain` (str, 可选): 领域过滤
- `limit` (int, 可选): 返回数量限制
- `use_hybrid` (bool, 可选): 是否使用混合搜索

**返回**:
```json
{
  "total": 5,
  "results": [
    {
      "id": "entity_123",
      "name": "UserService",
      "type": "class",
      "score": 0.85
    }
  ],
  "mode": "rag_semantic"
}
```

**示例**:
```python
await server.tool_search_interfaces(
    query="用户认证服务",
    use_hybrid=True,
    limit=10
)
```

---

### sync_rag

同步 SQLite 数据到向量数据库。

**参数**:
- `force` (bool, 可选): 是否强制重新同步

**返回**:
```json
{
  "success": true,
  "stats": {
    "vector_store": {
      "total_entities": 100
    },
    "sqlite": {
      "total_entities": 100
    }
  }
}
```

**示例**:
```python
await server.tool_sync_rag(force=True)
```

---

### context (增强)

获取实现任务的上下文，支持 RAG 模式。

**参数**:
- `task_id` (str, 可选): 任务 ID
- `files` (List[str], 可选): 指定文件列表
- `symbols` (List[str], 可选): 指定符号列表
- `max_tokens` (int, 可选): 最大 token 数
- `format` (str, 可选): 输出格式（structured/prompt）
- `depth` (int, 可选): 依赖遍历深度
- `mode` (str, 可选): 模式（dependency/rag/full）

**返回** (RAG 模式):
```json
{
  "text": "## 相关接口\n\n### UserService\n...",
  "mode": "rag",
  "interfaces": [...],
  "suggestions": [...]
}
```

**示例**:
```python
# RAG 模式
await server.tool_context(
    mode="rag",
    max_tokens=4000,
    format="prompt"
)

# 依赖图模式
await server.tool_context(
    files=["src/services/user.py"],
    mode="dependency",
    max_tokens=4000
)
```

---

## V1 工具（保留）

### index

索引代码库，构建知识图谱。

### search

搜索代码（符号、文件、内容、依赖）。

### inspect

查看文件或符号的详细信息。

### prd

PRD 生命周期管理。

### task

任务管理。

### verify

代码验证（语法、类型、测试）。

---

**版本**: V2.0  
**最后更新**: 2026-01-28
