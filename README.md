# AI CodeGen MCP Server

一个基于 MCP (Model Context Protocol) 的高可靠性 AI 编码系统，专注于**更好的编码**而非仅仅完成需求。

**版本**: V2.0 (Phase 2 完成)

---

## 🎯 核心理念

### 从"完成需求"到"更好的编码"

**V1**: 关注功能实现，PRD → 任务 → 编码 → 验证

**V2**: 关注代码质量，接口驱动开发，依赖感知编码，架构级别建议

---

## 🏗️ 核心能力

### 1. 接口自动提取 (Phase 1 ✅)

- 从代码自动提取接口定义
- 识别方法签名、类型信息、契约
- 检测模块边界和依赖关系

### 2. RAG 增强检索 (Phase 2 ✅)

- 向量化存储代码实体
- 语义搜索接口和依赖
- 智能上下文检索

### 3. 依赖感知编码

- 理解代码调用关系
- 分析改动影响范围
- 保持接口契约一致性

### 4. 专业编码辅助

- 基于接口规范生成代码
- 架构级别建议
- 关注代码质量、可维护性

---

## 📦 安装

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装 Phase 2 RAG 依赖（可选，用于语义搜索）
./install_phase2_deps.sh
```

---

## 🚀 快速开始

### 1. MCP 配置

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

### 2. 基本使用

```python
from ai_codegen.mcp_server.server import AICodeGenServer
import asyncio

server = AICodeGenServer("/path/to/workspace")

# 提取接口
await server.tool_extract_interfaces(paths=["src/"])

# 同步到向量数据库（需要 RAG 依赖）
await server.tool_sync_rag(force=True)

# 语义搜索
results = await server.tool_search_interfaces(
    query="用户认证服务",
    use_hybrid=True
)

# 获取上下文
context = await server.tool_context(
    mode="rag",
    max_tokens=4000
)
```

---

## 📚 文档

### 核心文档

- **[设计哲学](docs/design/DESIGN_PHILOSOPHY.md)** - V2 设计理念和原则
- **[数据模型](docs/design/DATA_MODEL.md)** - CodeEntity 统一数据模型
- **[架构概览](docs/design/ARCHITECTURE.md)** - 系统架构设计

### 实施文档

- **[Phase 1 实施](docs/implementation/PHASE1.md)** - 接口自动提取
- **[Phase 2 实施](docs/implementation/PHASE2.md)** - RAG 系统构建
- **[V2 路线图](docs/implementation/V2_ROADMAP.md)** - 完整迭代计划

### API 文档

- **[MCP 工具参考](docs/api/MCP_TOOLS.md)** - 所有 MCP 工具说明
- **[RAG API](docs/api/RAG_API.md)** - RAG 系统 API

### 使用示例

- **[基础示例](docs/examples/BASIC_USAGE.md)** - 基本使用场景
- **[完整工作流](docs/examples/WORKFLOW.md)** - 端到端工作流

---

## 🔧 MCP 工具

### V2 新工具

| 工具 | 功能 | 状态 |
|------|------|------|
| `extract_interfaces` | 从代码提取接口定义 | ✅ |
| `get_interface` | 获取接口详情 | ✅ |
| `list_interfaces` | 列出所有接口 | ✅ |
| `search_interfaces` | 语义搜索接口 | ✅ |
| `sync_rag` | 同步数据到向量数据库 | ✅ |

### V1 工具（保留）

| 工具 | 功能 | 状态 |
|------|------|------|
| `index` | 索引代码库 | ✅ |
| `search` | 搜索代码 | ✅ |
| `inspect` | 查看详情 | ✅ |
| `prd` | PRD 管理 | ✅ |
| `task` | 任务管理 | ✅ |
| `verify` | 代码验证 | ✅ |
| `context` | 获取上下文（已增强） | ✅ |

详细文档: [MCP 工具参考](docs/api/MCP_TOOLS.md)

---

## 🧪 测试

```bash
# 基础功能测试（不依赖 RAG）
python test_phase2_without_deps.py

# 完整功能测试（需要 RAG 依赖）
python test_phase2_complete.py
```

---

## 📊 项目结构

```
ai_codegen/
├── models/              # 数据模型
│   └── code_entity.py   # CodeEntity 统一模型
├── extractor/           # 接口提取器
│   ├── interface_extractor.py
│   ├── contract_inferencer.py
│   └── boundary_detector.py
├── rag/                 # RAG 系统
│   ├── vector_store.py
│   ├── embedder.py
│   ├── semantic_searcher.py
│   ├── context_retriever.py
│   └── rag_manager.py
├── parser/              # 代码解析
│   ├── tree_sitter_parser.py
│   └── relationship_extractor.py
├── mcp_server/          # MCP 服务器
│   ├── server.py
│   └── persistence_v2.py
└── verifier/            # 代码验证
```

---

## 🗺️ 版本历史

### V2.0 (当前)

- ✅ Phase 1: 接口自动提取
- ✅ Phase 2: RAG 系统构建
- ⏳ Phase 3: 专业编码辅助（规划中）
- ⏳ Phase 4: 集成和优化（规划中）

### V1.0

- 基础代码分析
- PRD 和任务管理
- 代码验证

---

## 📄 License

MIT

---

## 🔗 相关文档

- [设计哲学](docs/design/DESIGN_PHILOSOPHY.md)
- [V2 路线图](docs/implementation/V2_ROADMAP.md)
- [测试报告](docs/implementation/PHASE2_TEST_REPORT.md)
