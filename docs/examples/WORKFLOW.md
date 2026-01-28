# 完整工作流示例

## 场景：实现新功能

### 1. 提取现有接口

```python
# 提取项目中的接口
await server.tool_extract_interfaces(
    paths=["src/"],
    force=False  # 增量更新
)
```

### 2. 同步到向量数据库

```python
# 同步到 RAG 系统
await server.tool_sync_rag(force=False)
```

### 3. 搜索相关接口

```python
# 搜索相关接口
results = await server.tool_search_interfaces(
    query="用户认证和授权",
    use_hybrid=True,
    limit=10
)

# 查看相关接口
for result in results['results']:
    detail = await server.tool_get_interface(
        interface_id=result['id'],
        include_contracts=True,
        include_dependencies=True
    )
    print(detail['llm_format'])
```

### 4. 获取实现上下文

```python
# 获取上下文用于编码
context = await server.tool_context(
    mode="rag",
    max_tokens=4000,
    format="prompt"
)

# 使用上下文进行编码（在 Cursor/Claude 中）
# context['text'] 包含所有相关信息
```

### 5. 验证代码

```python
# 验证生成的代码
verification = await server.tool_verify(
    file="src/services/auth.py",
    checks=["syntax", "type", "test"]
)
```

---

## 场景：理解现有代码

### 1. 搜索符号

```python
# 搜索特定功能
results = await server.tool_search_interfaces(
    query="密码加密",
    limit=5
)
```

### 2. 查看依赖关系

```python
# 获取接口详情，包括依赖
interface = await server.tool_get_interface(
    interface_id="entity_123",
    include_dependencies=True
)

# 查看依赖的接口
for dep in interface['dependencies']:
    dep_detail = await server.tool_get_interface(
        interface_id=dep['target_id']
    )
    print(f"{dep['relation_type']}: {dep_detail['name']}")
```

### 3. 分析影响范围

```python
# 列出所有使用某个接口的地方
dependents = await server.db_v2.get_dependents("entity_123")

for dependent_id in dependents:
    entity = await server.tool_get_interface(dependent_id)
    print(f"被 {entity['name']} 使用")
```

---

## 场景：重构代码

### 1. 提取接口定义

```python
# 提取要重构的模块
await server.tool_extract_interfaces(
    paths=["src/legacy/"],
    force=True
)
```

### 2. 分析依赖关系

```python
# 获取所有依赖
interface = await server.tool_get_interface(
    interface_id="legacy_service",
    include_dependencies=True
)

# 查看所有依赖者
dependents = await server.db_v2.get_dependents("legacy_service")
```

### 3. 生成新接口

```python
# 基于旧接口生成新接口定义
# （在 Cursor/Claude 中使用 context 工具）
context = await server.tool_context(
    files=["src/legacy/old_service.py"],
    mode="rag",
    format="prompt"
)
```

---

**版本**: V2.0  
**最后更新**: 2026-01-28
