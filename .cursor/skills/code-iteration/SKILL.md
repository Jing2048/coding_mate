---
name: code-iteration
description: 基于 AI CodeGen MCP 的代码迭代流程。使用 MCP 工具进行代码分析、接口提取、RAG 检索、任务追踪，由 Cursor/Claude 完成编码。当用户提到"迭代"、"需求开发"、"新功能开发"、"代码重构"时使用此 skill。
---

# 代码迭代流程

使用 `user-ai-codegen` MCP 服务器进行代码分析和迭代开发。

## 核心原则

- **MCP 提供知识和验证** - 代码分析、接口提取、RAG 检索、任务追踪、代码验证
- **Cursor/Claude 负责编码** - 使用 MCP 提供的上下文完成实际编码
- **持久化追踪** - 所有状态存储在 SQLite，支持断点续做
- **接口驱动开发** - 基于接口规范生成代码，保持契约一致性
- **依赖感知编码** - 理解代码调用关系，分析改动影响范围

## MCP 工具速查

### 代码分析和索引
```
index              - 索引代码库，构建知识图谱
search             - 搜索代码 (symbol/file/content/dependency)
inspect            - 查看文件或符号详情
```

### 接口提取和 RAG
```
extract_interfaces - 从代码提取接口定义（类、函数、方法）
list_interfaces    - 列出所有接口（支持过滤）
get_interface      - 获取接口详情（包含契约和依赖）
search_interfaces  - 语义搜索接口（基于向量相似度）
sync_rag           - 同步数据到向量数据库（用于 RAG 检索）
```

### 任务管理
```
task               - 任务管理 (create/list/get/update)
```

### 代码验证和上下文
```
verify             - 代码验证 (syntax/type/test)
context            - 获取实现上下文（支持 RAG 模式）
```

## 支持的语言

- **Python** - 完整支持
- **JavaScript/TypeScript** - 完整支持
- **Swift** - 完整支持（类、结构体、协议、枚举、扩展）
- **Go, Rust, Java, C/C++** - 基础支持

---

## 完整迭代流程

### Phase 1: 初始化

**目标**: 确保代码库已索引，提取接口

```
进度追踪:
- [ ] 1.1 索引代码库
- [ ] 1.2 提取接口
- [ ] 1.3 同步到 RAG
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

**1.2 提取接口（推荐）**

在索引后，提取接口定义以便后续使用 RAG 搜索：

```json
// 调用 MCP: user-ai-codegen.extract_interfaces
{
  "paths": ["src", "lib"],
  "force": false
}
```

**1.3 同步到 RAG（推荐）**

如果已安装 RAG 依赖，同步接口到向量数据库：

```json
// 调用 MCP: user-ai-codegen.sync_rag
{
  "force": false
}
```

---

### Phase 2: 分析和规划

**目标**: 理解需求，搜索相关代码，规划任务

```
进度追踪:
- [ ] 2.1 搜索相关代码
- [ ] 2.2 查看接口和依赖
- [ ] 2.3 创建任务
```

**2.1 搜索相关代码**

使用多种搜索方式获取上下文：

```json
// 搜索符号
{"query": "<keyword>", "type": "symbol"}

// 搜索依赖
{"query": "<module>", "type": "dependency"}

// 搜索内容
{"query": "<pattern>", "type": "content"}

// 语义搜索接口（推荐，如果已提取接口）
{"query": "<功能描述>", "limit": 10, "use_hybrid": true}
```

**2.2 查看相关接口**

如果已提取接口，可以查看相关接口定义：

```json
// 列出相关接口
{"module": "<module_name>", "entity_type": "class", "limit": 20}

// 获取接口详情
{"interface_id": "<interface_id>", "include_contracts": true, "include_dependencies": true}

