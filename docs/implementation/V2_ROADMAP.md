# AI CodeGen MCP Server - V2 迭代计划

## 🎯 设计哲学

### 核心理念

**通过构建代码的依赖和调用关系，构建子模块的 interface，定义正确的输入输出规范，最终实现：**
1. **更好的分析改动依赖** - 理解代码变更的影响范围
2. **更好的生成代码** - 基于接口规范和依赖关系生成高质量代码

### 设计原则

1. **接口驱动开发** (Interface-Driven Development)
   - 从代码中自动提取接口定义
   - 定义清晰的输入输出规范（Contract）
   - 基于接口而非实现进行代码生成

2. **依赖感知编码** (Dependency-Aware Coding)
   - 理解模块间的调用关系
   - 分析改动的影响范围
   - 保持接口契约的一致性

3. **知识图谱增强** (Knowledge Graph Enhanced)
   - 构建完整的代码关系图
   - 支持语义搜索和推理
   - 提供上下文感知的编码建议

4. **专业编码辅助** (Professional Coding Assistant)
   - 不是简单地完成需求
   - 而是提供架构级别的编码指导
   - 关注代码质量、可维护性和扩展性

---

## 📊 当前状态分析

### ✅ 已有能力

1. **代码解析**
   - Tree-sitter 多语言解析
   - 符号提取（类、函数、变量）
   - 依赖关系提取（imports, calls, extends, instantiates）

2. **知识图谱**
   - SQLite 持久化存储
   - 节点和边的存储
   - 基础查询能力

3. **接口系统**
   - InterfaceSchema 定义
   - Contract 契约系统
   - InterfaceRegistry 注册表

4. **MCP 工具**
   - index, search, inspect, context, verify 等

### ❌ 缺失环节

1. **接口自动提取**
   - 无法从代码自动构建接口定义
   - 接口定义需要手动维护

2. **RAG 系统**
   - 依赖关系无法高效检索
   - 接口定义无法语义搜索
   - LLM 无法充分利用知识图谱

3. **专业编码指导**
   - 上下文生成不够智能
   - 缺乏架构级别的建议
   - 无法基于接口规范生成代码

---

## 🚀 V2 版本目标

### 核心目标

1. **自动接口提取与构建**
   - 从代码自动提取接口定义
   - 识别模块边界和接口契约
   - 自动维护接口注册表

2. **RAG 增强的知识检索**
   - 向量化存储接口和依赖关系
   - 语义搜索能力
   - 上下文相关的接口推荐

3. **专业编码辅助**
   - 基于接口规范的代码生成
   - 依赖影响分析
   - 架构级别的编码建议

---

## 📋 V2 迭代计划

### Phase 1: 接口自动提取 (2-3 周)

#### 1.1 接口提取器 (Interface Extractor)

**目标**：从代码自动提取接口定义

**任务**：
- [ ] 创建 `InterfaceExtractor` 类
- [ ] 从类定义提取公共方法签名
- [ ] 识别方法参数和返回类型
- [ ] 提取文档字符串作为接口描述
- [ ] 识别接口边界（输入/输出）

**技术实现**：
```python
class InterfaceExtractor:
    def extract_from_class(self, class_node, source_code) -> InterfaceSchema:
        """从类定义提取接口"""
        # 1. 提取公共方法
        # 2. 解析方法签名
        # 3. 提取类型注解
        # 4. 提取文档字符串
        # 5. 识别依赖关系
        pass
    
    def extract_from_module(self, module_path) -> List[InterfaceSchema]:
        """从模块提取所有接口"""
        pass
```

**输出**：
- 自动生成的接口定义（JSON）
- 接口注册表更新

#### 1.2 契约推断 (Contract Inference)

**目标**：从代码推断接口契约

**任务**：
- [ ] 分析参数验证逻辑（前置条件）
- [ ] 分析返回值约束（后置条件）
- [ ] 识别异常抛出（throws）
- [ ] 推断不变量（invariants）

**技术实现**：
```python
class ContractInferencer:
    def infer_preconditions(self, method_node) -> List[Precondition]:
        """从代码推断前置条件"""
        # 分析参数检查、类型验证等
        pass
    
    def infer_postconditions(self, method_node) -> List[Postcondition]:
        """从代码推断后置条件"""
        # 分析返回值类型、状态变化等
        pass
```

#### 1.3 模块边界识别 (Module Boundary Detection)

**目标**：识别模块的输入输出边界

