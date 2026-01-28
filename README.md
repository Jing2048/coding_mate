# AI CodeGen MCP Server

一个基于 MCP (Model Context Protocol) 的高可靠性 AI 编码系统，专注于**更好的编码**而非仅仅完成需求。

**版本**: V2.0

---

## 📋 目录

- [系统简介](#系统简介)
- [核心特性](#核心特性)
- [系统要求](#系统要求)
- [安装指南](#安装指南)
- [快速开始](#快速开始)
- [MCP 工具](#mcp-工具)
- [使用示例](#使用示例)
- [项目结构](#项目结构)
- [文档](#文档)
- [故障排除](#故障排除)
- [版本历史](#版本历史)
- [许可证](#许可证)

---

## 🎯 系统简介

AI CodeGen MCP Server 是一个智能代码分析和生成系统，通过理解代码的接口、依赖关系和架构，为 AI 编码助手提供高质量的上下文信息。

### 核心理念

**从"完成需求"到"更好的编码"**

- **V1**: 关注功能实现，PRD → 任务 → 编码 → 验证
- **V2**: 关注代码质量，接口驱动开发，依赖感知编码，架构级别建议

---

## ✨ 核心特性

### 1. 接口自动提取

- 从代码自动提取接口定义（类、函数、方法）
- 识别方法签名、类型信息、契约
- 检测模块边界和依赖关系
- 支持多种编程语言（Python、JavaScript、TypeScript 等）

### 2. RAG 增强检索

- 向量化存储代码实体
- 语义搜索接口和依赖
- 智能上下文检索
- 混合搜索（关键词 + 语义）

### 3. 依赖感知编码

- 理解代码调用关系
- 分析改动影响范围
- 保持接口契约一致性
- 构建完整的代码知识图谱

### 4. 专业编码辅助

- 基于接口规范生成代码
- 架构级别建议
- 关注代码质量、可维护性
- 提供完整的实现上下文

---

## 💻 系统要求

- **Python**: >= 3.8
- **操作系统**: macOS, Linux, Windows
- **内存**: 建议 >= 4GB（RAG 系统需要额外内存）
- **磁盘空间**: 至少 500MB（用于模型和数据库）

---

## 📦 安装指南

### 步骤 1: 克隆仓库

```bash
git clone <repository-url>
cd LLM
```

### 步骤 2: 创建虚拟环境

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# macOS/Linux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate
```

### 步骤 3: 安装基础依赖

```bash
# 升级 pip
pip install --upgrade pip

# 安装基础依赖
pip install -r requirements.txt
```

**基础依赖包括**:
- `mcp>=1.0.0` - MCP 服务器框架
- `tree-sitter>=0.21.0` - 代码解析器
- `tree-sitter-python`, `tree-sitter-javascript` 等 - 语言支持

### 步骤 4: 安装 RAG 系统依赖（可选）

RAG 系统提供语义搜索功能，是可选的。如果不安装，系统会自动降级到 SQLite 搜索模式。

#### 方式 1: 使用安装脚本（推荐）

```bash
# Bash 版本（增强版，包含错误处理）
./install_rag_deps.sh

# 或 Python 版本（更详细的错误信息）
python install_rag_deps_alternative.py
```

#### 方式 2: 手动安装

```bash
# 标准安装
pip install chromadb sentence-transformers

# 或使用国内镜像（如果网络较慢）
pip install chromadb sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 方式 3: 分步安装

```bash
# 1. 安装 chromadb
pip install chromadb>=0.4.22

# 2. 安装 sentence-transformers
pip install sentence-transformers>=2.2.0
```

**注意**: sentence-transformers 首次安装会下载模型文件（约 80MB），可能需要几分钟。

### 步骤 5: 验证安装

```bash
# 验证基础功能
python -c "from ai_codegen.mcp_server.server import AICodeGenServer; print('✓ 基础功能正常')"

# 验证 RAG 系统（如果已安装）
python -c "
from ai_codegen.mcp_server.server import AICodeGenServer
server = AICodeGenServer('.')
rag = server.rag_manager
if rag:
    print('✅ RAG 系统可用')
else:
    print('⚠️  RAG 系统不可用（将使用 SQLite 降级模式）')
"
```

**详细安装指南**: 参见 [INSTALL_RAG.md](INSTALL_RAG.md)

---

## 🚀 快速开始

### 1. MCP 配置（Cursor）

在 Cursor 的 MCP 配置文件中添加（通常位于 `~/.cursor/mcp.json` 或 Cursor 设置中）：

```json
{
  "mcpServers": {
    "ai-codegen": {
      "command": "/path/to/LLM/.venv/bin/python",
      "args": [
        "-m",
        "ai_codegen.mcp_server.server",
        "--workspace",
        "/path/to/your/project"
      ],
      "env": {
        "PYTHONPATH": "/path/to/LLM"
      }
    }
  }
}
```

**重要**: 
- 将 `/path/to/LLM` 替换为实际的仓库路径
- 将 `/path/to/your/project` 替换为要分析的项目路径
- 确保使用虚拟环境中的 Python 解释器

### 2. 基本使用（Python API）

```python
from ai_codegen.mcp_server.server import AICodeGenServer
import asyncio

async def main():
    # 初始化服务器
    server = AICodeGenServer("/path/to/workspace")
    
    # 1. 索引代码库
    index_result = await server.tool_index(
        paths=[],
        extensions=[".py"],
        force=False
    )
    print(f"索引完成: {index_result['indexed']} 个文件")
    
    # 2. 提取接口
    extract_result = await server.tool_extract_interfaces(
        paths=["src/"],
        force=True
    )
    print(f"提取了 {extract_result['extracted']} 个接口")
    
    # 3. 同步到向量数据库（需要 RAG 依赖）
    if server.rag_manager:
        sync_result = await server.tool_sync_rag(force=True)
        print(f"同步完成: {sync_result['stats']}")
    
    # 4. 搜索接口
    search_result = await server.tool_search_interfaces(
        query="用户认证服务",
        limit=10,
        use_hybrid=True
    )
    print(f"找到 {search_result['total']} 个结果")
    
    # 5. 获取上下文
    context = await server.tool_context(
        mode="rag",  # 或 "dependency" 或 "full"
        max_tokens=4000,
        format="prompt"
    )
    print(f"上下文已准备，共 {context['total_tokens']} tokens")

asyncio.run(main())
```

### 3. 命令行使用

```bash
# 启动 MCP 服务器
python -m ai_codegen.mcp_server.server --workspace /path/to/project
```

---

## 🔧 MCP 工具

系统提供 11 个 MCP 工具，分为两类：

### V2 新工具（接口和 RAG）

| 工具 | 功能 | 状态 |
|------|------|------|
| `extract_interfaces` | 从代码提取接口定义 | ✅ |
| `get_interface` | 获取接口详情 | ✅ |
| `list_interfaces` | 列出所有接口 | ✅ |
| `search_interfaces` | 语义搜索接口 | ✅ |
| `sync_rag` | 同步数据到向量数据库 | ✅ |
| `context` (增强) | 获取上下文（支持 RAG） | ✅ |

### V1 工具（代码分析）

| 工具 | 功能 | 状态 |
|------|------|------|
| `index` | 索引代码库，构建知识图谱 | ✅ |
| `search` | 搜索代码（符号/文件/内容/依赖） | ✅ |
| `inspect` | 查看文件或符号的详细信息 | ✅ |
| `prd` | PRD 生命周期管理 | ✅ |
| `task` | 任务管理 | ✅ |
| `verify` | 代码验证（语法/类型/测试） | ✅ |

**详细文档**: [MCP 工具参考](docs/api/MCP_TOOLS.md)

---

## 📖 使用示例

### 示例 1: 提取和搜索接口

```python
from ai_codegen.mcp_server.server import AICodeGenServer
import asyncio

async def example():
    server = AICodeGenServer(".")
    
    # 提取接口
    result = await server.tool_extract_interfaces(
        paths=["ai_codegen/rag/rag_manager.py"]
    )
    print(f"提取了 {result['extracted']} 个接口")
    
    # 列出接口
    interfaces = await server.tool_list_interfaces(limit=10)
    print(f"共有 {interfaces['total']} 个接口")
    
    # 搜索接口
    search = await server.tool_search_interfaces(
        query="RAG 管理器",
        limit=5
    )
    for item in search['results']:
        print(f"- {item['name']}: {item['description']}")

asyncio.run(example())
```

### 示例 2: 获取实现上下文

```python
async def get_context():
    server = AICodeGenServer(".")
    
    # 使用 RAG 模式获取上下文
    context = await server.tool_context(
        files=["ai_codegen/rag/rag_manager.py"],
        mode="rag",
        max_tokens=2000,
        format="prompt"
    )
    
    print(context['formatted_context'])

asyncio.run(get_context())
```

### 示例 3: 代码验证

```python
async def verify_code():
    server = AICodeGenServer(".")
    
    result = await server.tool_verify(
        file="ai_codegen/rag/rag_manager.py",
        checks=["syntax", "type"]
    )
    
    print(f"语法检查: {result['syntax']['valid']}")
    print(f"类型检查: {result['type']['valid']}")

asyncio.run(verify_code())
```

**更多示例**: 参见 [docs/examples/](docs/examples/)

---

## 📊 项目结构

```
LLM/
├── README.md                    # 本文件
├── requirements.txt             # Python 依赖
├── install_rag_deps.sh         # RAG 依赖安装脚本
├── install_rag_deps_alternative.py  # RAG 安装脚本（Python 版）
├── INSTALL_RAG.md              # RAG 安装指南
│
├── ai_codegen/                 # 主代码包
│   ├── models/                 # 数据模型
│   │   └── code_entity.py      # CodeEntity 统一模型
│   ├── extractor/              # 接口提取器
│   │   ├── interface_extractor.py
│   │   ├── contract_inferencer.py
│   │   └── boundary_detector.py
│   ├── rag/                    # RAG 系统
│   │   ├── vector_store.py     # 向量存储
│   │   ├── embedder.py         # 嵌入模型
│   │   ├── semantic_searcher.py # 语义搜索
│   │   ├── context_retriever.py # 上下文检索
│   │   └── rag_manager.py      # RAG 管理器
│   ├── parser/                 # 代码解析
│   │   ├── tree_sitter_parser.py
│   │   ├── dependency_extractor.py
│   │   └── relationship_extractor.py
│   ├── mcp_server/             # MCP 服务器
│   │   ├── server.py           # 主服务器
│   │   └── persistence_v2.py   # 数据持久化
│   └── verifier/               # 代码验证
│       ├── verifier.py
│       ├── syntax_checker.py
│       └── type_checker.py
│
├── docs/                       # 文档目录
│   ├── design/                 # 设计文档
│   ├── implementation/         # 实施文档
│   ├── api/                    # API 文档
│   └── examples/               # 使用示例
│
└── examples/                   # 示例代码
    └── data_model_usage.py
```

---

## 📚 文档

### 核心文档

- **[设计哲学](docs/design/DESIGN_PHILOSOPHY.md)** - 核心理念和设计原则
- **[数据模型](docs/design/DATA_MODEL.md)** - CodeEntity 统一数据模型
- **[系统架构](docs/design/ARCHITECTURE.md)** - 架构设计和组件关系

### 实施文档

- **[接口提取实施](docs/implementation/INTERFACE_EXTRACTION.md)** - 接口自动提取实现
- **[RAG 系统实施](docs/implementation/RAG_SYSTEM.md)** - RAG 系统构建实现
- **[系统总结](docs/implementation/SYSTEM_SUMMARY.md)** - 系统完成总结
- **[测试报告](docs/implementation/TEST_REPORT.md)** - 测试验证结果

### API 文档

- **[MCP 工具参考](docs/api/MCP_TOOLS.md)** - 所有 MCP 工具详细说明

### 使用示例

- **[基础使用](docs/examples/BASIC_USAGE.md)** - 基本使用场景
- **[完整工作流](docs/examples/WORKFLOW.md)** - 端到端工作流示例

### 安装指南

- **[RAG 系统安装指南](INSTALL_RAG.md)** - RAG 依赖安装和故障排除

---

## 🔍 故障排除

### RAG 系统安装失败

**问题**: `chromadb` 或 `sentence-transformers` 安装失败

**解决方案**:
1. 检查 Python 版本: `python --version`（需要 >= 3.8）
2. 升级 pip: `pip install --upgrade pip`
3. 使用国内镜像: `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple chromadb sentence-transformers`
4. 查看详细日志: `cat /tmp/chromadb_install.log`
5. 参考 [INSTALL_RAG.md](INSTALL_RAG.md) 获取更多帮助

### MCP 服务器无法启动

**问题**: Cursor 中无法连接到 MCP 服务器

**解决方案**:
1. 检查路径是否正确（使用绝对路径）
2. 确保虚拟环境已激活
3. 检查 PYTHONPATH 环境变量
4. 查看 Cursor 的 MCP 日志

### 接口提取失败

**问题**: `extract_interfaces` 返回空结果

**解决方案**:
1. 检查文件路径是否正确
2. 确保文件扩展名在支持列表中（.py, .js, .ts 等）
3. 检查代码语法是否正确
4. 尝试使用 `force=True` 强制重新提取

### RAG 搜索返回空结果

**问题**: `search_interfaces` 没有找到结果

**解决方案**:
1. 确保已运行 `sync_rag` 同步数据
2. 检查 RAG 系统是否可用: `server.rag_manager`
3. 尝试使用 SQLite 降级模式: `mode="dependency"`
4. 检查查询关键词是否合适

**更多故障排除**: 参见 [INSTALL_RAG.md](INSTALL_RAG.md) 和 [测试报告](docs/implementation/TEST_REPORT.md)

---

## 🗺️ 版本历史

### V2.0 (当前)

- ✅ 接口自动提取
- ✅ RAG 系统构建
- ✅ 依赖感知编码
- ✅ 专业编码辅助

### V1.0

- 基础代码分析
- PRD 和任务管理
- 代码验证

---

## 📄 许可证

MIT License

---

## 🔗 相关链接

- [设计哲学](docs/design/DESIGN_PHILOSOPHY.md)
- [系统架构](docs/design/ARCHITECTURE.md)
- [MCP 工具参考](docs/api/MCP_TOOLS.md)
- [RAG 安装指南](INSTALL_RAG.md)
- [测试报告](docs/implementation/TEST_REPORT.md)

---

## 💬 支持

如有问题或建议，请：
1. 查看 [故障排除](#故障排除) 部分
2. 参考 [文档](#文档) 部分
3. 查看 [测试报告](docs/implementation/TEST_REPORT.md) 了解已知问题

---

**最后更新**: 2026-01-28
