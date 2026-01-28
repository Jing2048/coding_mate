# 系统架构

## 整体架构

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
│  │ V2 Tools:                                           ││
│  │  • extract_interfaces - 接口提取                    ││
│  │  • get_interface     - 接口详情                     ││
│  │  • list_interfaces   - 接口列表                     ││
│  │  • search_interfaces - 语义搜索                     ││
│  │  • sync_rag          - RAG 同步                     ││
│  │  • context (增强)    - 上下文检索                    ││
│  └─────────────────────────────────────────────────────┘│
│                           │                              │
│     ┌─────────────────────┴─────────────────────┐       │
│     │         V2 数据层                        │       │
│     │  ┌─────────────────────────────────────┐ │       │
│     │  │ SQLite (结构化存储)                 │ │       │
│     │  │  • CodeEntity                      │ │       │
│     │  │  • Dependencies                    │ │       │
│     │  └─────────────────────────────────────┘ │       │
│     │  ┌─────────────────────────────────────┐ │       │
│     │  │ Chroma (向量存储)                    │ │       │
│     │  │  • Embeddings                      │ │       │
│     │  │  • Semantic Search                 │ │       │
│     │  └─────────────────────────────────────┘ │       │
│     └───────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. 数据模型层

**CodeEntity** - 统一的代码实体模型

```python
@dataclass
class CodeEntity:
    id: str
    name: str
    type: EntityType  # class, function, method, module
    module: str
    signature: Signature
    dependencies: List[Dependency]
    contracts: Contract
    boundary: Boundary
    embedding_text: str  # 用于向量化
```

### 2. 提取层

**InterfaceExtractor** - 自动提取接口定义
- 从 AST 提取类和函数
- 识别方法签名和类型
- 推断接口契约

**ContractInferencer** - 推断接口契约
- 前置条件
- 后置条件
- 异常规范
- 不变量

**ModuleBoundaryDetector** - 检测模块边界
- 输入输出识别
- 副作用检测

### 3. RAG 层

**VectorStore** - Chroma 向量存储
- 实体向量化存储
- 元数据过滤
- 批量操作

**Embedder** - sentence-transformers 嵌入
- 文本向量化
- 批量嵌入

**SemanticSearcher** - 语义搜索
- 向量相似度搜索
- 混合搜索（关键词 + 语义）
- 相关性评分

**ContextRetriever** - 上下文检索
- 任务意图理解
- 相关接口推荐
- 依赖关系扩展

**RAGManager** - 统一管理接口

### 4. 持久化层

**PersistenceManagerV2** - SQLite 存储
- CodeEntity 存储
- 依赖关系存储
- 查询接口

### 5. MCP 服务层

**AICodeGenServer** - MCP 服务器
- 工具注册和分发
- 工作流编排
- 错误处理

## 数据流

### 接口提取流程

```
源代码
  ↓
[TreeSitterParser] 解析
  ↓
AST + Symbols
  ↓
[InterfaceExtractor] 提取
  ↓
CodeEntity
  ↓
[PersistenceManagerV2] 存储到 SQLite
  ↓
[RAGManager] 向量化并存储到 Chroma
```

### 搜索流程

```
查询文本
  ↓
[Embedder] 向量化
  ↓
[VectorStore] 相似度搜索
  ↓
[SemanticSearcher] 排序和过滤
  ↓
[PersistenceManagerV2] 获取完整实体
  ↓
搜索结果
```

### 上下文检索流程

```
任务描述
  ↓
[ContextRetriever] 理解意图
  ↓
[SemanticSearcher] 搜索相关接口
  ↓
[ContextRetriever] 扩展依赖关系
  ↓
[ContextRetriever] 格式化上下文
  ↓
LLM 上下文
```

## 技术栈

### 核心依赖

- **tree-sitter** - 代码解析
- **SQLite** - 结构化存储
- **Chroma** - 向量存储
- **sentence-transformers** - 文本嵌入

### 支持的语言

- Python
- JavaScript / TypeScript
- Go
- Rust
- Java
- C++ / C
- Ruby
- Swift

## 设计原则

1. **接口驱动** - 围绕接口而非实现
2. **依赖感知** - 理解代码关系
3. **知识增强** - RAG 提升检索能力
4. **专业辅助** - 架构级别建议

---

**版本**: V2.0  
**最后更新**: 2026-01-28
