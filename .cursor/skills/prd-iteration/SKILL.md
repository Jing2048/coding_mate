---
name: prd-iteration
description: 基于 AI CodeGen MCP V2 的完整需求迭代流程。使用接口驱动开发、RAG 语义搜索、依赖感知编码，由 Cursor/Claude 完成高质量编码。当用户提到"迭代"、"PRD"、"需求开发"、"新功能开发"时使用此 skill。
---

# PRD 迭代流程 (V2)

使用 `user-ai-codegen` MCP 服务器 V2 版本管理完整的需求迭代生命周期。

## 核心原则

- **接口驱动开发** - 自动提取接口，基于接口规范生成代码
- **RAG 增强检索** - 语义搜索接口和依赖，智能上下文推荐
- **依赖感知编码** - 理解代码关系，分析改动影响
- **专业编码辅助** - 架构级别建议，关注代码质量
- **Cursor/Claude 负责编码** - 使用 MCP 提供的上下文完成实际编码
- **持久化追踪** - 所有状态存储在 SQLite + Chroma，支持断点续做

## MCP 工具速查

### V2 核心工具（接口和 RAG）

```
extract_interfaces - 从代码提取接口定义
get_interface      - 获取接口详情（包含契约和依赖）
list_interfaces    - 列出所有接口（支持过滤）
search_interfaces  - 语义搜索接口（RAG 驱动）
sync_rag          - 同步数据到向量数据库
context (增强)    - 获取实现上下文（支持 RAG 模式）
```

### V1 工具（代码分析）

```
index    - 索引代码库，构建知识图谱
search   - 搜索代码 (symbol/file/content/dependency)
inspect  - 查看文件或符号详情
prd      - PRD 管理 (create/analyze/list/get/update)
task     - 任务管理 (create/list/get/update/plan)
verify   - 代码验证 (syntax/type/test)
```

---

## 完整迭代流程 (V2)

### Phase 1: 初始化与接口提取

**目标**: 索引代码库，提取接口定义，同步到 RAG，创建 PRD

```
进度追踪:
- [ ] 1.1 索引代码库
- [ ] 1.2 提取接口定义
- [ ] 1.3 同步到 RAG 向量数据库
- [ ] 1.4 创建 PRD
```

**1.1 索引代码库**

```json
// 调用 MCP: user-ai-codegen.index
{
  "paths": ["src", "lib"],
  "extensions": [".py", ".ts", ".js", ".swift"],
  "force": false
}
```

检查返回的 `total_files` 和 `total_nodes`，确保代码库已被正确索引。

**1.2 提取接口定义**

```json
// 调用 MCP: user-ai-codegen.extract_interfaces
{
  "paths": ["src/services", "src/models"],
  "force": true
}
```

这会自动提取：
- 类、结构体、协议（接口）
- 函数和方法签名
- 类型信息和文档字符串
- 模块边界和依赖关系

**1.3 同步到 RAG 向量数据库**

```json
// 调用 MCP: user-ai-codegen.sync_rag
{
  "force": true
}
```

将提取的接口向量化并存储到 Chroma，启用语义搜索功能。

**1.4 创建 PRD**

```json
// 调用 MCP: user-ai-codegen.prd
{
  "action": "create",
  "prd_id": "<unique_id>",
  "title": "<PRD 标题>",
  "content": "<PRD 完整内容>"
}
```

> 💡 `prd_id` 建议使用 `feat_xxx` 或 `fix_xxx` 格式

---

### Phase 2: 分析与接口发现

**目标**: 分析 PRD 影响范围，使用 RAG 语义搜索发现相关接口

```
进度追踪:
- [ ] 2.1 分析 PRD
- [ ] 2.2 语义搜索相关接口
- [ ] 2.3 查看接口详情和依赖
- [ ] 2.4 确认改动点
```

**2.1 分析 PRD**

```json
// 调用 MCP: user-ai-codegen.prd
{
  "action": "analyze",
  "prd_id": "<prd_id>"
}
```

返回结果包含:
- `keywords` - 从 PRD 提取的关键词
- `impacted_files` - 受影响的文件数量
- `change_points` - 识别的改动点

**2.2 语义搜索相关接口（V2 新功能）**

使用 RAG 语义搜索找到与 PRD 相关的接口:

```json
// 调用 MCP: user-ai-codegen.search_interfaces
{
  "query": "<PRD 关键词或描述>",
  "limit": 10,
  "use_hybrid": true
}
```

