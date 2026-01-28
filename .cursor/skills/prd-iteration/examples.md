# PRD 迭代示例 (V2)

## 示例 1: 添加用户认证功能（接口驱动）

### Phase 1: 初始化与接口提取

```json
// 1. 索引代码库
user-ai-codegen.index({
  "paths": ["src"],
  "extensions": [".py"]
})
// 返回: {"indexed": 45, "total_nodes": 128, "total_edges": 67}

// 2. 提取接口定义（V2 新功能）
user-ai-codegen.extract_interfaces({
  "paths": ["src"],
  "force": true
})
// 返回: {"extracted": 25, "total_entities": 25, "total_dependencies": 30}

// 3. 同步到 RAG 向量数据库（V2 新功能）
user-ai-codegen.sync_rag({
  "force": true
})
// 返回: {"success": true, "stats": {"vector_store": {"total_entities": 25}}}

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

### Phase 2: 分析与接口发现（V2 增强）

```json
// 1. 分析 PRD
user-ai-codegen.prd({
  "action": "analyze",
  "prd_id": "feat_auth"
})

// 返回:
{
  "prd_id": "feat_auth",
  "keywords": ["User", "Token", "JWT", "password", "login", "register"],
  "impacted_files": 3,
  "change_points": [...]
}

// 2. 语义搜索相关接口（V2 新功能）
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
      "score": 0.85,
      "description": "用户服务类",
      "dependencies": [...]
    }
  ],
  "mode": "rag_semantic"
}

// 3. 查看接口详情（V2 新功能）
user-ai-codegen.get_interface({
  "interface_id": "services.user:UserService",
  "include_contracts": true,
  "include_dependencies": true
})

// 返回:
{
  "id": "services.user:UserService",
  "name": "UserService",
  "signature": {...},
  "contract": {
    "preconditions": [...],
    "postconditions": [...]
  },
  "dependencies": [...],
  "dependents": [...]
}

// 4. 传统搜索（补充）
user-ai-codegen.search({
  "query": "authenticate",
  "type": "symbol"
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

### Phase 4: 实现（V2 增强）

```json
// 获取第一个任务的上下文（使用 RAG 模式）
user-ai-codegen.context({
  "task_id": "feat_auth_task_1",
  "mode": "rag",                    // V2: RAG 模式
  "max_tokens": 4000,
  "format": "prompt"
})

// 返回 (RAG 模式):
{
  "text": "## 相关接口\n\n### UserService\n...",
  "mode": "rag",
  "interfaces": [
    {
      "id": "services.user:UserService",
      "name": "UserService",
      "relevance": 0.85
    }
  ],
  "suggestions": [
    "建议参考现有的 UserService 接口设计",
    "可以使用类似的认证模式"
  ]
}

// 或者使用依赖模式:
user-ai-codegen.context({
  "task_id": "feat_auth_task_1",
  "mode": "dependency",
  "max_tokens": 4000
})

// 返回:
{
  "task": {...},
  "target_files": [...],
  "dependencies": [...]
}

// [Cursor/Claude 完成编码]
// 基于接口规范实现代码:
// 1. 查看相关接口的签名和契约
// 2. 遵循接口设计模式
// 3. 保持依赖兼容性

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

### Phase 5: 完成（V2 增强）

```json
// 最终验证
user-ai-codegen.verify({
  "file": "src/services/auth.py",
  "checks": ["syntax", "type", "test"]
})

// 重新提取接口（V2 新功能）
user-ai-codegen.extract_interfaces({
  "paths": ["src/models", "src/services"],
  "force": true
})

// 同步到 RAG（V2 新功能）
user-ai-codegen.sync_rag({
  "force": false  // 增量同步
})

// 更新 PRD 状态
user-ai-codegen.prd({
  "action": "update",
  "prd_id": "feat_auth",
  "status": "completed"
})

// 重新索引更新知识图谱（可选）
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

## 示例 3: 代码理解（无 PRD）- V2 增强

当只需要理解代码而不进行修改时，使用 V2 的接口驱动方式:

```json
// 1. 索引和提取接口
user-ai-codegen.index({"paths": ["."]})
user-ai-codegen.extract_interfaces({"paths": ["."]})
user-ai-codegen.sync_rag()

// 2. 语义搜索接口（V2 新功能）
user-ai-codegen.search_interfaces({
  "query": "支付服务",
  "limit": 5,
  "use_hybrid": true
})

// 返回相关接口列表，按相关性排序

// 3. 查看接口详情（V2 新功能）
user-ai-codegen.get_interface({
  "interface_id": "services.payment:PaymentService",
  "include_contracts": true,
  "include_dependencies": true
})

// 返回:
// - 接口签名和类型
// - 契约（前置条件、后置条件、异常）
// - 依赖关系（使用的和被使用的）

// 4. 浏览接口列表（V2 新功能）
user-ai-codegen.list_interfaces({
  "module": "services.payment",
  "entity_type": "class",
  "limit": 20
})

// 5. 传统方式（补充）
user-ai-codegen.search({
  "query": "PaymentService",
  "type": "symbol"
})

user-ai-codegen.inspect({
  "target": "src/payment/service.py:PaymentService",
  "include_source": true,
  "include_deps": true
})
```

---

## 示例 4: 断点续做（V2 增强）

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

// 4. 继续第一个未完成的任务（使用 RAG 模式）
user-ai-codegen.context({
  "task_id": "feat_auth_task_2",
  "mode": "rag",              // V2: 使用 RAG 模式
  "max_tokens": 4000
})

// 返回智能上下文，包括:
// - 相关接口推荐
// - 架构建议
// - 依赖关系

// [继续编码...]
```

---

## 示例 5: 接口驱动开发（V2 新流程）

基于接口规范进行开发，而不是直接修改代码:

```json
// 1. 提取现有接口
user-ai-codegen.extract_interfaces({
  "paths": ["src/services"],
  "force": true
})

// 2. 搜索相似接口作为参考
user-ai-codegen.search_interfaces({
  "query": "用户管理服务",
  "limit": 5
})

// 3. 查看参考接口的完整规范
user-ai-codegen.get_interface({
  "interface_id": "services.user:UserService",
  "include_contracts": true,
  "include_dependencies": true
})

// 4. 基于接口规范设计新接口
// [设计接口签名、契约、依赖关系]

// 5. 实现接口
// [基于接口规范实现代码，遵循契约要求]

// 6. 验证实现
user-ai-codegen.verify({
  "file": "src/services/new_service.py",
  "checks": ["syntax", "type"]
})

// 7. 重新提取接口
user-ai-codegen.extract_interfaces({
  "paths": ["src/services/new_service.py"],
  "force": true
})

// 8. 同步到 RAG
user-ai-codegen.sync_rag({"force": false})
```