**任务**：
- [ ] 分析模块的公共 API
- [ ] 识别外部依赖（输入）
- [ ] 识别对外暴露的接口（输出）
- [ ] 构建模块依赖图

**技术实现**：
```python
class ModuleBoundaryDetector:
    def detect_boundary(self, module_path) -> Dict:
        """识别模块边界"""
        return {
            "inputs": [...],  # 外部依赖
            "outputs": [...],  # 对外接口
            "side_effects": [...]  # 副作用
        }
```

#### 1.4 MCP 工具扩展

**新增工具**：
- `extract_interfaces` - 提取接口定义
- `get_interface` - 获取接口详情
- `list_interfaces` - 列出所有接口
- `validate_implementation` - 验证实现是否符合接口

---

### Phase 2: RAG 系统构建 (2-3 周)

#### 2.1 向量化存储 (Vector Store)

**目标**：将接口和依赖关系向量化存储

**任务**：
- [ ] 选择向量数据库（Chroma / FAISS / Qdrant）
- [ ] 设计向量化策略
- [ ] 实现接口向量化
- [ ] 实现依赖关系向量化

**技术选型**：
- **推荐**：Chroma（轻量级，易集成）
- **备选**：FAISS（高性能），Qdrant（云原生）

**向量化内容**：
1. **接口定义**
   - 接口名称和描述
   - 方法签名和文档
   - 契约规范

2. **依赖关系**
   - 调用关系上下文
   - 模块依赖描述
   - 代码片段

**实现**：
```python
class VectorStore:
    def __init__(self):
        self.client = ChromaClient()
        self.interface_collection = "interfaces"
        self.dependency_collection = "dependencies"
    
    def embed_interface(self, interface: InterfaceSchema):
        """向量化接口定义"""
        text = self._format_interface_text(interface)
        embedding = self.embedder.embed(text)
        self.client.add(
            collection=self.interface_collection,
            embeddings=[embedding],
            documents=[text],
            metadatas=[interface.to_dict()]
        )
    
    def embed_dependency(self, relationship: Relationship):
        """向量化依赖关系"""
        text = self._format_dependency_text(relationship)
        embedding = self.embedder.embed(text)
        self.client.add(...)
```

#### 2.2 语义搜索 (Semantic Search)

**目标**：基于语义搜索接口和依赖

**任务**：
- [ ] 实现接口语义搜索
- [ ] 实现依赖关系搜索
- [ ] 支持混合搜索（关键词 + 语义）
- [ ] 相关性排序

**实现**：
```python
class SemanticSearcher:
    def search_interfaces(
        self,
        query: str,
        limit: int = 10
    ) -> List[InterfaceSchema]:
        """语义搜索接口"""
        query_embedding = self.embedder.embed(query)
        results = self.vector_store.query(
            collection="interfaces",
            query_embeddings=[query_embedding],
            n_results=limit
        )
        return self._parse_results(results)
    
    def search_dependencies(
        self,
        query: str,
        source: Optional[str] = None
    ) -> List[Relationship]:
        """语义搜索依赖关系"""
        pass
```

#### 2.3 上下文检索 (Context Retrieval)

**目标**：基于任务检索相关接口和依赖

**任务**：
- [ ] 任务意图理解
- [ ] 相关接口推荐
- [ ] 依赖关系检索
- [ ] 上下文组装

**实现**：
```python
class ContextRetriever:
    def retrieve_for_task(
        self,
        task_description: str,
        max_interfaces: int = 5,
        max_dependencies: int = 10
    ) -> Dict:
        """为任务检索上下文"""
        # 1. 理解任务意图
        intent = self._understand_intent(task_description)
        
        # 2. 搜索相关接口
        interfaces = self.searcher.search_interfaces(
            query=intent,
            limit=max_interfaces
        )
        
        # 3. 检索依赖关系
        dependencies = self._get_related_dependencies(interfaces)
        
        # 4. 组装上下文
        return {
            "interfaces": interfaces,
            "dependencies": dependencies,
            "suggestions": self._generate_suggestions(interfaces)
        }
```

#### 2.4 嵌入模型集成

**任务**：
- [ ] 选择嵌入模型（OpenAI / Sentence-BERT / 本地模型）
- [ ] 实现嵌入接口
- [ ] 批量嵌入优化
- [ ] 缓存策略

**推荐方案**：
- **开发阶段**：sentence-transformers (本地，免费)
- **生产阶段**：OpenAI text-embedding-3-small (高质量)

