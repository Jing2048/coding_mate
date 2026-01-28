# MCP 工具总览

## 📋 工具列表

MCP 服务器共提供 **11 个工具**，分为两类：

### V2 新工具 (6个) ✅

| 工具 | 功能 | 状态 |
|------|------|------|
| `extract_interfaces` | 从代码提取接口定义 | ✅ |
| `get_interface` | 获取接口详情 | ✅ |
| `list_interfaces` | 列出所有接口 | ✅ |
| `search_interfaces` | 语义搜索接口 | ✅ |
| `sync_rag` | 同步数据到向量数据库 | ✅ |
| `context` (增强) | 获取上下文（支持 RAG） | ✅ |

### V1 工具 (5个) ✅

| 工具 | 功能 | 状态 |
|------|------|------|
| `index` | 索引代码库，构建知识图谱 | ✅ |
| `search` | 搜索代码（符号/文件/内容/依赖） | ✅ |
| `inspect` | 查看文件或符号的详细信息 | ✅ |
| `prd` | PRD 生命周期管理 | ✅ |
| `task` | 任务管理 | ✅ |
| `verify` | 代码验证（语法/类型/测试） | ✅ |

---

## 🔧 工具详情

### V2 新工具

#### 1. extract_interfaces

**功能**: 从代码文件自动提取接口定义

**参数**:
- `paths` (List[str]): 文件路径列表
- `force` (bool): 是否强制重新提取

**返回**: 提取统计信息

---

#### 2. get_interface

**功能**: 获取接口的详细信息

**参数**:
- `interface_id` (str): 接口 ID
- `include_contracts` (bool): 是否包含契约
- `include_dependencies` (bool): 是否包含依赖

**返回**: 接口详情（签名、契约、依赖、LLM 格式）

---

#### 3. list_interfaces

**功能**: 列出所有接口，支持过滤

**参数**:
- `module` (str, 可选): 模块过滤
- `entity_type` (str, 可选): 类型过滤
- `domain` (str, 可选): 领域过滤
- `limit` (int, 可选): 数量限制

**返回**: 接口列表

---

#### 4. search_interfaces

**功能**: 语义搜索接口（需要 RAG 依赖）

**参数**:
- `query` (str): 搜索查询
- `entity_type` (str, 可选): 类型过滤
- `domain` (str, 可选): 领域过滤
- `limit` (int, 可选): 数量限制
- `use_hybrid` (bool, 可选): 混合搜索

**返回**: 搜索结果（带相似度分数）

**注意**: 如果 RAG 不可用，会降级到 SQLite 搜索

---

#### 5. sync_rag

**功能**: 同步 SQLite 数据到向量数据库

**参数**:
- `force` (bool, 可选): 是否强制重新同步

**返回**: 同步结果和统计信息

---

#### 6. context (增强)

**功能**: 获取实现任务的上下文

**参数**:
- `task_id` (str, 可选): 任务 ID
- `files` (List[str], 可选): 文件列表
- `symbols` (List[str], 可选): 符号列表
- `max_tokens` (int, 可选): 最大 token 数
- `format` (str, 可选): 输出格式（structured/prompt）
- `depth` (int, 可选): 依赖遍历深度
- `mode` (str, 可选): 模式（dependency/rag/full）

**返回**: 上下文信息（支持 prompt-ready 格式）

---

### V1 工具

#### 7. index

**功能**: 索引代码库，构建知识图谱

**参数**:
- `paths` (List[str]): 要索引的路径
- `extensions` (List[str], 可选): 文件扩展名过滤
- `force` (bool, 可选): 是否强制重新索引

**返回**: 索引统计信息

---

#### 8. search

**功能**: 搜索代码

**参数**:
- `query` (str): 搜索查询
- `type` (str, 可选): 搜索类型（symbol/file/content/dependency）
- `limit` (int, 可选): 数量限制

**返回**: 搜索结果列表

---

#### 9. inspect

**功能**: 查看文件或符号的详细信息

**参数**:
- `target` (str): 目标（文件路径或符号）
- `include_source` (bool, 可选): 是否包含源码
- `include_deps` (bool, 可选): 是否包含依赖

**返回**: 详细信息

---

#### 10. prd

**功能**: PRD 生命周期管理

**参数**:
- `action` (str): 操作（create/analyze/list/get/update）
- `prd_id` (str, 可选): PRD ID
- `title` (str, 可选): 标题
- `content` (str, 可选): 内容
- `status` (str, 可选): 状态

**返回**: 操作结果

---

#### 11. task

**功能**: 任务管理

**参数**:
- `action` (str): 操作（create/plan/list/get/update）
- `task_id` (str, 可选): 任务 ID
- `prd_id` (str, 可选): PRD ID
- `title` (str, 可选): 标题
- `description` (str, 可选): 描述
- `status` (str, 可选): 状态

**返回**: 操作结果

---

#### 12. verify

**功能**: 代码验证

**参数**:
- `file` (str): 文件路径
- `checks` (List[str], 可选): 检查类型（syntax/type/test）

**返回**: 验证结果

---

## 📊 工具分类

### 按功能分类

**代码分析**:
- `index` - 索引代码库
- `search` - 搜索代码
- `inspect` - 查看详情
- `extract_interfaces` - 提取接口
- `get_interface` - 获取接口详情
- `list_interfaces` - 列出接口
- `search_interfaces` - 语义搜索接口

**上下文和检索**:
- `context` - 获取上下文
- `sync_rag` - 同步 RAG 数据

**项目管理**:
- `prd` - PRD 管理
- `task` - 任务管理

**代码验证**:
- `verify` - 代码验证

---

## 🚀 使用建议

### 典型工作流

1. **索引代码库**
   ```
   index(paths=["src/"])
   ```

2. **提取接口**
   ```
   extract_interfaces(paths=["src/"])
   ```

3. **同步到 RAG**
   ```
   sync_rag(force=True)
   ```

4. **搜索相关接口**
   ```
   search_interfaces(query="用户认证")
   ```

5. **获取上下文**
   ```
   context(mode="rag", max_tokens=4000)
   ```

6. **验证代码**
   ```
   verify(file="src/service.py", checks=["syntax", "type"])
   ```

---

**版本**: V2.0  
**工具总数**: 12 个  
**最后更新**: 2026-01-28
