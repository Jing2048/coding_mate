# AI CodeGen MCP Server - 系统能力总结

## 📋 目录

- [核心架构](#核心架构)
- [MCP 工具能力](#mcp-工具能力)
- [代码分析能力](#代码分析能力)
- [关系提取能力](#关系提取能力)
- [搜索能力](#搜索能力)
- [上下文生成能力](#上下文生成能力)
- [PRD 生命周期管理](#prd-生命周期管理)
- [任务管理能力](#任务管理能力)
- [代码验证能力](#代码验证能力)
- [持久化存储](#持久化存储)
- [支持的语言](#支持的语言)

---

## 核心架构

```
┌─────────────────────────────────────────────────────────┐
│              Cursor / Claude (MCP Client)               │
│           负责编码工作，调用 MCP 工具获取知识             │
└─────────────────────────────────────────────────────────┘
                           │
                           │ MCP Protocol
                           ▼
┌─────────────────────────────────────────────────────────┐
│            AI CodeGen MCP Server                        │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 7 个核心工具                                        │ │
│  │ • index   - 代码库索引                             │ │
│  │ • search  - 智能搜索                               │ │
│  │ • inspect - 详情查看                               │ │
│  │ • prd     - PRD 管理                               │ │
│  │ • task    - 任务管理                               │ │
│  │ • verify  - 代码验证                               │ │
│  │ • context - 上下文生成                             │ │
│  └───────────────────────────────────────────────────┘ │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐ │
│  │  Tree-sitter 解析器                                │ │
│  │  • Python / JS / TS / Swift / Go                  │ │
│  │  • AST 遍历                                        │ │
│  │  • 符号提取                                        │ │
│  └───────────────────────────────────────────────────┘ │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐ │
│  │  关系提取器 (RelationshipExtractor)                │ │
│  │  • 调用关系 (calls)                                │ │
│  │  • 继承关系 (extends)                              │ │
│  │  • 实例化 (instantiates)                          │ │
│  │  • 导入关系 (imports)                             │ │
│  │  • 装饰器 (decorates)                              │ │
│  └───────────────────────────────────────────────────┘ │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐ │
│  │  SQLite 持久化存储                                 │ │
│  │  • 解析结果缓存                                    │ │
│  │  • 知识图谱（节点+边）                             │ │
│  │  • PRD 文档                                        │ │
│  │  • 任务追踪                                        │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**核心理念**：
- ✅ MCP Server 提供**代码分析、知识管理、验证**能力
- ✅ MCP Client (Cursor/Claude) 负责**实际编码工作**
- ✅ 通过 MCP Protocol 实现**职责分离**和**能力复用**

---

## MCP 工具能力

### 1. `index` - 代码库索引

**功能**：构建代码知识图谱，支持增量索引

**能力**：
- ✅ 多路径、多扩展名索引
- ✅ 基于内容哈希的增量更新
- ✅ 自动语言检测
- ✅ 符号提取（类/函数/变量）
- ✅ 依赖关系提取
- ✅ 调用关系提取
- ✅ 错误处理和报告

**输出**：
```json
{
  "indexed": 42,
  "symbols": 156,
  "total_files": 42,
  "total_nodes": 198,
  "total_edges": 1234,
  "errors": []
}
```

---

### 2. `search` - 智能代码搜索

**功能**：多维度代码搜索，支持模糊匹配

**搜索类型**：
- `symbol` - 符号搜索（类/函数/变量）
- `file` - 文件搜索
- `content` - 内容搜索
- `dependency` - 依赖关系搜索

**搜索特性**：
- ✅ 大小写不敏感
- ✅ 命名规范归一化（`UserService` ↔ `user_service`）
- ✅ 相关性评分
- ✅ 多级匹配（精确 → 归一化 → 子串 → 单词）

**示例**：
```json
{
  "query": "userService",
  "type": "symbol",
  "limit": 20
}
```

---

### 3. `inspect` - 代码详情查看

**功能**：获取文件或符号的完整信息

**能力**：
- ✅ 源码查看（可指定行范围）
- ✅ 符号信息（类型、位置、文档）
- ✅ 依赖关系（导入、调用）
- ✅ 文件统计信息

**示例**：
```json
{
  "target": "src/services/user.py:UserService",
  "include_source": true,
  "include_deps": true
}
```

---

### 4. `prd` - PRD 生命周期管理

**功能**：管理产品需求文档的完整生命周期

**操作**：
- `create` - 创建 PRD
- `analyze` - 分析 PRD，识别影响的代码
- `list` - 列出所有 PRD
- `get` - 获取 PRD 详情
- `update` - 更新 PRD 状态

**状态流转**：
```
draft → analyzing → planned → in_progress → completed → archived
```

**能力**：
- ✅ PRD 内容存储
- ✅ 自动代码影响分析
- ✅ 状态追踪
- ✅ 时间戳记录

---

### 5. `task` - 任务管理

**功能**：从 PRD 创建和管理实现任务

**操作**：
- `plan` - 从 PRD 自动创建任务
- `create` - 手动创建任务
- `list` - 列出任务
- `get` - 获取任务详情
- `update` - 更新任务状态

**状态**：
- `pending` - 待处理
- `in_progress` - 进行中
- `completed` - 已完成
- `blocked` - 阻塞
- `cancelled` - 已取消

**能力**：
- ✅ 任务与 PRD 关联
- ✅ 状态追踪
- ✅ 描述和元数据存储

---

### 6. `verify` - 代码验证

**功能**：验证代码的语法、类型和测试

**检查类型**：
- `syntax` - 语法检查（Python AST）
- `type` - 类型检查（MyPy）
- `test` - 测试运行（Pytest）

**能力**：
- ✅ 多检查类型组合
- ✅ 详细错误报告
- ✅ 行号定位
- ✅ 错误消息格式化

**示例**：
```json
{
  "file": "src/services/user.py",
  "checks": ["syntax", "type", "test"]
}
```

---

### 7. `context` - 智能上下文生成

**功能**：为编码任务生成智能上下文

**能力**：
- ✅ 基于任务的上下文收集
- ✅ 文件级上下文（源码+符号）
- ✅ 依赖图遍历（BFS，可配置深度）
- ✅ Token 预算管理
- ✅ 结构化输出（JSON）
- ✅ Prompt 就绪格式（Markdown）
- ✅ 符号级上下文（函数/类）

**参数**：
- `task_id` - 任务 ID（可选）
- `files` - 文件列表（可选）
- `symbols` - 符号列表（可选）
- `max_tokens` - Token 预算（默认 8000）
- `format` - 输出格式（`structured` / `prompt`）
- `depth` - 依赖遍历深度（默认 1）

**示例输出**：
```markdown
# Context for task: feat_auth_task_1

## Files
### src/models/user.py
```python
class User:
    ...
```

## Dependencies
### src/services/auth.py
- `authenticate()` - 用户认证
- `validate_token()` - Token 验证
```

---

## 代码分析能力

### Tree-sitter 解析器

**支持的语言**：
- ✅ Python (`tree-sitter-python`)
- ✅ JavaScript (`tree-sitter-javascript`)
- ✅ TypeScript/TSX (`tree-sitter-typescript`)
- ✅ Swift (`tree-sitter-swift`)
- ✅ Go (`tree-sitter-go`)
- ✅ 其他语言（正则表达式后备）

**提取的符号**：
- 类定义（`class`）
- 函数定义（`function`）
- 方法定义（`method`）
- 变量定义（`variable`）
- 导入语句（`import`）

**符号信息**：
- 名称
- 类型
- 位置（文件、行号）
- 文档字符串
- 参数列表

---

## 关系提取能力

### 已实现的关系类型

| 关系类型 | 说明 | 状态 |
|---------|------|------|
| `IMPORTS` | 模块导入关系 | ✅ |
| `CALLS` | 函数/方法调用关系 | ✅ |
| `EXTENDS` | 类继承关系 | ✅ |
| `INSTANTIATES` | 对象实例化关系 | ✅ |
| `DECORATES` | 装饰器关系 | ✅ |

### 已定义但未实现

| 关系类型 | 说明 | 状态 |
|---------|------|------|
| `IMPLEMENTS` | 接口实现关系 | ⏳ |
| `REFERENCES` | 类型引用关系 | ⏳ |
| `ACCESSES` | 属性访问关系 | ⏳ |

### 关系提取技术

**方法 1：Tree-sitter AST 遍历**（优先）
- 高精度
- 语言特定优化
- 支持复杂语法结构

**方法 2：正则表达式匹配**（后备）
- 兼容性保证
- 适用于未支持的语言
- 基础关系提取

### 关系数据示例

```
【调用关系】
  UserService.get_user → db.query
  UserService.get_user → User.from_dict

【继承关系】
  UserService → BaseService
  AdminUser → User

【实例化关系】
  UserService.create_user → DataValidator
  AuthService.login → TokenManager
```

---

## 搜索能力

### 搜索维度

1. **符号搜索** (`type: "symbol"`)
   - 类名、函数名、变量名
   - 模糊匹配
   - 命名规范归一化

2. **文件搜索** (`type: "file"`)
   - 文件名匹配
   - 路径搜索

3. **内容搜索** (`type: "content"`)
   - 源代码内容搜索
   - 全文检索

4. **依赖搜索** (`type: "dependency"`)
   - 查找依赖某个模块的文件
   - 查找被某个文件依赖的模块

### 匹配算法

**多级匹配策略**：
1. **精确匹配** - 完全匹配（score: 1.0）
2. **归一化匹配** - 命名规范归一化后匹配（score: 0.8）
3. **子串匹配** - 包含子串（score: 0.6）
4. **单词匹配** - 单词级别匹配（score: 0.4）

**命名规范归一化**：
- `UserService` → `user_service`
- `user_service` → `userservice`
- 移除多余下划线

---

## 上下文生成能力

### 上下文收集策略

1. **任务级上下文**
   - 从任务描述提取关键词
   - 搜索相关文件和符号
   - 收集依赖关系

2. **文件级上下文**
   - 完整源码
   - 符号列表
   - 导入关系

3. **依赖级上下文**
   - BFS 遍历依赖图
   - 可配置深度（`depth` 参数）
   - 只收集公共 API（符号名+文档）

4. **符号级上下文**
   - 符号完整定义
   - 调用关系
   - 依赖的符号

### Token 预算管理

- 默认预算：8000 tokens
- 动态分配：
  - 文件源码：40%
  - 依赖关系：40%
  - 符号详情：20%
- 自动截断：超出预算时保留关键部分

### 输出格式

**结构化格式** (`format: "structured"`)：
```json
{
  "files": [...],
  "dependencies": [...],
  "symbols": [...],
  "metadata": {...}
}
```

**Prompt 格式** (`format: "prompt"`)：
```markdown
# Context for task: ...

## Files
...

## Dependencies
...
```

---

## PRD 生命周期管理

### PRD 状态

```
draft → analyzing → planned → in_progress → completed → archived
```

### PRD 操作

1. **创建 PRD**
   ```json
   {
     "action": "create",
     "prd_id": "feat_auth",
     "title": "用户认证功能",
     "content": "..."
   }
   ```

2. **分析 PRD**
   - 自动识别影响的代码文件
   - 提取关键词
   - 搜索相关符号

3. **更新状态**
   - 追踪开发进度
   - 记录时间戳

---

## 任务管理能力

### 任务创建

**自动创建**（从 PRD）：
```json
{
  "action": "plan",
  "prd_id": "feat_auth"
}
```

**手动创建**：
```json
{
  "action": "create",
  "task_id": "task_001",
  "prd_id": "feat_auth",
  "title": "实现登录接口",
  "description": "..."
}
```

### 任务状态

- `pending` - 待处理
- `in_progress` - 进行中
- `completed` - 已完成
- `blocked` - 阻塞
- `cancelled` - 已取消

### 任务查询

- 按 PRD 查询：`task(action="list", prd_id="feat_auth")`
- 查询所有：`task(action="list")`
- 获取详情：`task(action="get", task_id="task_001")`

---

## 代码验证能力

### 验证类型

1. **语法检查** (`syntax`)
   - Python AST 解析
   - 语法错误检测
   - 行号定位

2. **类型检查** (`type`)
   - MyPy 集成
   - 类型错误报告
   - 类型注解验证

3. **测试运行** (`test`)
   - Pytest 集成
   - 测试结果报告
   - 覆盖率统计（可选）

### 验证输出

```json
{
  "passed": false,
  "checks": {
    "syntax": {"passed": true},
    "type": {
      "passed": false,
      "errors": [
        {
          "file": "src/user.py",
          "line": 42,
          "message": "Incompatible types..."
        }
      ]
    }
  }
}
```

---

## 持久化存储

### SQLite 数据库结构

**表结构**：
1. `parse_results` - 解析结果缓存
2. `graph_nodes` - 知识图谱节点
3. `graph_edges` - 知识图谱边
4. `prds` - PRD 文档
5. `tasks` - 任务追踪

### 存储特性

- ✅ 基于内容哈希的增量更新
- ✅ 关系去重（UNIQUE 约束）
- ✅ 索引优化（文件路径、符号名）
- ✅ 数据完整性（外键约束）

### 数据统计

```python
{
  "parsed_files": 42,
  "graph_nodes": 198,
  "graph_edges": 1234,
  "prds": 5,
  "tasks": 12
}
```

---

## 支持的语言

### 完整支持（Tree-sitter）

| 语言 | 包 | 符号提取 | 关系提取 | 状态 |
|------|-----|---------|---------|------|
| Python | `tree-sitter-python` | ✅ | ✅ | ✅ |
| JavaScript | `tree-sitter-javascript` | ✅ | ✅ | ✅ |
| TypeScript | `tree-sitter-typescript` | ✅ | ✅ | ✅ |
| TSX | `tree-sitter-typescript` | ✅ | ✅ | ✅ |
| Swift | `tree-sitter-swift` | ✅ | ✅ | ✅ |
| Go | `tree-sitter-go` | ✅ | ✅ | ✅ |

### 基础支持（正则表达式）

- Ruby
- Java
- C/C++
- 其他语言

---

## 典型工作流

### 1. 新需求开发

```
1. 索引代码库
   index(paths=["src"])

2. 创建 PRD
   prd(action="create", prd_id="feat_auth", ...)

3. 分析 PRD
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

4. 获取上下文
   context(symbols=["AuthService"], depth=2)
```

### 3. 重构支持

```
1. 查找所有调用点
   search(query="oldMethod", type="dependency")

2. 分析影响范围
   inspect(target="src/old.py:oldMethod", include_deps=true)

3. 获取重构上下文
   context(files=["src/old.py", "src/new.py"], depth=1)
```

---

## 性能指标

### 索引性能

- 单文件解析：~50-200ms（取决于文件大小）
- 1000 文件索引：~2-5 分钟
- 增量更新：仅解析变更文件

### 搜索性能

- 符号搜索：<100ms（1000+ 符号）
- 依赖搜索：<200ms
- 上下文生成：<500ms（深度 2）

### 存储大小

- 1000 文件：~10-50MB（SQLite）
- 关系边：~100-500KB/1000 文件

---

## 扩展性

### 添加新语言

1. 安装对应的 `tree-sitter-{language}` 包
2. 在 `RelationshipExtractor._init_tree_sitter()` 中添加语言
3. 在 `_extract_with_tree_sitter()` 中添加语言特定的 AST 遍历逻辑

### 添加新关系类型

1. 在 `RelationType` 枚举中添加新类型
2. 在 `RelationshipExtractor` 中实现提取逻辑
3. 更新 `server.py` 中的关系存储逻辑

---

## 总结

**核心优势**：
- ✅ **职责分离**：MCP Server 专注知识管理，Client 专注编码
- ✅ **多语言支持**：5+ 语言完整支持，其他语言基础支持
- ✅ **智能关系提取**：调用、继承、实例化等 5 种关系类型
- ✅ **持久化存储**：SQLite 数据库，增量更新
- ✅ **智能上下文**：Token 预算管理，依赖图遍历
- ✅ **完整工作流**：PRD → 任务 → 编码 → 验证

**适用场景**：
- 大型代码库的理解和维护
- 新功能开发的上下文准备
- 代码重构的影响分析
- 团队协作的需求管理
- AI 辅助编码的上下文提供