---

### Phase 3: 专业编码辅助 (2-3 周)

#### 3.1 接口驱动的代码生成

**目标**：基于接口规范生成代码

**任务**：
- [ ] 接口规范格式化（Prompt 模板）
- [ ] 代码生成建议
- [ ] 接口实现检查
- [ ] 契约验证提示

**实现**：
```python
class InterfaceDrivenGenerator:
    def generate_implementation_prompt(
        self,
        interface: InterfaceSchema,
        context: Dict
    ) -> str:
        """生成实现代码的 Prompt"""
        return f"""
# 实现接口: {interface.name}

## 接口定义
{interface.description}

## 方法规范
{self._format_methods(interface.methods)}

## 契约要求
{self._format_contracts(interface)}

## 依赖关系
{self._format_dependencies(context)}

## 实现要求
1. 遵循接口定义的方法签名
2. 满足所有契约条件
3. 保持与依赖模块的兼容性
4. 添加适当的错误处理
"""
```

#### 3.2 依赖影响分析

**目标**：分析代码变更的影响范围

**任务**：
- [ ] 接口变更影响分析
- [ ] 依赖传播分析
- [ ] 破坏性变更检测
- [ ] 影响范围可视化

**实现**：
```python
class ImpactAnalyzer:
    def analyze_interface_change(
        self,
        interface_name: str,
        changes: Dict
    ) -> ImpactReport:
        """分析接口变更的影响"""
        # 1. 查找所有实现
        implementations = self.registry.find_implementations(interface_name)
        
        # 2. 查找所有调用点
        callers = self.graph.find_callers(interface_name)
        
        # 3. 分析影响范围
        return ImpactReport(
            affected_implementations=implementations,
            affected_callers=callers,
            breaking_changes=self._detect_breaking_changes(changes),
            migration_suggestions=self._generate_migration_suggestions(changes)
        )
```

#### 3.3 架构级别建议

**目标**：提供架构级别的编码建议

**任务**：
- [ ] 模块设计建议
- [ ] 接口设计模式推荐
- [ ] 依赖关系优化建议
- [ ] 代码质量评估

**实现**：
```python
class ArchitectureAdvisor:
    def suggest_module_design(
        self,
        module_path: str,
        requirements: List[str]
    ) -> DesignSuggestion:
        """提供模块设计建议"""
        # 分析现有模块结构
        # 推荐接口设计
        # 建议依赖关系
        pass
    
    def assess_code_quality(
        self,
        code_path: str
    ) -> QualityReport:
        """评估代码质量"""
        # 接口完整性
        # 契约覆盖率
        # 依赖合理性
        pass
```

#### 3.4 增强的 Context 工具

**改进 `context` 工具**：
- 基于 RAG 的智能检索
- 接口规范优先
- 依赖关系可视化
- 编码建议生成

**新参数**：
```json
{
  "task_id": "task_001",
  "mode": "interface_driven",  // interface_driven / dependency_aware / full
  "include_suggestions": true,
  "max_interfaces": 5,
  "max_dependencies": 10
}
```

---

### Phase 4: 系统集成与优化 (1-2 周)

#### 4.1 MCP 工具更新

**新增工具**：
- `extract_interfaces` - 提取接口
- `search_interfaces` - 语义搜索接口
- `analyze_impact` - 影响分析
- `suggest_design` - 设计建议

**增强工具**：
- `context` - 集成 RAG 检索
- `search` - 支持语义搜索
- `inspect` - 显示接口定义

#### 4.2 持久化扩展

**新增表**：
- `interfaces` - 接口定义
- `interface_embeddings` - 接口向量
- `dependency_embeddings` - 依赖向量
- `impact_cache` - 影响分析缓存

#### 4.3 性能优化

**任务**：
- [ ] 向量化批量处理
- [ ] 嵌入缓存
- [ ] 增量更新接口
- [ ] 查询性能优化

#### 4.4 文档更新

**任务**：
- [ ] 更新 README
- [ ] 接口提取使用指南
- [ ] RAG 系统文档
- [ ] 编码辅助最佳实践

---

## 🏗️ 技术架构

### V2 架构图

