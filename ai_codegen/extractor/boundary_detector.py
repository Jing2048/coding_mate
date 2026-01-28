"""
模块边界检测器

识别模块的输入输出边界。
"""

from typing import Dict, List, Set
from pathlib import Path
from ai_codegen.models import Boundary
from ai_codegen.parser.tree_sitter_parser import ParseResult


class ModuleBoundaryDetector:
    """模块边界检测器"""
    
    def detect_boundary(self, parse_result: ParseResult) -> Boundary:
        """
        检测模块边界
        
        Args:
            parse_result: 解析结果
        
        Returns:
            Boundary 对象
        """
        boundary = Boundary()
        
        # 分析导入（输入）
        boundary.inputs = self._extract_inputs(parse_result)
        
        # 分析导出（输出）
        boundary.outputs = self._extract_outputs(parse_result)
        
        # 识别副作用
        boundary.side_effects = self._detect_side_effects(parse_result)
        
        return boundary
    
    def _extract_inputs(self, parse_result: ParseResult) -> List[str]:
        """提取输入依赖"""
        inputs = set()
        
        for imp in parse_result.imports:
            if isinstance(imp, dict):
                module = imp.get('module', '')
                if module:
                    # 提取顶层模块名
                    top_level = module.split('.')[0]
                    inputs.add(top_level)
        
        return sorted(list(inputs))
    
    def _extract_outputs(self, parse_result: ParseResult) -> List[str]:
        """提取输出接口"""
        outputs = []
        
        # 公共类和函数
        for symbol in parse_result.symbols:
            if not symbol.name.startswith('_'):
                if symbol.node_type.value in ('class', 'function'):
                    outputs.append(symbol.name)
        
        # 导出列表
        if parse_result.exports:
            outputs.extend(parse_result.exports)
        
        return sorted(list(set(outputs)))
    
    def _detect_side_effects(self, parse_result: ParseResult) -> List[str]:
        """检测副作用"""
        side_effects = []
        
        # 从文件路径和符号名推断
        file_path = parse_result.file_path
        
        # 文件操作
        if any(keyword in file_path.lower() for keyword in ['file', 'storage', 'io']):
            side_effects.append("file_operation")
        
        # 网络操作
        if any(keyword in file_path.lower() for keyword in ['http', 'api', 'client', 'request']):
            side_effects.append("network_request")
        
        # 数据库操作
        if any(keyword in file_path.lower() for keyword in ['db', 'database', 'model', 'repository']):
            side_effects.append("database_operation")
        
        # 缓存操作
        if any(keyword in file_path.lower() for keyword in ['cache', 'redis', 'memcached']):
            side_effects.append("cache_operation")
        
        return side_effects
