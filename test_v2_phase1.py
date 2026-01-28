"""
Phase 1 完整功能测试

测试接口提取、存储和查询的完整流程。
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ai_codegen.extractor import InterfaceExtractor
from ai_codegen.mcp_server.persistence_v2 import PersistenceManagerV2
from ai_codegen.mcp_server.server import AICodeGenServer


async def test_phase1():
    """测试 Phase 1 完整功能"""
    
    print("=" * 60)
    print("Phase 1 完整功能测试")
    print("=" * 60)
    print()
    
    # 1. 测试接口提取
    print("【1. 接口提取测试】")
    print("-" * 60)
    extractor = InterfaceExtractor()
    
    test_files = [
        "ai_codegen/mcp_server/server.py",
        "ai_codegen/models/code_entity.py",
    ]
    
    all_entities = []
    for file_path in test_files:
        if Path(file_path).exists():
            entities = extractor.extract_from_file(file_path)
            all_entities.extend(entities)
            print(f"  ✓ {file_path}: 提取到 {len(entities)} 个实体")
            for e in entities[:2]:
                print(f"    - {e.name} ({e.type.value})")
        else:
            print(f"  ✗ {file_path}: 文件不存在")
    
    print(f"\n  总计: {len(all_entities)} 个实体")
    print()
    
    # 2. 测试存储
    print("【2. 存储测试】")
    print("-" * 60)
    db_v2 = PersistenceManagerV2(".")
    
    saved_count = 0
    for entity in all_entities:
        try:
            db_v2.save_entity(entity)
            saved_count += 1
        except Exception as e:
            print(f"  ✗ 保存失败 {entity.id}: {e}")
    
    print(f"  ✓ 成功保存 {saved_count}/{len(all_entities)} 个实体")
    
    stats = db_v2.get_statistics()
    print(f"  数据库统计:")
    print(f"    - 总实体数: {stats['total_entities']}")
    print(f"    - 总依赖数: {stats['total_dependencies']}")
    print(f"    - 总模块数: {stats['total_modules']}")
    print()
    
    # 3. 测试查询
    print("【3. 查询测试】")
    print("-" * 60)
    
    # 按 ID 查询
    if all_entities:
        test_entity = all_entities[0]
        retrieved = db_v2.get_entity(test_entity.id)
        if retrieved:
            print(f"  ✓ 按 ID 查询成功: {retrieved.name}")
            print(f"    描述: {retrieved.description[:50]}...")
            if retrieved.embedding_text:
                print(f"    Embedding Text: {retrieved.embedding_text[:80]}...")
        else:
            print(f"  ✗ 查询失败: {test_entity.id}")
    
    # 按模块查询
    entities_by_module = db_v2.get_entities_by_module("ai_codegen.mcp_server.server")
    print(f"  ✓ 按模块查询: {len(entities_by_module)} 个实体")
    
    # 按类型查询
    classes = db_v2.get_entities_by_type("class")
    functions = db_v2.get_entities_by_type("function")
    print(f"  ✓ 按类型查询: {len(classes)} 个类, {len(functions)} 个函数")
    
    # 语义搜索
    search_results = db_v2.search_entities("server", limit=5)
    print(f"  ✓ 语义搜索 'server': {len(search_results)} 个结果")
    for r in search_results[:3]:
        print(f"    - {r.name} ({r.type.value})")
    print()
    
    # 4. 测试 MCP Server 工具
    print("【4. MCP Server 工具测试】")
    print("-" * 60)
    server = AICodeGenServer(".")
    
    # extract_interfaces
    result = await server.tool_extract_interfaces(
        paths=["ai_codegen/models/code_entity.py"],
        force=True
    )
    print(f"  ✓ extract_interfaces: {result.get('extracted', 0)} 个实体")
    
    # list_interfaces
    if result.get('extracted', 0) > 0:
        list_result = await server.tool_list_interfaces(limit=5)
        print(f"  ✓ list_interfaces: {list_result.get('total', 0)} 个接口")
        for iface in list_result.get('interfaces', [])[:3]:
            print(f"    - {iface['name']} ({iface['type']})")
        
        # get_interface
        if list_result.get('interfaces'):
            first_id = list_result['interfaces'][0]['id']
            get_result = await server.tool_get_interface(
                interface_id=first_id,
                include_contracts=True,
                include_dependencies=True
            )
            if 'error' not in get_result:
                print(f"  ✓ get_interface: {get_result['name']}")
                if 'llm_format' in get_result:
                    print(f"    LLM 格式长度: {len(get_result['llm_format'])} 字符")
            else:
                print(f"  ✗ get_interface: {get_result['error']}")
    print()
    
    # 5. 测试 LLM 格式化
    print("【5. LLM 格式化测试】")
    print("-" * 60)
    if all_entities:
        test_entity = all_entities[0]
        llm_text = test_entity.format_for_llm(
            include_dependencies=True,
            include_examples=True
        )
        print(f"  ✓ LLM 格式化成功")
        print(f"    长度: {len(llm_text)} 字符")
        print(f"    预览:")
        print("    " + "\n    ".join(llm_text.split('\n')[:10]))
    print()
    
    print("=" * 60)
    print("✓ Phase 1 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_phase1())