```
┌─────────────────────────────────────────────────────────┐
│              Cursor / Claude (MCP Client)                │
│        专业编码辅助：基于接口和依赖的代码生成              │
└─────────────────────────────────────────────────────────┘
                           │
                           │ MCP Protocol
                           ▼
┌─────────────────────────────────────────────────────────┐
│            AI CodeGen MCP Server V2                     │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 增强的 MCP 工具                                    │ │
│  │ • extract_interfaces - 接口提取                    │ │
│  │ • search_interfaces - 语义搜索接口                 │ │
│  │ • context (增强) - RAG 驱动的上下文生成            │ │
│  │ • analyze_impact - 依赖影响分析                   │ │
│  │ • suggest_design - 架构建议                        │ │
│  └───────────────────────────────────────────────────┘ │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐ │
│  │  接口自动提取层                                     │ │
│  │  • InterfaceExtractor - 从代码提取接口             │ │
│  │  • ContractInferencer - 推断契约                   │ │
│  │  • ModuleBoundaryDetector - 识别模块边界           │ │
│  └───────────────────────────────────────────────────┘ │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐ │
│  │  RAG 系统                                           │ │
│  │  • VectorStore - 向量化存储                         │ │
│  │  • SemanticSearcher - 语义搜索                      │ │
│  │  • ContextRetriever - 上下文检索                    │ │
│  │  • Embedder - 嵌入模型集成                          │ │
│  └───────────────────────────────────────────────────┘ │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐ │
│  │  专业编码辅助层                                      │ │
│  │  • InterfaceDrivenGenerator - 接口驱动生成          │ │
│  │  • ImpactAnalyzer - 影响分析                        │ │
│  │  • ArchitectureAdvisor - 架构建议                   │ │
│  └───────────────────────────────────────────────────┘ │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐ │
│  │  持久化存储                                          │ │
│  │  • SQLite - 结构化数据                              │ │
│  │  • Vector DB - 向量数据                             │ │
│  │  • 接口注册表                                        │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 依赖项

### 新增依赖

```txt
# RAG 系统
chromadb>=0.4.0  # 向量数据库
sentence-transformers>=2.2.0  # 嵌入模型（可选）
# 或
openai>=1.0.0  # OpenAI 嵌入（可选）

# 接口提取增强
ast-comments>=0.1.0  # AST 注释解析（可选）
```

---

## 🎯 成功指标

### 功能指标

1. **接口提取覆盖率**
   - 目标：自动提取 80%+ 的公共接口
   - 测量：接口数量 / 代码中的类数量

2. **RAG 检索准确率**
   - 目标：Top-5 准确率 > 70%
   - 测量：相关接口在检索结果中的排名

3. **代码生成质量**
   - 目标：基于接口生成的代码通过验证率 > 80%
   - 测量：生成的代码通过语法/类型检查的比例

### 性能指标

1. **接口提取速度**
   - 目标：< 100ms/文件
   - 测量：提取接口的平均时间

2. **RAG 检索延迟**
   - 目标：< 200ms/查询
   - 测量：语义搜索的平均响应时间

3. **上下文生成速度**
   - 目标：< 500ms（包含 RAG 检索）
   - 测量：完整上下文生成的平均时间

---

## 📅 时间线

| Phase | 时间 | 里程碑 |
|-------|------|--------|
| Phase 1 | Week 1-3 | 接口自动提取完成 |
| Phase 2 | Week 4-6 | RAG 系统构建完成 |
| Phase 3 | Week 7-9 | 专业编码辅助完成 |
| Phase 4 | Week 10-11 | 系统集成与优化 |
| **总计** | **11 周** | **V2 版本发布** |

---

## 🔄 迭代策略

### 增量开发

1. **每个 Phase 独立可交付**
   - Phase 1 完成后即可使用接口提取
   - Phase 2 完成后即可使用 RAG 搜索
   - Phase 3 完成后即可使用编码辅助

2. **持续集成**
   - 每个 Phase 完成后进行集成测试
   - 确保向后兼容
   - 及时修复问题

3. **用户反馈**
   - 每个 Phase 完成后收集反馈
   - 根据反馈调整后续 Phase
   - 优先实现高价值功能

---

## 📝 下一步行动

### 立即开始

1. **创建 Phase 1 任务清单**
   - [ ] 设计 InterfaceExtractor API
   - [ ] 实现基础接口提取
   - [ ] 编写单元测试

2. **技术调研**
   - [ ] 评估向量数据库选项
   - [ ] 选择嵌入模型
   - [ ] 设计向量化策略

3. **文档准备**
   - [ ] 更新设计文档
   - [ ] 创建开发指南
   - [ ] 准备示例代码

---

**版本**: V2.0  
**状态**: 规划中  
**最后更新**: 2026-01-28
