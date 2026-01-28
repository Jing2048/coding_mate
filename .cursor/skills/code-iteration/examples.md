# 代码迭代示例

## 示例 1: 添加用户认证功能

### Phase 1: 初始化

```json
// 1. 索引代码库
user-ai-codegen.index({
  "paths": ["src"],
  "extensions": [".py", ".ts", ".swift"]
})
// 返回: {"indexed": 45, "total_nodes": 128, "total_edges": 67}

// 2. 提取接口（推荐）
user-ai-codegen.extract_interfaces({
  "paths": ["src"],
  "force": false
})
// 返回: {"extracted": 25, "total_entities": 25}

// 3. 同步到 RAG（推荐，如果已安装 RAG 依赖）
user-ai-codegen.sync_rag({
  "force": false
})
// 返回: {"success": true, "stats": {...}}
```

### Phase 2: 分析和规划

```json
// 1. 语义搜索相关接口
user-ai-codegen.search_interfaces({
  "query": "用户认证服务",
  "limit": 10,
  "use_hybrid": true
})

// 返回:
{
  "total": 3,
  "results": [
    {
      "id": "services.user:UserService",
      "name": "UserService",
      "type": "class",
      "description": "用户服务类"
    }
  ],
  "mode": "rag_hybrid"
}

// 2. 查看相关文件
user-ai-codegen.inspect({
  "target": "src/models/user.py",
  "include_source": true,
  "include_deps": true
})

// 3. 搜索现有的认证相关代码
user-ai-codegen.search({
  "query": "authenticate",
  "type": "symbol"
})

// 4. 创建任务
user-ai-codegen.task({
  "action": "create",
  "task_id": "task_auth_001",
  "title": "添加用户模型字段",
  "description": "在 User 模型中添加 password_hash、email、created_at 字段",
  "files": ["src/models/user.py"]
})

user-ai-codegen.task({
  "action": "create",
  "task_id": "task_auth_002",
  "title": "实现认证服务",
  "description": "创建 AuthService 类，实现登录、注册、Token 验证功能",
  "files": ["src/services/auth.py"]
})
```

### Phase 3: 实现

```json
// 获取第一个任务的上下文（使用 RAG 模式）
user-ai-codegen.context({
  "task_id": "task_auth_001",
  "max_tokens": 4000,
  "mode": "rag",
  "format": "prompt"
})

// 返回:
{
  "task": {
    "title": "添加用户模型字段",
    "description": "在 User 模型中添加 password_hash、email、created_at 字段",
    "files": ["src/models/user.py"]
  },
  "target_files": [
    {
      "path": "src/models/user.py",
      "symbols": [{"name": "User", "type": "class"}],
      "source": "class User:\n    id: int\n    name: str\n..."
    }
  ],
  "dependencies": [...],
  "related_code": [...]
}

// [Cursor/Claude 完成编码]
// 修改 src/models/user.py，添加:
// - password_hash 字段
// - email 字段
// - created_at 字段

// 验证代码
user-ai-codegen.verify({
  "file": "src/models/user.py",
  "checks": ["syntax", "type"]
})

// 返回: {"passed": true, "details": {...}}

// 更新任务状态
user-ai-codegen.task({
  "action": "update",
  "task_id": "task_auth_001",
  "status": "completed"
})
```

### Phase 4: 完成

```json
// 最终验证
user-ai-codegen.verify({
  "file": "src/services/auth.py",
  "checks": ["syntax", "type", "test"]
})

// 重新索引更新知识图谱
user-ai-codegen.index({
  "paths": ["src/models", "src/services"],
  "force": true
})
```

---

## 示例 2: 修复性能问题

### 快速流程

```json
// 1. 索引代码库
user-ai-codegen.index({"paths": ["src"]})

// 2. 提取接口
user-ai-codegen.extract_interfaces({"paths": ["src"]})

// 3. 同步 RAG
user-ai-codegen.sync_rag()

// 4. 搜索相关代码
user-ai-codegen.search({"query": "DataService", "type": "symbol"})
user-ai-codegen.search({"query": "get_all", "type": "content"})

// 5. 查看详情
user-ai-codegen.inspect({
  "target": "src/services/data.py:DataService",
  "include_source": true
})

// 6. 创建任务并实现
user-ai-codegen.task({
  "action": "create",
  "task_id": "task_perf_001",
  "title": "添加分页参数",
  "files": ["src/services/data.py"]
})

// 7. 获取上下文 → 编码 → 验证 → 完成
```

---

## 示例 3: 代码理解（无任务）

当只需要理解代码而不进行修改时:

```json
// 1. 确保已索引
user-ai-codegen.index({"paths": ["."]})

// 2. 提取接口
user-ai-codegen.extract_interfaces({"paths": ["."]})

// 3. 同步到 RAG
user-ai-codegen.sync_rag()

// 4. 语义搜索相关接口
user-ai-codegen.search_interfaces({
  "query": "支付服务",
  "limit": 10,
  "use_hybrid": true
})

// 5. 获取接口详情
user-ai-codegen.get_interface({
  "interface_id": "payment.service:PaymentService",
  "include_contracts": true,
  "include_dependencies": true
})

// 6. 查看符号详情
user-ai-codegen.inspect({
  "target": "src/payment/service.py:PaymentService",
  "include_source": true,
  "include_deps": true
})

// 7. 查看谁调用了这个服务
user-ai-codegen.search({
  "query": "PaymentService",
  "type": "dependency"
})

// 8. 列出所有相关接口
user-ai-codegen.list_interfaces({
  "module": "payment",
  "entity_type": "class",
  "limit": 20
})
```

---

## 示例 4: 断点续做

```json
// 1. 查看所有任务
user-ai-codegen.task({"action": "list"})
// 返回:
{
  "tasks": [
    {"task_id": "task_auth_001", "title": "添加用户模型", "status": "completed"},
    {"task_id": "task_auth_002", "title": "实现认证服务", "status": "pending"},
    {"task_id": "task_auth_003", "title": "添加 Token 验证", "status": "pending"}
  ]
}

// 2. 获取任务详情
user-ai-codegen.task({"action": "get", "task_id": "task_auth_002"})

// 3. 继续第一个未完成的任务
user-ai-codegen.context({
  "task_id": "task_auth_002",
  "mode": "rag"
})

// [继续编码...]
```

---

## 示例 5: 接口驱动开发

```json
// 1. 提取接口
user-ai-codegen.extract_interfaces({
  "paths": ["src/services"]
})

// 2. 同步到 RAG
user-ai-codegen.sync_rag()

// 3. 语义搜索相关接口
user-ai-codegen.search_interfaces({
  "query": "用户服务接口",
  "limit": 5
})

// 4. 查看接口详情（包含契约和依赖）
user-ai-codegen.get_interface({
  "interface_id": "services.user:UserService",
  "include_contracts": true,
  "include_dependencies": true
})

// 5. 基于接口契约实现代码
// [使用接口定义、契约、依赖关系等信息进行编码]
```
