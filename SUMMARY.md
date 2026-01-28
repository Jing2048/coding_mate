# AI CodeGen MCP Server - 能力总结

## 🎯 核心定位

**MCP Server 提供代码分析、知识管理、验证能力**  
**MCP Client (Cursor/Claude) 负责实际编码工作**

---

## 📦 7 个核心 MCP 工具

| 工具 | 功能 | 关键能力 |
|------|------|---------|
| `index` | 代码库索引 | 构建知识图谱，增量更新，多语言支持 |
| `search` | 智能搜索 | 符号/文件/依赖搜索，模糊匹配，命名归一化 |
| `inspect` | 详情查看 | 源码、符号、依赖关系查看 |
| `prd` | PRD 管理 | 需求文档生命周期管理，代码影响分析 |
| `task` | 任务管理 | 任务规划与追踪，状态管理 |
| `verify` | 代码验证 | 语法/类型/测试检查 |
| `context` | 上下文生成 | Token 预算，依赖图遍历，Prompt 就绪 |

---

## 🌐 支持的语言

### 完整支持（Tree-sitter）
- ✅ **Python** - tree-sitter-python
- ✅ **JavaScript** - tree-sitter-javascript  
- ✅ **TypeScript/TSX** - tree-sitter-typescript
- ✅ **Swift** - tree-sitter-swift ⭐ 新增
- ✅ **Go** - tree-sitter-go

### 基础支持（正则表达式）
- Ruby, Java, C/C++, 其他语言

---

## 🔗 代码关系提取

### 已实现（5种）
- ✅ **IMPORTS** - 模块导入关系
- ✅ **CALLS** - 函数/方法调用关系 ⭐ 核心能力
- ✅ **EXTENDS** - 类继承关系
- ✅ **INSTANTIATES** - 对象实例化关系 ⭐ 核心能力
- ✅ **DECORATES** - 装饰器关系

### 已定义（3种）
- ⏳ IMPLEMENTS - 接口实现
- ⏳ REFERENCES - 类型引用
- ⏳ ACCESSES - 属性访问

**技术实现**：
- Tree-sitter AST 遍历（优先，高精度）
- 正则表达式匹配（后备，兼容性）

---

## 💡 核心能力亮点

### 1. 智能上下文生成
```
context(task_id="task_001", max_tokens=8000, depth=2)
```
- 基于任务的上下文收集
- BFS 依赖图遍历（可配置深度）
- Token 预算管理（自动分配）
- 两种输出格式（JSON / Markdown）

### 2. 完整调用关系图
```
【调用关系】
  UserService.get_user → db.query
  UserService.get_user → User.from_dict

【继承关系】
  UserService → BaseService

【实例化关系】
  UserService.create_user → DataValidator
```

### 3. 模糊搜索
- 大小写不敏感
- 命名规范归一化（`UserService` ↔ `user_service`）
- 多级匹配（精确 → 归一化 → 子串 → 单词）
- 相关性评分

### 4. 持久化存储
- SQLite 数据库
- 基于内容哈希的增量更新
- 知识图谱（节点+边）
- PRD 和任务追踪

---

## 📊 性能指标

- **索引**：1000 文件 ~2-5 分钟
- **搜索**：<100ms（1000+ 符号）
- **上下文生成**：<500ms（深度 2）
- **存储**：1000 文件 ~10-50MB

---

## 🚀 典型工作流

### 新需求开发
```
1. index(paths=["src"])
2. prd(action="create", prd_id="feat_auth", ...)
3. prd(action="analyze", prd_id="feat_auth")
4. task(action="plan", prd_id="feat_auth")
5. context(task_id="feat_auth_task_1")
6. [Cursor/Claude 编码]
7. verify(file="src/auth.py", checks=["syntax", "type"])
8. task(action="update", task_id="...", status="completed")
```

### 代码理解
```
1. search(query="authenticate", type="symbol")
2. inspect(target="src/auth.py:authenticate")
3. search(query="AuthService", type="dependency")
4. context(symbols=["AuthService"], depth=2)
```

---

## 📈 数据统计示例

```
索引结果：
  • 42 个文件
  • 156 个符号
  • 198 个图谱节点
  • 1234 个关系边（调用/继承/实例化等）

关系分布：
  • calls: 402
  • instantiates: 33
  • decorates: 5
  • imports: 4
```

---

## 🎓 适用场景

- ✅ 大型代码库的理解和维护
- ✅ 新功能开发的上下文准备
- ✅ 代码重构的影响分析
- ✅ 团队协作的需求管理
- ✅ AI 辅助编码的上下文提供

---

## 📚 文档

- `README.md` - 快速开始
- `CAPABILITIES.md` - 详细能力文档
- `.cursor/skills/prd-iteration/` - PRD 迭代流程 Skill

---

**版本**: v1.0  
**最后更新**: 2026-01-28
