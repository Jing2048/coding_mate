# 仓库结构

## 📁 目录结构

```
LLM/
├── README.md                    # 主入口文档
├── REPOSITORY_STRUCTURE.md      # 本文件
├── requirements.txt             # Python 依赖
├── install_phase2_deps.sh      # Phase 2 依赖安装脚本
│
├── docs/                        # 文档目录
│   ├── README.md               # 文档索引
│   ├── CHANGELOG.md            # 更新日志
│   ├── design/                 # 设计文档
│   │   ├── DESIGN_PHILOSOPHY.md
│   │   ├── DATA_MODEL.md
│   │   └── ARCHITECTURE.md
│   ├── implementation/         # 实施文档
│   │   ├── V2_ROADMAP.md
│   │   ├── V2_SUMMARY.md
│   │   ├── PHASE1.md
│   │   ├── PHASE2.md
│   │   ├── PHASE2_TEST_REPORT.md
│   │   └── PHASE2_FINAL_REPORT.md
│   ├── api/                    # API 文档
│   │   └── MCP_TOOLS.md
│   └── examples/               # 使用示例
│       ├── BASIC_USAGE.md
│       └── WORKFLOW.md
│
├── ai_codegen/                  # 主代码包
│   ├── __init__.py
│   ├── models/                 # 数据模型
│   │   ├── __init__.py
│   │   └── code_entity.py
│   ├── extractor/              # 接口提取器
│   │   ├── __init__.py
│   │   ├── interface_extractor.py
│   │   ├── contract_inferencer.py
│   │   └── boundary_detector.py
│   ├── rag/                    # RAG 系统
│   │   ├── __init__.py
│   │   ├── vector_store.py
│   │   ├── embedder.py
│   │   ├── semantic_searcher.py
│   │   ├── context_retriever.py
│   │   └── rag_manager.py
│   ├── parser/                 # 代码解析
│   │   ├── __init__.py
│   │   ├── tree_sitter_parser.py
│   │   ├── relationship_extractor.py
│   │   └── dependency_extractor.py
│   ├── mcp_server/            # MCP 服务器
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── persistence.py
│   │   └── persistence_v2.py
│   └── verifier/              # 代码验证
│       ├── __init__.py
│       ├── verifier.py
│       ├── syntax_checker.py
│       ├── type_checker.py
│       └── test_runner.py
│
├── examples/                   # 示例代码
│   └── data_model_usage.py
│
├── test_*.py                  # 测试脚本
│   ├── test_v2_phase1.py
│   ├── test_phase2_without_deps.py
│   └── test_phase2_complete.py
│
└── .cursor/                   # Cursor 配置
    └── skills/
        └── prd-iteration/
```

## 📄 关键文件说明

### 文档

- `README.md` - 项目主入口，快速开始指南
- `docs/README.md` - 文档索引和导航
- `docs/design/` - 设计文档（设计哲学、数据模型、架构）
- `docs/implementation/` - 实施文档（路线图、Phase 实施、测试报告）
- `docs/api/` - API 文档（MCP 工具参考）
- `docs/examples/` - 使用示例

### 代码

- `ai_codegen/models/` - CodeEntity 统一数据模型
- `ai_codegen/extractor/` - 接口自动提取（Phase 1）
- `ai_codegen/rag/` - RAG 系统（Phase 2）
- `ai_codegen/mcp_server/` - MCP 服务器实现

### 测试

- `test_v2_phase1.py` - Phase 1 测试
- `test_phase2_without_deps.py` - Phase 2 基础测试
- `test_phase2_complete.py` - Phase 2 完整测试

---

**版本**: V2.0  
**最后更新**: 2026-01-28
