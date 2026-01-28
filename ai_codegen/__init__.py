"""
AI CodeGen - MCP-based Code Engineering Assistant V2

提供代码分析、接口提取、RAG 检索和专业编码辅助的 MCP 服务。
编码工作交给 MCP 客户端（如 Cursor/Claude）完成。

Usage:
    python -m ai_codegen.mcp_server.server --workspace /path/to/project
"""

__version__ = "2.0.0"

# Core exports
from ai_codegen.mcp_server.server import AICodeGenServer, create_server
from ai_codegen.mcp_server.persistence import PersistenceManager

# V2 新模块
from ai_codegen.models import CodeEntity, EntityType, RelationType
from ai_codegen.extractor import InterfaceExtractor, ContractInferencer, ModuleBoundaryDetector
from ai_codegen.mcp_server.persistence_v2 import PersistenceManagerV2

__all__ = [
    # V1 兼容
    "AICodeGenServer",
    "create_server", 
    "PersistenceManager",
    # V2 新模块
    "CodeEntity",
    "EntityType",
    "RelationType",
    "InterfaceExtractor",
    "ContractInferencer",
    "ModuleBoundaryDetector",
    "PersistenceManagerV2",
]