例如，PRD 关于"用户认证"，可以搜索:
```json
{
  "query": "用户认证服务",
  "entity_type": "class",
  "limit": 5
}
```

**2.3 查看接口详情**

对于搜索到的接口，查看完整信息:

```json
// 调用 MCP: user-ai-codegen.get_interface
{
  "interface_id": "<interface_id>",
  "include_contracts": true,
  "include_dependencies": true
}
```

这会返回：
- 接口签名和类型信息
- 契约（前置条件、后置条件、异常）
- 依赖关系（使用的和被使用的）

**2.4 传统搜索（补充）**

如需更多上下文，使用传统搜索:

```json
// 搜索符号
{"query": "<keyword>", "type": "symbol"}

// 搜索依赖
{"query": "<module>", "type": "dependency"}

// 查看文件详情
{"target": "<file_path>", "include_source": true, "include_deps": true}
```

---

### Phase 3: 规划

**目标**: 从 PRD 创建具体任务

```
进度追踪:
- [ ] 3.1 自动创建任务
- [ ] 3.2 审查任务列表
- [ ] 3.3 调整任务（如需要）
```

**3.1 自动创建任务**

```json
// 调用 MCP: user-ai-codegen.task
{
  "action": "plan",
  "prd_id": "<prd_id>"
}
```

这会根据 `change_points` 自动创建任务。

**3.2 查看任务列表**

```json
// 调用 MCP: user-ai-codegen.task
{
  "action": "list",
  "prd_id": "<prd_id>"
}
```

**3.3 手动创建任务（可选）**

如果自动创建的任务不够细致:

```json
// 调用 MCP: user-ai-codegen.task
{
  "action": "create",
  "prd_id": "<prd_id>",
  "task_id": "<task_id>",
  "title": "任务标题",
  "description": "详细描述",
  "files": ["file1.py", "file2.py"]
}
```

**3.4 更新 PRD 状态**

```json
// 调用 MCP: user-ai-codegen.prd
{
  "action": "update",
  "prd_id": "<prd_id>",
  "status": "planned"
}
```

---

### Phase 4: 实现（循环）

**目标**: 逐个完成任务

```
对于每个任务:
- [ ] 4.1 获取任务上下文
- [ ] 4.2 实现代码 (Cursor/Claude)
- [ ] 4.3 验证代码
- [ ] 4.4 更新任务状态
```

**4.1 获取任务上下文（V2 增强）**

使用 RAG 模式获取智能上下文:

```json
// 调用 MCP: user-ai-codegen.context (RAG 模式)
{
  "task_id": "<task_id>",
  "mode": "rag",              // rag | dependency | full
  "max_tokens": 4000,
  "format": "prompt"          // prompt | structured
}
```

**RAG 模式** (`mode: "rag"`):
- 基于任务描述语义搜索相关接口
- 自动推荐相关接口和依赖
- 提供架构级别的建议

**依赖模式** (`mode: "dependency"`):
- 基于依赖图收集上下文
- 理解调用链和依赖链
- 分析影响范围

**完整模式** (`mode: "full"`):
- 结合 RAG 和依赖图
- 最全面的上下文

返回结果包含:
- `task` - 任务信息
- `interfaces` - 相关接口（RAG 模式）
- `suggestions` - 架构建议（RAG 模式）
- `files` - 相关文件源码
- `symbols` - 相关符号
- `dependencies` - 依赖关系

**4.2 实现代码**

使用上下文信息，由 Cursor/Claude 完成编码:

1. 阅读相关文件源码
2. 理解现有架构和模式
3. 实现所需功能
4. 遵循项目代码风格

**4.3 验证代码**

```json
// 调用 MCP: user-ai-codegen.verify
{
  "file": "<modified_file>",
  "checks": ["syntax", "type"]
}
```

验证失败时:
- 查看错误详情
- 修复问题
- 重新验证

**4.4 更新任务状态**

```json
// 调用 MCP: user-ai-codegen.task
{
  "action": "update",
  "task_id": "<task_id>",
  "status": "completed"
}
```

---

### Phase 5: 完成

**目标**: 收尾工作

```
进度追踪:
- [ ] 5.1 最终验证
- [ ] 5.2 更新 PRD 状态
- [ ] 5.3 重新索引
```

**5.1 最终验证**

对所有修改的文件运行完整验证:

```json
// 调用 MCP: user-ai-codegen.verify
{
  "file": "<file>",
  "checks": ["syntax", "type", "test"]
}
```

**5.2 更新 PRD 状态**

```json
// 调用 MCP: user-ai-codegen.prd
{
  "action": "update",
  "prd_id": "<prd_id>",
  "status": "completed"
}
```

**5.3 重新提取接口和同步 RAG**

```json
// 重新提取修改文件的接口
// 调用 MCP: user-ai-codegen.extract_interfaces
{
  "paths": ["<modified_paths>"],
  "force": true
}

// 同步到向量数据库
// 调用 MCP: user-ai-codegen.sync_rag
{
  "force": false  // 增量同步
}

// 重新索引知识图谱（可选）
// 调用 MCP: user-ai-codegen.index
{
  "paths": ["<modified_paths>"],
  "force": true
}
```

---

## 断点续做

如果中断，可以恢复进度:

```json
// 查看 PRD 状态
{"action": "get", "prd_id": "<prd_id>"}

// 查看任务列表和状态
{"action": "list", "prd_id": "<prd_id>"}
```

根据 `status` 字段确定从哪个阶段继续。

---

## 快捷流程 (V2)

### 快速开始新需求（接口驱动）

```
1. index(paths=["src"])                                    # 索引代码库
2. extract_interfaces(paths=["src"], force=true)           # 提取接口
3. sync_rag(force=true)                                    # 同步到 RAG
4. prd(action="create", prd_id="feat_xxx", ...)            # 创建 PRD
5. prd(action="analyze", prd_id="feat_xxx")                # 分析 PRD
6. search_interfaces(query="关键词", limit=10)              # 搜索相关接口
7. task(action="plan", prd_id="feat_xxx")                  # 创建任务
8. [循环] context(mode="rag") → 编码 → verify → task.update
9. extract_interfaces(paths=["修改的文件"], force=true)     # 重新提取
10. sync_rag(force=false)                                  # 增量同步
11. prd(action="update", status="completed")
```

### 继续未完成的需求

```
1. prd(action="list")                                      # 找到未完成的 PRD
2. task(action="list", prd_id="xxx")                       # 查看任务状态
3. context(task_id="pending_task", mode="rag")             # RAG 上下文
4. [继续编码]
```

### 代码理解（无 PRD）- V2 增强

```
1. index(paths=["src"])
2. extract_interfaces(paths=["src"])                       # 提取接口
3. sync_rag()                                              # 同步 RAG
4. search_interfaces(query="服务名称", use_hybrid=true)     # 语义搜索接口
5. get_interface(interface_id="xxx", include_deps=true)   # 查看接口详情
6. list_interfaces(module="services", limit=20)            # 浏览接口列表
```

### 接口驱动开发流程

```
1. 提取现有接口: extract_interfaces(paths=["src"])
2. 搜索相似接口: search_interfaces(query="需求描述")
3. 查看接口规范: get_interface(interface_id="xxx")
4. 基于接口生成代码: [使用接口签名和契约]
5. 验证实现: verify(file="xxx", checks=["syntax", "type"])
```

---

## 状态参考

### PRD 状态

| 状态 | 含义 |
|------|------|
| `draft` | 草稿，未分析 |
| `analyzing` | 正在分析 |
| `planned` | 已创建任务 |
| `in_progress` | 正在实现 |
| `completed` | 已完成 |
| `archived` | 已归档 |

### 任务状态

| 状态 | 含义 |
|------|------|
| `pending` | 待开始 |
| `in_progress` | 进行中 |
| `completed` | 已完成 |
| `blocked` | 被阻塞 |
| `cancelled` | 已取消 |

---

## 最佳实践 (V2)

1. **先提取接口后分析** - 确保接口定义是最新的
2. **使用 RAG 语义搜索** - 比关键词搜索更智能
3. **接口驱动编码** - 先理解接口规范，再实现
4. **查看接口契约** - 理解前置条件、后置条件、异常
5. **分析依赖关系** - 理解改动的影响范围
6. **小步迭代** - 每个任务保持小而聚焦
7. **及时验证** - 每次修改后立即验证
8. **更新状态** - 保持 PRD 和任务状态同步
9. **使用 RAG 上下文** - `context(mode="rag")` 提供更智能的上下文
10. **定期同步 RAG** - 修改代码后重新提取和同步接口
