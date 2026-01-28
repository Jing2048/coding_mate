# AI CodeGen

一个基于 MCP (Model Context Protocol) 的代码工程辅助系统。

**核心理念**：MCP 提供代码分析、PRD 管理和验证能力，**编码工作交给 Cursor/Claude**。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Cursor / Claude                       │
│                    (负责编码工作)                         │
└─────────────────────────────────────────────────────────┘
                           │
                           │ MCP Protocol
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  AI CodeGen MCP Server                   │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Tools:                                              ││
│  │  • index    - 索引代码库                             ││
│  │  • search   - 搜索代码                               ││
│  │  • inspect  - 查看符号/文件详情                      ││
│  │  • prd      - PRD 生命周期管理                       ││
│  │  • task     - 任务管理                               ││
│  │  • verify   - 代码验证                               ││
│  │  • context  - 获取实现上下文                          ││
│  └─────────────────────────────────────────────────────┘│
│                           │                              │
│     ┌─────────────────────┴─────────────────────┐       │
│     │           SQLite 持久化存储                │       │
│     │  • 解析结果  • 知识图谱  • PRD  • 任务     │       │
│     └───────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

## 安装

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## MCP 配置

在 Cursor 的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "ai-codegen": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "ai_codegen.mcp_server.server", "--workspace", "/path/to/project"],
      "env": {
        "PYTHONPATH": "/path/to/LLM"
      }
    }
  }
}
```

## MCP 工具

### index - 索引代码库

构建代码知识图谱，支持增量索引。

```json
{
  "paths": ["src"],
  "extensions": [".py"],
  "force": false
}
```

### search - 搜索代码

支持符号、文件、内容、依赖搜索。

```json
{
  "query": "UserService",
  "type": "symbol",
  "limit": 20
}
```

### inspect - 查看详情

获取文件或符号的详细信息，包括源码和依赖。

```json
{
  "target": "src/services/user.py:UserService",
  "include_source": true,
  "include_deps": true
}
```

### prd - PRD 管理

管理需求文档的完整生命周期。

```json
// 创建 PRD
{"action": "create", "prd_id": "feat_001", "title": "用户认证", "content": "..."}

// 分析 PRD，识别影响的代码
{"action": "analyze", "prd_id": "feat_001"}

// 列出所有 PRD
{"action": "list"}

// 获取 PRD 详情
{"action": "get", "prd_id": "feat_001"}

// 更新状态
{"action": "update", "prd_id": "feat_001", "status": "in_progress"}
```

### task - 任务管理

从 PRD 创建和管理实现任务。

```json
// 从 PRD 自动创建任务
{"action": "plan", "prd_id": "feat_001"}

// 列出任务
{"action": "list", "prd_id": "feat_001"}

// 更新任务状态
{"action": "update", "task_id": "task_001", "status": "completed"}
```

### verify - 代码验证

验证代码的语法、类型和测试。

```json
{
  "file": "src/services/user.py",
  "checks": ["syntax", "type", "test"]
}
```

### context - 获取上下文

获取实现任务所需的上下文，可直接用于 prompt。

```json
{
  "task_id": "task_001",
  "files": ["src/models/user.py"],
  "max_tokens": 4000
}
```

## 典型工作流

### 1. 新需求开发

```
1. 索引代码库
   index(paths=["src"])

2. 创建 PRD
   prd(action="create", prd_id="feat_auth", content="实现用户认证...")

3. 分析 PRD，找出影响的代码
   prd(action="analyze", prd_id="feat_auth")

4. 自动创建任务
   task(action="plan", prd_id="feat_auth")

5. 获取任务上下文
   context(task_id="feat_auth_task_1")

6. [Cursor/Claude 完成编码]

7. 验证代码
   verify(file="src/auth/service.py", checks=["syntax", "type"])

8. 更新任务状态
   task(action="update", task_id="feat_auth_task_1", status="completed")
```

### 2. 代码理解

```
1. 搜索符号
   search(query="authenticate", type="symbol")

2. 查看详情
   inspect(target="src/auth/service.py:authenticate")

3. 查看依赖
   search(query="AuthService", type="dependency")
```

## 项目结构

```
ai_codegen/
├── mcp_server/         # MCP 服务器
│   ├── server.py       # 服务实现
│   └── persistence.py  # 持久化存储
├── parser/             # 代码解析
│   ├── tree_sitter_parser.py
│   └── dependency_extractor.py
├── graph/              # 知识图谱
├── verifier/           # 代码验证
└── visualization/      # 可视化
```

## License

MIT
