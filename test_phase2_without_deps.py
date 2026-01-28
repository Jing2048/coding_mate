"""
Phase 2 测试（不依赖外部库，测试基础功能）

测试 RAG 系统的基础架构和接口。
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ai_codegen.extractor import InterfaceExtractor
from ai_codegen.mcp_server.persistence_v2 import PersistenceManagerV2
from ai_codegen.mcp_server.server import AICodeGenServer


async def test_phase2_basic():
    """Phase 2 基础功能测试（不依赖 RAG）"""
    
    print("=" * 70)
    print("Phase 2: 基础功能测试（RAG 依赖可选）")
    print("=" * 70)
    print()
    
    workspace_path = "."
    server = AICodeGenServer(workspace_path)
    
    # ========================================================================
    # 1. 接口提取和存储
    # ========================================================================
    print("【步骤 1: 接口提取和存储】")
    print("-" * 70)
    
    test_files = [
        "ai_codegen/mcp_server/server.py",
        "ai_codegen/models/code_entity.py",
    ]
    
    extract_result = await server.tool_extract_interfaces(
        paths=test_files,
        force=True
    )
    
    print(f"✓ 提取结果: {extract_result.get('extracted', 0)} 个实体")
    print(f"  总实体数: {extract_result.get('total_entities', 0)}")
    print()
    
    # ========================================================================
    # 2. 列出接口
    # ========================================================================
    print("【步骤 2: 列出接口】")
    print("-" * 70)
    
    list_result = await server.tool_list_interfaces(limit=10)
    print(f"✓ 接口列表: {list_result.get('total', 0)} 个接口")
    for i, iface in enumerate(list_result.get('interfaces', [])[:5], 1):
        print(f"  {i}. {iface['name']} ({iface['type']}) - {iface['module']}")
    print()
    
    # ========================================================================
    # 3. 获取接口详情
    # ========================================================================
    print("【步骤 3: 获取接口详情】")
    print("-" * 70)
    
    if list_result.get('interfaces'):
        first_id = list_result['interfaces'][0]['id']
        get_result = await server.tool_get_interface(
            interface_id=first_id,
            include_contracts=True,
            include_dependencies=True
        )
        
        if 'error' not in get_result:
            print(f"✓ 接口详情: {get_result['name']}")
            print(f"  描述: {get_result.get('description', '')[:60]}...")
            print(f"  LLM 格式长度: {len(get_result.get('llm_format', ''))} 字符")
        else:
            print(f"✗ 获取失败: {get_result['error']}")
    print()
    
    # ========================================================================
    # 4. 测试 RAG 系统可用性
    # ========================================================================
    print("【步骤 4: RAG 系统可用性检查】")
    print("-" * 70)
    
    if server.rag_manager:
        print("✓ RAG 系统可用")
        stats = server.rag_manager.get_stats()
        print(f"  向量数据库: {stats.get('vector_store', {}).get('total_entities', 0)} 个实体")
        print(f"  向量维度: {stats.get('embedding_dimension', 0)}")
    else:
        print("⚠ RAG 系统不可用（需要安装 chromadb 和 sentence-transformers）")
        print("  降级到 SQLite 搜索模式")
    print()
    
    # ========================================================================
    # 5. 搜索测试（降级模式）
    # ========================================================================
    print("【步骤 5: 搜索测试】")
    print("-" * 70)
    
    search_result = await server.tool_search_interfaces(
        query="server",
        limit=5
    )
    
    if "error" not in search_result:
        print(f"✓ 搜索成功: 'server'")
        print(f"  找到: {search_result.get('total', 0)} 个结果")
        print(f"  模式: {search_result.get('mode', 'unknown')}")
        
        for i, result in enumerate(search_result.get("results", [])[:3], 1):
            print(f"    {i}. {result.get('name')} ({result.get('type')})")
    else:
        print(f"✗ 搜索失败: {search_result.get('error')}")
    print()
    
    # ========================================================================
    # 6. 上下文测试（降级模式）
    # ========================================================================
    print("【步骤 6: 上下文检索测试（依赖图模式）】")
    print("-" * 70)
    
    context_result = await server.tool_context(
        task_id=None,
        files=["ai_codegen/models/code_entity.py"],
        max_tokens=2000,
        format="prompt",
        mode="dependency"
    )
    
    if isinstance(context_result, dict):
        if "text" in context_result:
            print(f"✓ 上下文生成成功（RAG 模式）")
            print(f"  长度: {len(context_result['text'])} 字符")
        else:
            print(f"✓ 上下文生成成功（依赖图模式）")
            print(f"  文件数: {context_result.get('summary', {}).get('total_files', 0)}")
            print(f"  Token 使用: {context_result.get('summary', {}).get('tokens_used', 0)}")
    print()
    
    # ========================================================================
    # 7. 统计信息
    # ========================================================================
    print("【步骤 7: 系统统计】")
    print("-" * 70)
    
    if server.db_v2:
        sqlite_stats = server.db_v2.get_statistics()
        print(f"✓ SQLite 统计:")
        print(f"  总实体: {sqlite_stats.get('total_entities', 0)}")
        print(f"  总依赖: {sqlite_stats.get('total_dependencies', 0)}")
        print(f"  总模块: {sqlite_stats.get('total_modules', 0)}")
        print(f"  总领域: {sqlite_stats.get('total_domains', 0)}")
    print()
    
    print("=" * 70)
    print("✓ Phase 2 基础测试完成")
    print("=" * 70)
    print()
    print("注意: 要启用完整的 RAG 功能，请安装依赖:")
    print("  pip install chromadb sentence-transformers")


if __name__ == "__main__":
    asyncio.run(test_phase2_basic())