// 查看文件或符号详情
{"target": "<file_path>", "include_source": true, "include_deps": true}
```

**2.3 创建任务**

根据分析结果创建任务：

```json
// 调用 MCP: user-ai-codegen.task
{
  "action": "create",
  "task_id": "<task_id>",
  "title": "任务标题",
  "description": "详细描述",
  "files": ["file1.py", "file2.py"]
}
```

---

### Phase 3: 实现（循环）

**目标**: 逐个完成任务

```
对于每个任务:
- [ ] 3.1 获取任务上下文
- [ ] 3.2 实现代码 (Cursor/Claude)
- [ ] 3.3 验证代码
- [ ] 3.4 更新任务状态
```

**3.1 获取任务上下文**

充分利用 MCP 的依赖图和 RAG 能力获取智能上下文：

```json
// 调用 MCP: user-ai-codegen.context
{
  "task_id": "<task_id>",
  "max_tokens": 4000,
  "mode": "rag",        // 推荐: "rag" | "dependency" | "full"
  "format": "prompt",    // 推荐: "prompt" 直接用于 LLM
  "depth": 2            // 依赖遍历深度，默认 1
}
```

**三种模式对比**:

- **`mode="dependency"`** - 基于依赖图收集上下文
  - 从目标文件开始，沿着依赖关系遍历
  - 适合：需要理解调用链和依赖关系
  - 返回：目标文件 + 直接依赖 + 间接依赖（根据 depth）

- **`mode="rag"`** - 基于语义相似度检索上下文（推荐）
  - 理解任务意图，语义搜索相关接口和代码
  - 适合：需要找到功能相似的代码模式
  - 返回：语义相关的接口 + 依赖关系 + 编码建议

- **`mode="full"`** - 结合依赖图和 RAG
  - 既利用依赖关系，又利用语义搜索
  - 适合：复杂任务，需要全面上下文
  - 返回：依赖图 + 语义相关代码 + 完整上下文

**RAG 模式的优势**:
- **智能匹配**: 基于任务描述语义找到相关代码，不依赖精确关键词
- **模式发现**: 自动发现相似功能的实现模式
- **编码建议**: 基于接口契约和依赖关系生成编码建议
- **上下文丰富**: 包含接口定义、契约、依赖、示例代码

返回结果包含:
- `task` - 任务信息
- `interfaces` - 语义相关的接口（RAG 模式）
- `dependencies` - 依赖关系图
- `suggestions` - 编码建议（RAG 模式）
- `formatted_context` - 格式化后的完整上下文（format="prompt" 时可直接使用）

**3.2 利用依赖图分析影响范围**

在编码前，使用依赖图理解改动影响：

```json
// 1. 查看目标接口的依赖关系
{"interface_id": "<interface_id>", "include_dependencies": true}

// 2. 查看谁使用了这个接口
{"interface_id": "<interface_id>", "include_dependents": true}

// 3. 搜索依赖关系
{"query": "<module>", "type": "dependency"}

// 4. 查看文件的依赖图
{"target": "<file_path>", "include_deps": true}
```

**依赖图的价值**:
- **影响分析**: 了解修改某个接口会影响哪些调用者
- **调用链追踪**: 理解代码的执行路径
- **架构理解**: 看清模块间的依赖关系
- **重构安全**: 确保重构不会破坏依赖关系

**3.3 利用 RAG 语义搜索发现模式**

使用语义搜索找到相似功能的实现：

```json
// 语义搜索相关接口
{
  "query": "用户认证服务",
  "limit": 10,
  "use_hybrid": true  // 混合搜索：关键词 + 语义
}

// 获取接口详情（包含契约和依赖）
{
  "interface_id": "<interface_id>",
  "include_contracts": true,
  "include_dependencies": true
}
```

**RAG 搜索的价值**:
- **模式复用**: 找到相似功能的实现，复用代码模式
- **接口发现**: 发现已有的接口定义，避免重复实现
- **契约理解**: 理解接口的前置条件、后置条件、异常规范
- **最佳实践**: 学习项目中已有的最佳实践

**3.4 实现代码**

使用上下文信息，由 Cursor/Claude 完成编码:

**编码策略**:

1. **基于接口契约编码**
   - 查看 `get_interface` 返回的契约信息
   - 遵循前置条件、后置条件、异常规范
   - 保持接口一致性

2. **参考相似实现**
   - 使用 RAG 找到的相似接口作为参考
   - 复用已有的代码模式
   - 保持代码风格一致

3. **考虑依赖影响**
   - 检查依赖关系，确保不破坏现有调用
   - 理解依赖接口的契约
   - 保持向后兼容

4. **利用编码建议**
   - 查看 `context` 返回的 `suggestions`
   - 参考系统生成的编码建议
   - 遵循项目领域规范

**3.3 验证代码**

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

**3.4 更新任务状态**

```json
// 调用 MCP: user-ai-codegen.task
{
  "action": "update",
  "task_id": "<task_id>",
  "status": "completed"
}
```

---

### Phase 4: 完成

**目标**: 收尾工作

```
进度追踪:
- [ ] 4.1 最终验证
- [ ] 4.2 重新索引
```

**4.1 最终验证**

对所有修改的文件运行完整验证:

```json
// 调用 MCP: user-ai-codegen.verify
{
  "file": "<file>",
  "checks": ["syntax", "type", "test"]
}
```

**4.2 重新索引（更新知识图谱）**

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
// 查看任务列表和状态
{"action": "list"}

// 获取任务详情
{"action": "get", "task_id": "<task_id>"}
```

根据任务的 `status` 字段确定从哪个阶段继续。

---

## 快捷流程

### 快速开始新功能

```
1. index(paths=["src"], extensions=[".py", ".ts", ".swift"])
2. extract_interfaces(paths=["src"])  # 可选但推荐
3. sync_rag()  # 可选但推荐（如果已安装 RAG）
4. search_interfaces(query="功能描述")  # 搜索相关接口
5. task(action="create", task_id="xxx", title="...", files=[...])
6. [循环] context(mode="rag") → 编码 → verify → task.update
```

### 继续未完成的任务

