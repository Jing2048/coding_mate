# PRD 迭代示例

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

// 4. 创建 PRD
user-ai-codegen.prd({
  "action": "create",
  "prd_id": "feat_auth",
  "title": "用户认证系统",
  "content": `
# 用户认证系统

## 背景
系统需要添加用户认证功能，支持登录、注册、Token 验证。

## 功能需求
1. 用户注册 - 邮箱、密码、用户名
2. 用户登录 - 返回 JWT Token
3. Token 验证中间件
4. 密码加密存储

## 技术要求
- 使用 JWT 进行身份验证
- 密码使用 bcrypt 加密
- Token 有效期 24 小时
`
})
```

### Phase 2: 分析

```json
// 分析 PRD
user-ai-codegen.prd({
  "action": "analyze",
  "prd_id": "feat_auth"
})

// 返回:
{
  "prd_id": "feat_auth",
  "keywords": ["User", "Token", "JWT", "password", "login", "register"],
  "impacted_files": 3,
  "change_points": [
    {
      "file": "src/models/user.py",
      "description": "修改 src/models/user.py",
      "symbols": ["User", "UserCreate"]
    },
    {
      "file": "src/services/auth.py",
      "description": "修改 src/services/auth.py",
      "symbols": ["AuthService"]
    }
  ]
}

// 查看相关文件
user-ai-codegen.inspect({
  "target": "src/models/user.py",
  "include_source": true,
  "include_deps": true
})

// 搜索现有的认证相关代码
user-ai-codegen.search({
  "query": "authenticate",
  "type": "symbol"
})

// 语义搜索相关接口（推荐）
user-ai-codegen.search_interfaces({
  "query": "用户认证服务",
  "limit": 10,
  "use_hybrid": true
})

// 查看相关接口详情
user-ai-codegen.get_interface({
  "interface_id": "services.auth:AuthService",
  "include_contracts": true,
  "include_dependencies": true
})
```

### Phase 3: 规划

```json
// 自动创建任务
user-ai-codegen.task({
  "action": "plan",
  "prd_id": "feat_auth"
})

// 返回:
{
  "prd_id": "feat_auth",
  "tasks_created": 2,
  "task_ids": ["feat_auth_task_1", "feat_auth_task_2"]
}

// 查看任务列表
user-ai-codegen.task({
  "action": "list",
  "prd_id": "feat_auth"
})

// 手动添加额外任务
user-ai-codegen.task({
  "action": "create",
  "prd_id": "feat_auth",
  "task_id": "feat_auth_task_3",
  "title": "添加密码加密工具",
  "description": "使用 bcrypt 实现密码哈希和验证",
  "files": ["src/utils/crypto.py"]
})
```

### Phase 4: 实现

```json
// 获取第一个任务的上下文（使用 RAG 模式）
user-ai-codegen.context({
  "task_id": "feat_auth_task_1",
  "max_tokens": 4000,
  "mode": "rag",
  "format": "prompt"
})

// 返回:
{
  "task": {
    "title": "修改 src/models/user.py",
    "description": "添加用户模型字段",
    "files": ["src/models/user.py"]
  },
  "files": [
    {
      "path": "src/models/user.py",
      "symbols": ["User", "UserCreate"],
      "source": "class User:\n    id: int\n    name: str\n..."
    }
  ],
  "dependencies": [...]
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
  "task_id": "feat_auth_task_1",
  "status": "completed"
})
```

### Phase 5: 完成

```json
// 最终验证
user-ai-codegen.verify({
  "file": "src/services/auth.py",
  "checks": ["syntax", "type", "test"]
})

// 更新 PRD 状态
user-ai-codegen.prd({
  "action": "update",
  "prd_id": "feat_auth",
  "status": "completed"
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
// 1. 创建 PRD
user-ai-codegen.prd({
  "action": "create",
  "prd_id": "fix_perf_001",
  "title": "优化数据库查询性能",
  "content": "DataService.get_all() 方法在数据量大时响应缓慢，需要添加分页支持"
})

// 2. 分析
user-ai-codegen.prd({"action": "analyze", "prd_id": "fix_perf_001"})

// 3. 搜索相关代码
user-ai-codegen.search({"query": "DataService", "type": "symbol"})
user-ai-codegen.search({"query": "get_all", "type": "content"})

// 4. 查看详情
user-ai-codegen.inspect({
  "target": "src/services/data.py:DataService",
  "include_source": true
})

// 5. 创建任务并实现
user-ai-codegen.task({
  "action": "create",
  "prd_id": "fix_perf_001",
  "task_id": "fix_perf_001_task_1",
  "title": "添加分页参数",
  "files": ["src/services/data.py"]
})

// 6. 获取上下文 → 编码 → 验证 → 完成
```

---

## 示例 3: 代码理解（无 PRD）

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
// 1. 查看所有 PRD
user-ai-codegen.prd({"action": "list"})
// 返回:
{
  "prds": [
    {"prd_id": "feat_auth", "title": "用户认证", "status": "in_progress"},
    {"prd_id": "fix_bug_001", "title": "修复登录问题", "status": "completed"}
  ]
}

// 2. 获取进行中的 PRD 详情
user-ai-codegen.prd({"action": "get", "prd_id": "feat_auth"})

// 3. 查看任务状态
user-ai-codegen.task({"action": "list", "prd_id": "feat_auth"})
// 返回:
{
  "tasks": [
    {"task_id": "feat_auth_task_1", "status": "completed"},
    {"task_id": "feat_auth_task_2", "status": "pending"},
    {"task_id": "feat_auth_task_3", "status": "pending"}
  ]
}

// 4. 继续第一个未完成的任务
user-ai-codegen.context({"task_id": "feat_auth_task_2"})

// [继续编码...]
```
