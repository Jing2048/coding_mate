"""
Phase 2 完整功能测试和验证

测试 RAG 系统的完整流程：提取 → 存储 → 向量化 → 搜索 → 检索
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ai_codegen.extractor import InterfaceExtractor
from ai_codegen.mcp_server.persistence_v2 import PersistenceManagerV2
from ai_codegen.mcp_server.server import AICodeGenServer
from ai_codegen.rag import RAGManager


async def test_phase2_complete():
    """Phase 2 完整测试"""
    
    print("=" * 70)
    print("Phase 2: RAG 系统完整功能测试")
    print("=" * 70)
    print()
    
    workspace_path = "."
    
    # ========================================================================
    # 1. 接口提取和存储
    # ========================================================================
    print("【步骤 1: 接口提取和存储】")
    print("-" * 70)
    
    server = AICodeGenServer(workspace_path)
    
    # 提取接口
    test_files = [
        "ai_codegen/mcp_server/server.py",
        "ai_codegen/models/code_entity.py",
        "ai_codegen/extractor/interface_extractor.py",
    ]
    
    extract_result = await server.tool_extract_interfaces(
        paths=test_files,
        force=True
    )
    
    print(f"✓ 提取结果: {extract_result.get('extracted', 0)} 个实体")
    print(f"  总实体数: {extract_result.get('total_entities', 0)}")
    print()
    
    # ========================================================================
    # 2. RAG 系统同步
    # ========================================================================
    print("【步骤 2: RAG 系统同步】")
    print("-" * 70)
    
    sync_result = await server.tool_sync_rag(force=True)
    
    if sync_result.get("success"):
        stats = sync_result.get("stats", {})
        print(f"✓ 同步成功")
        print(f"  向量数据库: {stats.get('vector_store', {}).get('total_entities', 0)} 个实体")
        print(f"  SQLite: {stats.get('sqlite', {}).get('total_entities', 0)} 个实体")
        print(f"  向量维度: {stats.get('embedding_dimension', 0)}")
    else:
        print(f"✗ 同步失败: {sync_result.get('error', 'Unknown error')}")
        return
    
    print()
    
    # ========================================================================
    # 3. 语义搜索测试
    # ========================================================================
    print("【步骤 3: 语义搜索测试】")
    print("-" * 70)
    
    search_queries = [
        "服务器",
        "接口提取",
        "代码实体",
        "持久化存储",
    ]
    
    for query in search_queries:
        search_result = await server.tool_search_interfaces(
            query=query,
            limit=5
        )
        
        if "error" not in search_result:
            print(f"✓ 查询: '{query}'")
            print(f"  找到: {search_result.get('total', 0)} 个结果")
            print(f"  模式: {search_result.get('mode', 'unknown')}")
            
            for i, result in enumerate(search_result.get("results", [])[:3], 1):
                print(f"    {i}. {result.get('name')} ({result.get('type')})")
                print(f"       描述: {result.get('description', '')[:50]}...")
        else:
            print(f"✗ 查询失败: {search_result.get('error')}")
        print()
    
    # ========================================================================
    # 4. RAG 上下文检索测试
    # ========================================================================
    print("【步骤 4: RAG 上下文检索测试】")
    print("-" * 70)
    
    test_tasks = [
        "实现用户认证功能",
        "优化代码上下文管理",
        "添加新的接口提取能力",
    ]
    
    for task_desc in test_tasks:
        context_result = await server.tool_context(
            task_id=None,
            max_tokens=4000,
            format="prompt",
            mode="rag"
        )
        
        if isinstance(context_result, dict) and "text" in context_result:
            print(f"✓ 任务: '{task_desc}'")
            print(f"  上下文长度: {len(context_result['text'])} 字符")
            print(f"  模式: {context_result.get('mode', 'unknown')}")
            print(f"  接口数量: {len(context_result.get('interfaces', []))}")
            print(f"  建议数量: {len(context_result.get('suggestions', []))}")
            
            # 显示前 200 字符
            preview = context_result['text'][:200]
            print(f"  预览: {preview}...")
        else:
            print(f"✗ 检索失败: {context_result}")
        print()
    
    # ========================================================================
    # 5. 混合搜索测试
    # ========================================================================
    print("【步骤 5: 混合搜索测试】")
    print("-" * 70)
    
    hybrid_result = await server.tool_search_interfaces(
        query="代码生成和验证",
        limit=5,
        use_hybrid=True
    )
    
    if "error" not in hybrid_result:
        print(f"✓ 混合搜索: '代码生成和验证'")
        print(f"  找到: {hybrid_result.get('total', 0)} 个结果")
        print(f"  模式: {hybrid_result.get('mode', 'unknown')}")
        
        for i, result in enumerate(hybrid_result.get("results", [])[:3], 1):
            print(f"    {i}. {result.get('name')} (分数: {result.get('score', 0):.3f})")
    else:
        print(f"✗ 混合搜索失败: {hybrid_result.get('error')}")
    print()
    
    # ========================================================================
    # 6. 性能测试
    # ========================================================================
    print("【步骤 6: 性能测试】")
    print("-" * 70)
    
    import time
    
    # 搜索性能
    start = time.time()
    await server.tool_search_interfaces("server", limit=10)
    search_time = time.time() - start
    print(f"✓ 语义搜索延迟: {search_time*1000:.1f}ms")
    
    # 检索性能
    start = time.time()
    await server.tool_context(task_id=None, mode="rag", max_tokens=2000)
    retrieve_time = time.time() - start
    print(f"✓ 上下文检索延迟: {retrieve_time*1000:.1f}ms")
    print()
    
    # ========================================================================
    # 7. 统计信息
    # ========================================================================
    print("【步骤 7: 系统统计】")
    print("-" * 70)
    
    if server.rag_manager:
        stats = server.rag_manager.get_stats()
        print(f"✓ RAG 系统统计:")
        print(f"  向量数据库: {stats.get('vector_store', {}).get('total_entities', 0)} 个实体")
        print(f"  SQLite: {stats.get('sqlite', {}).get('total_entities', 0)} 个实体")
        print(f"  向量维度: {stats.get('embedding_dimension', 0)}")
    
    if server.db_v2:
        sqlite_stats = server.db_v2.get_statistics()
        print(f"✓ SQLite 统计:")
        print(f"  总实体: {sqlite_stats.get('total_entities', 0)}")
        print(f"  总依赖: {sqlite_stats.get('total_dependencies', 0)}")
        print(f"  总模块: {sqlite_stats.get('total_modules', 0)}")
        print(f"  总领域: {sqlite_stats.get('total_domains', 0)}")
    print()
    
    print("=" * 70)
    print("✓ Phase 2 完整测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_phase2_complete())
