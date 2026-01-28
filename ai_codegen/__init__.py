"""
AI CodeGen - MCP-based Code Engineering Assistant

提供代码分析、PRD 管理和验证能力的 MCP 服务。
编码工作交给 MCP 客户端（如 Cursor/Claude）完成。

Usage:
    python -m ai_codegen.mcp_server.server --workspace /path/to/project
"""

__version__ = "0.2.0"

# Core exports
from ai_codegen.mcp_server.server import AICodeGenServer, create_server
from ai_codegen.mcp_server.persistence import PersistenceManager

__all__ = [
    "AICodeGenServer",
    "create_server", 
    "PersistenceManager",
]
