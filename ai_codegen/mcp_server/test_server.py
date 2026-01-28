"""
MCP Server 测试脚本
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ai_codegen.mcp_server.server import AICodeGenServer


async def test_server():
    """测试服务器功能"""
    
    workspace = "/Users/jing/LLM"
    server = AICodeGenServer(workspace)
    
    print("=" * 60)
    print("AI CodeGen MCP Server 测试")
    print("=" * 60)
    
    # 1. 测试代码库分析
    print("\n### 1. 分析代码库")
    result = await server.analyze_codebase(
        paths=['ai_codegen'],
        extensions=['.py'],
        incremental=True
    )
    print(f"  分析文件: {result['analyzed_files']}")
    print(f"  跳过文件: {result['skipped_files']}")
    print(f"  新符号: {result['new_symbols']}")
    print(f"  总文件: {result['total_files']}")
    print(f"  总节点: {result['total_nodes']}")
    
    # 2. 测试 PRD 分析
    print("\n### 2. 分析 PRD")
    prd_content = """
# 新功能：支持指定精度

## 需求背景
当前系统需要支持可配置的精度参数。

## 功能需求
- FR-1: 创建精度配置类
- FR-2: 支持预设精度级别

## 验收标准
- AC-1: 可以设置自定义精度
- AC-2: 可以使用预设级别
"""
    result = await server.analyze_prd(prd_content, "test_prd_001")
    print(f"  PRD ID: {result['prd_id']}")
    print(f"  标题: {result['title']}")
    print(f"  改动点: {len(result['change_points'])} 个")
    for cp in result['change_points']:
        print(f"    - {cp['title']}")
    
    # 3. 测试代码查询
    print("\n### 3. 查询代码")
    result = await server.query_code(query_type="statistics")
    print(f"  统计信息: {result}")
    
    # 4. 测试接口设计
    print("\n### 4. 设计接口")
    result = await server.design_interface(
        name="ICalculator",
        module="math.calculator",
        description="计算器接口",
        methods=[
            {
                "name": "add",
                "description": "加法运算",
                "parameters": [
                    {"name": "a", "type": {"kind": "primitive", "name": "float"}, "description": "第一个数"},
                    {"name": "b", "type": {"kind": "primitive", "name": "float"}, "description": "第二个数"}
                ],
                "return_type": {"kind": "primitive", "name": "float"},
                "contract": {
                    "preconditions": [
                        {"expression": "a is not None", "description": "a 不能为空"},
                        {"expression": "b is not None", "description": "b 不能为空"}
                    ],
                    "postconditions": [
                        {"expression": "result == a + b", "description": "返回正确的和"}
                    ]
                }
            }
        ]
    )
    print(f"  接口: {result['name']}")
    print(f"  模块: {result['module']}")
    print(f"  方法: {result['methods']}")
    print(f"  TypeScript:\n{result['typescript'][:300]}...")
    
    # 5. 测试任务规划
    print("\n### 5. 创建任务计划")
    try:
        result = await server.plan_tasks("test_prd_001")
        if 'error' in result:
            print(f"  跳过: {result['error']}")
        else:
            print(f"  计划 ID: {result['plan_id']}")
            print(f"  任务数: {result['total_tasks']}")
            print(f"  就绪任务: {result['ready_tasks']}")
    except Exception as e:
        print(f"  跳过: PRD 改动点不足以生成任务 ({e})")
    
    # 6. 测试代码验证
    print("\n### 6. 验证代码")
    test_code = '''
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b
'''
    result = await server.verify_code(test_code, "python")
    print(f"  验证通过: {result['passed']}")
    
    # 7. 测试获取上下文
    print("\n### 7. 获取上下文")
    result = await server.get_context(
        interface_names=["ICalculator"]
    )
    print(f"  接口数: {len(result['interfaces'])}")
    print(f"  符号数: {len(result['symbols'])}")
    
    # 8. 列出所有接口
    print("\n### 8. 列出接口")
    result = await server.list_interfaces()
    print(f"  接口数: {result['count']}")
    for iface in result['interfaces']:
        print(f"    - {iface['name']} ({iface['method_count']} 方法)")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_server())
