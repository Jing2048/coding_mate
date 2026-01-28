# AI CodeGen MCP Server - 设计哲学

## 🎯 核心理念

### 从"完成需求"到"更好的编码"

**V1 版本**：专注于完成需求
- PRD → 任务 → 编码 → 验证
- 关注功能实现
- 缺乏架构层面的指导

**V2 版本**：专注于更好的编码
- 接口驱动开发
- 依赖感知编码
- 架构级别的建议
- 专业编码辅助

---

## 🏗️ 设计哲学

### 1. 接口驱动开发 (Interface-Driven Development)

#### 理念

**代码应该围绕接口而非实现来组织**。接口定义了模块的契约，是实现和使用的桥梁。

#### 实践

1. **自动提取接口**
   - 从代码自动识别公共 API
   - 提取方法签名和类型信息
   - 推断接口契约

2. **接口优先设计**
   - 先定义接口，再实现
   - 基于接口生成代码
   - 验证实现是否符合接口

3. **接口作为文档**
   - 接口定义即文档
   - 清晰的输入输出规范
   - 契约约束明确

#### 示例

```python
# 自动提取的接口定义
{
  "name": "UserService",
  "module": "services.user",
  "description": "用户服务接口",
  "methods": [
    {
      "name": "get_user",
      "parameters": [
        {"name": "user_id", "type": "int"}
      ],
      "return_type": "User",
      "contract": {
        "preconditions": ["user_id > 0"],
        "postconditions": ["result is not None"],
        "throws": ["UserNotFoundError if user not exists"]
      }
    }
  ],
  "boundary": {
    "inputs": ["Database", "Cache"],
    "outputs": ["User", "UserList"]
  }
}
```

---

### 2. 依赖感知编码 (Dependency-Aware Coding)

#### 理念

**理解代码的依赖关系是高质量编码的基础**。只有理解依赖，才能：
- 分析改动的影响范围
- 保持接口契约的一致性
- 避免破坏性变更

#### 实践

1. **构建完整依赖图**
   - 调用关系（calls）
   - 继承关系（extends）
   - 实例化关系（instantiates）
   - 导入关系（imports）

2. **依赖影响分析**
   - 接口变更影响哪些实现
   - 方法修改影响哪些调用点
   - 模块重构的影响范围

3. **依赖驱动的上下文**
   - 基于依赖关系收集上下文
   - 理解调用链和依赖链
   - 提供相关的接口和实现

#### 示例

```
【依赖关系图】

UserService
  ├─ calls → Database.query
  ├─ calls → Cache.get
  ├─ instantiates → UserValidator
  └─ extends → BaseService

【影响分析】

修改 UserService.get_user 方法：
  ✓ 影响：UserController (调用者)
  ✓ 影响：UserServiceTest (测试)
  ✓ 影响：UserService 的其他方法（内部依赖）
  ⚠️ 破坏性变更：返回类型从 User 改为 Optional[User]
```

---

### 3. 知识图谱增强 (Knowledge Graph Enhanced)

#### 理念

**代码知识应该以图谱形式组织**，支持语义搜索和推理。

#### 实践

1. **多维度知识存储**
   - 结构化数据（SQLite）：节点、边、属性
   - 向量数据（Vector DB）：语义嵌入
   - 关系数据：调用、继承、依赖

2. **语义搜索能力**
   - 基于意图搜索接口
   - 理解上下文相关性
   - 推荐相关接口和依赖

3. **推理能力**
   - 基于依赖关系推理影响
   - 基于接口规范推理实现
   - 基于模式推理最佳实践

#### 示例

```
【语义搜索】

查询："需要验证用户输入的服务"

检索结果：
  1. UserValidator (相关性: 0.95)
  2. InputValidator (相关性: 0.87)
  3. DataValidator (相关性: 0.82)

【推理】

基于接口定义：
  UserService.get_user(user_id: int) -> User
  
推理：
  - 需要处理 user_id <= 0 的情况
  - 需要处理用户不存在的情况
  - 可能需要缓存查询结果
```