```
1. task(action="list")                    # 查看所有任务
2. task(action="get", task_id="xxx")     # 获取任务详情
3. context(task_id="pending_task")       # 获取下一个任务上下文
4. [继续编码]
```

### 代码理解（无任务）

```
1. index(paths=["src"])
2. extract_interfaces(paths=["src"])  # 提取接口
3. sync_rag()  # 同步到 RAG
4. search_interfaces(query="功能描述")  # 语义搜索
5. get_interface(interface_id="xxx")  # 查看接口详情
6. inspect(target="file:symbol")  # 查看符号详情
7. search(query="xxx", type="dependency")  # 查看依赖关系
```

---

## 状态参考

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

### 初始化阶段

1. **先索引后分析** - 确保知识图谱是最新的
2. **提取接口** - 提取接口定义以便使用 RAG 语义搜索
3. **同步 RAG** - 如果已安装 RAG 依赖，同步数据以获得更好的搜索体验

### 分析和规划阶段

4. **组合使用搜索工具**
   - 先用 `search_interfaces` 语义搜索找到相关接口
   - 再用 `search(type="dependency")` 查看依赖关系
   - 最后用 `inspect` 查看详细实现

5. **理解依赖图**
   - 使用 `get_interface(include_dependencies=true)` 查看接口依赖
   - 使用 `inspect(include_deps=true)` 查看文件依赖
   - 分析改动的影响范围，避免破坏性变更

### 实现阶段

6. **充分利用 RAG 模式上下文**
   - 使用 `context(mode="rag")` 获得智能上下文检索
   - 基于语义相似度找到相关代码模式
   - 利用返回的 `suggestions` 获得编码建议

7. **基于接口契约编码**
   - 使用 `get_interface(include_contracts=true)` 查看完整契约
   - 遵循前置条件、后置条件、异常规范
   - 保持接口一致性

8. **参考相似实现**
   - 使用 RAG 搜索找到的相似接口作为参考
   - 复用已有的代码模式和最佳实践
   - 保持代码风格一致

9. **依赖感知编码**
   - 检查依赖关系，确保不破坏现有调用
   - 理解依赖接口的契约
   - 保持向后兼容

### 验证和完成阶段

10. **及时验证** - 每次修改后立即验证
11. **更新状态** - 保持任务状态同步
12. **重新索引** - 修改后重新索引更新知识图谱

### 高级技巧

13. **混合搜索模式** - 使用 `search_interfaces(use_hybrid=true)` 结合关键词和语义搜索
14. **深度依赖遍历** - 使用 `context(depth=2)` 获取更深层的依赖关系
15. **Prompt-ready 格式** - 使用 `context(format="prompt")` 直接获得可用于 LLM 的上下文
16. **多语言支持** - 系统支持 Python、TypeScript、Swift 等多种语言，充分利用语言特定特性

---

## 利用 MCP 能力的完整工作流

### 场景 1: 添加新功能

```
1. 索引代码库 → 提取接口 → 同步 RAG
2. 语义搜索相关功能: search_interfaces(query="相似功能描述")
3. 查看相关接口: get_interface(include_contracts=true, include_dependencies=true)
4. 分析依赖关系: inspect(include_deps=true)
5. 创建任务: task.create(...)
6. 获取智能上下文: context(mode="rag", format="prompt")
   - 系统自动找到语义相关的接口
   - 提供依赖关系图
   - 生成编码建议
7. 基于上下文编码:
   - 参考相似接口的实现模式
   - 遵循接口契约
   - 考虑依赖影响
8. 验证 → 更新任务状态 → 重新索引
```

### 场景 2: 重构代码

```
1. 查看目标接口: get_interface(include_dependents=true)
2. 分析影响范围: 
   - 查看谁使用了这个接口
   - 搜索依赖关系: search(type="dependency")
3. 语义搜索替代方案: search_interfaces(query="新实现方式")
4. 获取重构上下文: context(mode="full", depth=2)
   - 依赖图：理解调用链
   - RAG：找到最佳实践
5. 安全重构:
   - 保持接口契约不变
   - 逐步迁移调用者
   - 验证每个步骤
```

### 场景 3: 理解代码库

```
1. 索引 → 提取接口 → 同步 RAG
2. 语义探索: search_interfaces(query="感兴趣的功能")
3. 查看接口详情: get_interface(include_contracts=true)
4. 追踪依赖链: 
   - inspect(include_deps=true)
   - 递归查看依赖的依赖
5. 发现模式: 使用 RAG 找到相似实现
6. 理解架构: 通过依赖图理解模块关系
```

### 场景 4: 修复 Bug

```
1. 定位问题代码: search(type="symbol", query="问题函数")
2. 查看实现: inspect(include_source=true)
3. 分析依赖: inspect(include_deps=true)
4. 语义搜索修复模式: search_interfaces(query="类似问题的解决方案")
5. 获取修复上下文: context(mode="rag")
   - 找到相似问题的处理方式
   - 理解依赖关系
6. 安全修复:
   - 保持接口契约
   - 不影响依赖者
   - 添加测试
```
