# 基础使用示例

## 1. 接口提取

```python
from ai_codegen.mcp_server.server import AICodeGenServer
import asyncio

async def main():
    server = AICodeGenServer("/path/to/workspace")
    
    # 提取接口
    result = await server.tool_extract_interfaces(
        paths=["src/services/user.py", "src/models/user.py"],
        force=True
    )
    
    print(f"提取了 {result['extracted']} 个实体")

asyncio.run(main())
```

## 2. 列出接口

```python
# 列出所有类
classes = await server.tool_list_interfaces(
    entity_type="class",
    limit=20
)

for iface in classes['interfaces']:
    print(f"{iface['name']} - {iface['module']}")
```

## 3. 获取接口详情

```python
# 获取接口详情
interface = await server.tool_get_interface(
    interface_id="entity_123",
    include_contracts=True,
    include_dependencies=True
)

print(interface['llm_format'])
```

## 4. 语义搜索（需要 RAG 依赖）

```python
# 先同步数据
await server.tool_sync_rag(force=True)

# 语义搜索
results = await server.tool_search_interfaces(
    query="用户认证服务",
    use_hybrid=True,
    limit=10
)

for result in results['results']:
    print(f"{result['name']} (分数: {result.get('score', 0):.2f})")
```

## 5. 获取上下文

```python
# RAG 模式
context = await server.tool_context(
    mode="rag",
    max_tokens=4000,
    format="prompt"
)

print(context['text'])

# 依赖图模式
context = await server.tool_context(
    files=["src/services/user.py"],
    mode="dependency",
    max_tokens=4000
)
```

---

**版本**: V2.0  
**最后更新**: 2026-01-28