---

### 4. 专业编码辅助 (Professional Coding Assistant)

#### 理念

**不是简单地完成需求，而是提供架构级别的编码指导**。

#### 实践

1. **架构级别建议**
   - 模块设计建议
   - 接口设计模式推荐
   - 依赖关系优化

2. **代码质量关注**
   - 接口完整性
   - 契约覆盖率
   - 依赖合理性

3. **最佳实践指导**
   - 基于项目模式推荐
   - 基于接口规范生成
   - 基于依赖关系优化

#### 示例

```
【编码建议】

任务：实现用户认证功能

建议：
  1. 接口设计：
     - 创建 AuthService 接口
     - 定义 authenticate(username, password) 方法
     - 定义 validate_token(token) 方法
  
  2. 依赖关系：
     - 依赖 UserService (获取用户信息)
     - 依赖 TokenService (生成/验证 token)
     - 依赖 PasswordHasher (密码加密)
  
  3. 契约要求：
     - authenticate: 前置条件（username/password 非空）
     - authenticate: 后置条件（返回 Token 或 None）
     - authenticate: 异常（InvalidCredentials）
  
  4. 实现建议：
     - 使用依赖注入
     - 添加日志记录
     - 实现重试机制
```

---

## 🔄 工作流程

### V2 完整工作流

```
1. 代码索引
   index(paths=["src"])
   ↓
   [自动提取接口定义]
   [构建依赖关系图]
   [向量化存储]

2. 任务理解
   context(task_id="task_001", mode="interface_driven")
   ↓
   [RAG 检索相关接口]
   [分析依赖关系]
   [生成编码建议]

3. 接口驱动编码
   [基于接口规范生成代码]
   [遵循契约要求]
   [保持依赖兼容性]

4. 影响分析
   analyze_impact(interface="UserService", changes={...})
   ↓
   [分析影响范围]
   [检测破坏性变更]
   [生成迁移建议]

5. 验证与优化
   verify(file="src/user_service.py", checks=["syntax", "type", "contract"])
   ↓
   [验证接口实现]
   [检查契约满足]
   [评估代码质量]
```

---

## 📊 对比：V1 vs V2

| 维度 | V1 | V2 |
|------|----|----|
| **目标** | 完成需求 | 更好的编码 |
| **接口** | 手动定义 | 自动提取 |
| **依赖** | 基础关系 | 完整图谱 + 语义搜索 |
| **上下文** | 文件级 | 接口级 + 依赖感知 |
| **代码生成** | 基于文件 | 基于接口规范 |
| **影响分析** | ❌ | ✅ 完整分析 |
| **架构建议** | ❌ | ✅ 专业指导 |

---

## 🎓 设计原则

### 1. 接口即契约 (Interface as Contract)

- 接口定义清晰的输入输出
- 契约约束行为规范
- 实现必须满足契约

### 2. 依赖即知识 (Dependency as Knowledge)

- 依赖关系是代码知识
- 理解依赖才能理解代码
- 依赖变化需要影响分析

### 3. 图谱即智能 (Graph as Intelligence)

- 知识图谱支持推理
- 语义搜索提升效率
- 上下文感知增强准确性

### 4. 辅助即专业 (Assistant as Professional)

- 不是完成需求，而是指导编码
- 关注架构和质量
- 提供最佳实践建议

---

## 🚀 未来愿景

### 长期目标

1. **智能代码生成**
   - 基于接口规范自动生成实现
   - 自动满足契约要求
   - 自动处理依赖关系

2. **架构演进支持**
   - 识别架构问题
   - 推荐重构方案
   - 指导架构演进

3. **团队协作增强**
   - 接口变更通知
   - 影响范围共享
   - 编码规范统一

---

**版本**: V2.0  
**状态**: 设计阶段  
**最后更新**: 2026-01-28
