---
name: prd-iteration
description: 基于 AI CodeGen MCP 的完整需求迭代流程。使用 MCP 工具进行代码分析、PRD 管理、任务追踪，由 Cursor/Claude 完成编码。当用户提到"迭代"、"PRD"、"需求开发"、"新功能开发"时使用此 skill。
---

# PRD 迭代流程

使用 `user-ai-codegen` MCP 服务器管理完整的需求迭代生命周期。

## 核心原则

- **MCP 提供知识和验证** - 代码分析、PRD 管理、任务追踪、代码验证
- **Cursor/Claude 负责编码** - 使用 MCP 提供的上下文完成实际编码
- **持久化追踪** - 所有状态存储在 SQLite，支持断点续做

## MCP 工具速查

```
index    - 索引代码库
search   - 搜索代码 (symbol/file/content/dependency)
inspect  - 查看文件或符号详情
prd      - PRD 管理 (create/analyze/list/get/update)
task     - 任务管理 (create/list/get/update/plan)
verify   - 代码验证 (syntax/type/test)
context  - 获取实现上下文
```

---

## 完整迭代流程

### Phase 1: 初始化

**目标**: 确保代码库已索引，创建 PRD

```
进度追踪:
- [ ] 1.1 索引代码库
- [ ] 1.2 创建 PRD
```

**1.1 索引代码库**

```json
// 调用 MCP: user-ai-codegen.index
{
  "paths": ["src", "lib"],
  "extensions": [".py", ".ts", ".js"],
  "force": false
}
```

检查返回的 `total_files` 和 `total_nodes`，确保代码库已被正确索引。

**1.2 创建 PRD**

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

### Phase 2: 分析

**目标**: 分析 PRD 影响范围，识别改动点

```
进度追踪:
- [ ] 2.1 分析 PRD
- [ ] 2.2 审查影响范围
- [ ] 2.3 确认改动点
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

**2.2 审查影响范围**

对于每个 `impacted_file`，使用 `inspect` 查看详情:

```json
// 调用 MCP: user-ai-codegen.inspect
{
  "target": "<file_path>",
  "include_source": true,
  "include_deps": true
}
```

**2.3 搜索相关代码**

如需更多上下文，使用 `search`:

```json
// 搜索符号
{"query": "<keyword>", "type": "symbol"}

// 搜索依赖
{"query": "<module>", "type": "dependency"}

// 搜索内容
{"query": "<pattern>", "type": "content"}
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

**4.1 获取任务上下文**

```json
// 调用 MCP: user-ai-codegen.context
{
  "task_id": "<task_id>",
  "max_tokens": 4000
}
```

返回结果包含:
- `task` - 任务信息
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

**5.3 重新索引（更新知识图谱）**

```json
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

## 快捷流程

### 快速开始新需求

```
1. index(paths=["src"])
2. prd(action="create", prd_id="feat_xxx", title="...", content="...")
3. prd(action="analyze", prd_id="feat_xxx")
4. task(action="plan", prd_id="feat_xxx")
5. [循环] context → 编码 → verify → task.update
6. prd(action="update", status="completed")
```

### 继续未完成的需求

```
1. prd(action="list")                    # 找到未完成的 PRD
2. task(action="list", prd_id="xxx")     # 查看任务状态
3. context(task_id="pending_task")       # 获取下一个任务上下文
4. [继续编码]
```

### 代码理解（无 PRD）

```
1. index(paths=["src"])
2. search(query="xxx", type="symbol")
3. inspect(target="file:symbol")
4. search(query="xxx", type="dependency")
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

## 最佳实践

1. **先索引后分析** - 确保知识图谱是最新的
2. **小步迭代** - 每个任务保持小而聚焦
3. **及时验证** - 每次修改后立即验证
4. **更新状态** - 保持 PRD 和任务状态同步
5. **使用上下文** - 充分利用 `context` 工具获取相关代码
