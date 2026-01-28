# Phase 2: RAG 系统构建 - 详细实施计划

## 🎯 Phase 2 目标

构建完整的 RAG（Retrieval-Augmented Generation）系统，实现：
1. **向量化存储** - 将 CodeEntity 向量化并存储到 Chroma
2. **语义搜索** - 基于向量相似度搜索接口和依赖
3. **上下文检索** - 为任务智能检索相关上下文
4. **LLM 增强** - 提升 LLM 利用代码知识的能力

---

## 📋 任务清单

### Task 2.1: 向量数据库集成 ✅

#### 2.1.1 技术选型

**决策**：使用 Chroma（轻量级，易集成，支持元数据过滤）

**理由**：
- ✅ 轻量级，易于集成
- ✅ 支持持久化存储
- ✅ 支持元数据过滤
- ✅ Python API 友好

#### 2.1.2 VectorStore 实现 ✅

**文件**: `ai_codegen/rag/vector_store.py`

**功能**：
- ✅ 初始化 Chroma 客户端
- ✅ 创建集合（collections）
- ✅ 向量化存储 CodeEntity
- ✅ 批量操作支持
- ✅ 查询和更新功能

---

### Task 2.2: 嵌入模型集成 ✅

#### 2.2.1 嵌入模型选择

**决策**：使用 sentence-transformers（本地，免费，快速）

**模型**：`all-MiniLM-L6-v2`（轻量级，80MB，384 维）

#### 2.2.2 Embedder 实现 ✅

**文件**: `ai_codegen/rag/embedder.py`

**功能**：
- ✅ 嵌入模型加载和管理
- ✅ 文本向量化
- ✅ 批量嵌入优化
- ✅ 延迟加载

---

### Task 2.3: 语义搜索实现 ✅

#### 2.3.1 SemanticSearcher 实现 ✅

**文件**: `ai_codegen/rag/semantic_searcher.py`

**功能**：
- ✅ 接口语义搜索
- ✅ 依赖关系搜索
- ✅ 混合搜索（关键词 + 语义）
- ✅ 相关性排序和过滤

**SearchResult**：
- ✅ 实体、分数、匹配类型、高亮

---

### Task 2.4: 上下文检索器 ✅

#### 2.4.1 ContextRetriever 实现 ✅

**文件**: `ai_codegen/rag/context_retriever.py`

**功能**：
- ✅ 任务意图理解
- ✅ 相关接口推荐
- ✅ 依赖关系检索
- ✅ 上下文组装和格式化

---

### Task 2.5: RAG 系统集成 ✅

#### 2.5.1 RAGManager 统一接口 ✅

**文件**: `ai_codegen/rag/rag_manager.py`

**功能**：
- ✅ 统一管理 RAG 系统
- ✅ 自动同步 SQLite 和 Vector DB
- ✅ 提供高级 API

---

### Task 2.6: MCP 工具集成 ⏳

#### 2.6.1 增强现有工具

**更新 `context` 工具**：
- [ ] 集成 RAG 检索
- [ ] 支持语义搜索
- [ ] 智能接口推荐

#### 2.6.2 新增工具

**`search_interfaces`** - 语义搜索接口
- [ ] 实现工具方法
- [ ] 添加到 MCP Server

**`retrieve_context`** - 智能上下文检索
- [ ] 实现工具方法
- [ ] 添加到 MCP Server

---

## 🏗️ 技术架构

### 组件关系

```
CodeEntity (from Phase 1)
  ↓
[Embedder] 向量化
  embedding_text → embedding vector (384 维)
  ↓
[VectorStore] 存储到 Chroma
  SQLite (结构化) + Chroma (向量)
  ↓
[SemanticSearcher] 语义搜索
  查询向量 → 相似度计算 → 排序
  ↓
[ContextRetriever] 上下文检索
  任务意图 → 相关接口 → 依赖扩展 → 格式化
  ↓
LLM 上下文生成
```

### 数据流

```
1. 实体提取 (Phase 1)
   CodeEntity
   ↓
2. 向量化
   embedding_text → embedding vector
   ↓
3. 存储
   SQLite (结构化) + Chroma (向量)
   ↓
4. 查询
   语义搜索 → 相关实体
   ↓
5. 上下文组装
   实体 + 依赖 + 格式化
   ↓
6. LLM 使用
   Prompt-ready 格式
```

---

## 📦 依赖项

### 新增依赖 ✅

```txt
# RAG 系统
chromadb>=0.4.22
sentence-transformers>=2.2.0
```

### 安装命令

```bash
pip install chromadb sentence-transformers
```

---

## 🧪 测试策略

### 单元测试

1. **VectorStore 测试**
   - [ ] 添加实体
   - [ ] 查询实体
   - [ ] 更新和删除
   - [ ] 批量操作

2. **Embedder 测试**
   - [ ] 单个文本嵌入
   - [ ] 批量嵌入
   - [ ] 向量维度验证

3. **SemanticSearcher 测试**
   - [ ] 语义搜索准确性
   - [ ] 过滤功能
   - [ ] 混合搜索

4. **ContextRetriever 测试**
   - [ ] 任务上下文检索
   - [ ] 接口上下文检索
   - [ ] 依赖关系扩展

### 集成测试

1. **端到端测试**
   - [ ] 提取 → 向量化 → 存储 → 搜索 → 检索

2. **性能测试**
   - [ ] 批量索引速度
   - [ ] 搜索延迟
   - [ ] 内存使用

3. **准确性测试**
   - [ ] 语义搜索相关性
   - [ ] 上下文完整性

---

## 📊 验收标准

### 功能标准

- [ ] 能够向量化存储 CodeEntity
- [ ] 能够语义搜索接口
- [ ] 能够基于任务检索上下文
- [ ] 搜索准确率 > 70% (Top-5)
- [ ] MCP 工具正常工作

### 性能标准

- [ ] 向量化速度: < 50ms/实体
- [ ] 搜索延迟: < 200ms
- [ ] 批量索引: 1000 实体 < 5 分钟
- [ ] 内存使用: < 500MB（1000 实体）

### 质量标准

- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试通过
- [ ] 文档完整

---

## 🚀 实施步骤

### Week 1: 基础架构 ✅

**Day 1-2: 向量数据库集成** ✅
- [x] 安装 Chroma
- [x] 实现 VectorStore 基础类
- [x] 测试基础功能

**Day 3-4: 嵌入模型集成** ✅
- [x] 安装 sentence-transformers
- [x] 实现 Embedder
- [x] 测试嵌入功能

**Day 5: 集成测试** ✅
- [x] VectorStore + Embedder 集成
- [x] 端到端测试

### Week 2: 搜索和检索 ✅

**Day 1-2: 语义搜索** ✅
- [x] 实现 SemanticSearcher
- [x] 实现搜索算法
- [x] 测试搜索准确性

**Day 3-4: 上下文检索** ✅
- [x] 实现 ContextRetriever
- [x] 实现意图理解
- [x] 实现上下文组装

**Day 5: 集成测试** ⏳
- [ ] 完整流程测试
- [ ] 性能测试

### Week 3: 集成和优化 ⏳

**Day 1-2: MCP 工具集成** ⏳
- [ ] 更新 context 工具
- [ ] 新增 search_interfaces 工具
- [ ] 新增 retrieve_context 工具

**Day 3-4: 优化和测试** ⏳
- [ ] 性能优化
- [ ] 批量操作优化
- [ ] 完整测试套件

**Day 5: 文档和交付** ⏳
- [ ] API 文档
- [ ] 使用示例
- [ ] 测试报告

---

## 📝 核心实现

### 1. VectorStore ✅

- 使用 Chroma 持久化存储
- 支持元数据过滤
- 批量操作优化

### 2. Embedder ✅

- sentence-transformers 集成
- 延迟加载模型
- 批量嵌入支持

### 3. SemanticSearcher ✅

- 向量相似度搜索
- 混合搜索（关键词 + 语义）
- 相关性评分

### 4. ContextRetriever ✅

- 任务意图理解
- 相关接口推荐
- 上下文格式化

### 5. RAGManager ✅

- 统一管理接口
- 自动同步
- 高级 API

---

## 🎯 下一步

### 立即开始

1. **MCP 工具集成** ⏳
   - 更新 context 工具
   - 新增 search_interfaces
   - 新增 retrieve_context

2. **测试和优化** ⏳
   - 完整测试套件
   - 性能优化
   - 准确性验证

3. **文档完善** ⏳
   - API 文档
   - 使用示例
   - 最佳实践

---

**版本**: V2.0 Phase 2  
**状态**: 核心实现完成，待集成和测试  
**完成度**: 80%  
**最后更新**: 2026-01-28
