"""
接口提取器

从代码自动提取接口定义，构建 CodeEntity。
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import re
import ast as py_ast

from ai_codegen.models import (
    CodeEntity,
    EntityType,
    Signature,
    Parameter,
    TypeInfo,
    Contract,
    Boundary,
    Dependency,
    RelationType,
)
from ai_codegen.parser import TreeSitterParser, CodeSymbol, NodeType


class InterfaceExtractor:
    """
    接口提取器
    
    从代码自动提取接口定义，构建 CodeEntity。
    """
    
    def __init__(self, parser: Optional[TreeSitterParser] = None):
        """
        初始化提取器
        
        Args:
            parser: Tree-sitter 解析器（可选，会自动创建）
        """
        self.parser = parser or TreeSitterParser()
        self.contract_inferencer = None  # 延迟初始化
    
    def extract_from_file(self, file_path: str) -> List[CodeEntity]:
        """
        从文件提取所有接口
        
        Args:
            file_path: 文件路径
        
        Returns:
            CodeEntity 列表
        """
        path = Path(file_path)
        if not path.exists():
            return []
        
        source_code = path.read_text(encoding='utf-8')
        return self.extract_from_source(source_code, str(file_path))
    
    def extract_from_source(
        self,
        source_code: str,
        file_path: str
    ) -> List[CodeEntity]:
        """
        从源代码提取接口
        
        Args:
            source_code: 源代码
            file_path: 文件路径（用于生成 ID）
        
        Returns:
            CodeEntity 列表
        """
        entities = []
        
        # 解析文件
        ext = Path(file_path).suffix
        lang_map = {'.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.swift': 'swift', '.go': 'go'}
        language = lang_map.get(ext, 'python')
        
        try:
            result = self.parser.parse_source(source_code, file_path, language)
        except Exception:
            return entities
        
        # 提取模块路径
        module_path = self._extract_module_path(file_path)
        
        # 提取类和方法
        classes = {}
        for symbol in result.symbols:
            if symbol.node_type == NodeType.CLASS:
                entity = self._extract_class_entity(
                    symbol,
                    source_code,
                    file_path,
                    module_path,
                    result
                )
                if entity:
                    entities.append(entity)
                    classes[symbol.name] = entity
            
            elif symbol.node_type in (NodeType.FUNCTION, NodeType.METHOD):
                # 检查是否是类的方法
                parent_class = symbol.parent
                if parent_class and parent_class in classes:
                    # 这是类的方法，已经在类实体中处理
                    continue
                
                entity = self._extract_function_entity(
                    symbol,
                    source_code,
                    file_path,
                    module_path,
                    result
                )
                if entity:
                    entities.append(entity)
        
        return entities
    
    def _extract_class_entity(
        self,
        symbol: CodeSymbol,
        source_code: str,
        file_path: str,
        module_path: str,
        parse_result: Any
    ) -> Optional[CodeEntity]:
        """提取类实体"""
        class_name = symbol.name
        if not class_name or class_name.startswith('_'):
            return None  # 跳过私有类
        
        entity_id = f"{module_path}:{class_name}"
        
        # 提取描述
        description = symbol.docstring or f"{class_name} 类"
        
        # 提取继承关系
        dependencies = []
        if symbol.annotations.get('extends'):
            for parent in symbol.annotations['extends']:
                dependencies.append(Dependency(
                    target_id=parent,
                    relation_type=RelationType.EXTENDS,
                    context="类继承",
                    line=symbol.location.start_line
                ))
        
        # 提取类的方法
        methods = []
        for child_symbol in parse_result.symbols:
            if (child_symbol.parent == class_name and 
                child_symbol.node_type in (NodeType.METHOD, NodeType.FUNCTION)):
                method_sig = self._extract_signature_from_symbol(child_symbol, source_code)
                if method_sig:
                    methods.append(method_sig)
        
        # 构建边界
        boundary = self._extract_class_boundary(symbol, source_code, parse_result)
        
        # 构建实体
        entity = CodeEntity(
            id=entity_id,
            type=EntityType.CLASS,
            name=class_name,
            module=module_path,
            file_path=file_path,
            description=description,
            purpose=self._infer_purpose(description, class_name),
            domain=self._infer_domain(class_name, description),
            contract=self._infer_class_contract(symbol, source_code),
            boundary=boundary,
            dependencies=dependencies,
            source_snippet=self._extract_class_snippet(source_code, symbol),
            tags=self._extract_tags(class_name, description),
            complexity=self._estimate_complexity(symbol, source_code),
            last_modified=Path(file_path).stat().st_mtime if Path(file_path).exists() else 0.0
        )
        
        return entity
    
    def _extract_function_entity(
        self,
        symbol: CodeSymbol,
        source_code: str,
        file_path: str,
        module_path: str,
        parse_result: Any
    ) -> Optional[CodeEntity]:
        """提取函数实体"""
        func_name = symbol.name
        if not func_name or func_name.startswith('_'):
            return None  # 跳过私有函数
        
        entity_id = f"{module_path}:{func_name}"
        
        # 提取描述
        description = symbol.docstring or f"{func_name} 函数"
        
        # 提取签名
        signature = self._extract_signature_from_symbol(symbol, source_code)
        
        # 推断契约
        contract = self._infer_function_contract(symbol, source_code)
        
        # 提取依赖
        dependencies = self._extract_function_dependencies(symbol, source_code, parse_result)
        
        # 构建实体
        entity = CodeEntity(
            id=entity_id,
            type=EntityType.FUNCTION,
            name=func_name,
            module=module_path,
            file_path=file_path,
            description=description,
            purpose=self._infer_purpose(description, func_name),
            domain=self._infer_domain(func_name, description),
            signature=signature,
            contract=contract,
            dependencies=dependencies,
            source_snippet=self._extract_function_snippet(source_code, symbol),
            examples=self._extract_examples(symbol, source_code),
            tags=self._extract_tags(func_name, description),
            complexity=self._estimate_complexity(symbol, source_code),
            last_modified=Path(file_path).stat().st_mtime if Path(file_path).exists() else 0.0
        )
        
        return entity
    
    def _extract_signature_from_symbol(
        self,
        symbol: CodeSymbol,
        source_code: str
    ) -> Optional[Signature]:
        """从符号提取方法签名"""
        func_name = symbol.name
        
        # 如果有 signature 字段，直接解析
        if symbol.signature:
            return self._parse_signature_string(symbol.signature, func_name)
        
        # 否则从源代码解析
        return self._extract_signature_from_source(symbol, source_code)
    
    def _extract_signature_from_source(
        self,
        symbol: CodeSymbol,
        source_code: str
    ) -> Optional[Signature]:
        """从源代码提取签名（使用 AST）"""
        func_name = symbol.name
        start_line = symbol.location.start_line
        end_line = symbol.location.end_line
        
        lines = source_code.split('\n')
        if start_line > len(lines):
            return None
        
        # 提取函数定义行
        func_lines = lines[start_line-1:min(start_line+10, len(lines))]
        func_text = '\n'.join(func_lines)
        
        # Python AST 解析
        if Path(symbol.location.file_path).suffix == '.py':
            try:
                tree = py_ast.parse(func_text)
                for node in py_ast.walk(tree):
                    if isinstance(node, py_ast.FunctionDef) and node.name == func_name:
                        return self._ast_to_signature(node, func_text)
            except Exception:
                pass
        
        # 正则表达式后备方案
        return self._regex_extract_signature(func_name, func_text)
    
    def _ast_to_signature(self, node: py_ast.FunctionDef, source: str) -> Signature:
        """从 AST 节点转换为 Signature"""
        parameters = []
        
        for arg in node.args.args:
            arg_name = arg.arg
            if arg_name == 'self':
                continue
            
            # 提取类型注解
            if arg.annotation:
                type_str = py_ast.unparse(arg.annotation)
            else:
                type_str = "Any"
            
            parameters.append(Parameter(
                name=arg_name,
                type=TypeInfo(name=type_str),
                description=""
            ))
        
        # 提取返回类型
        return_type = None
        if node.returns:
            return_type = TypeInfo(name=py_ast.unparse(node.returns))
        
        # 检查是否是异步
        is_async = False
        for decorator in node.decorator_list:
            if isinstance(decorator, py_ast.Name) and decorator.id == 'asynccontextmanager':
                is_async = True
                break
        
        return Signature(
            name=node.name,
            parameters=parameters,
            return_type=return_type,
            is_async=is_async
        )
    
    def _regex_extract_signature(self, func_name: str, source: str) -> Optional[Signature]:
        """使用正则表达式提取签名（后备方案）"""
        # 匹配 async def 或 def
        pattern = rf'(?:async\s+)?def\s+{re.escape(func_name)}\s*\(([^)]*)\)(?:\s*->\s*([^:]+))?'
        match = re.search(pattern, source)
        if not match:
            return None
        
        params_str = match.group(1)
        return_type_str = match.group(2)
        
        parameters = []
        for param in params_str.split(','):
            param = param.strip()
            if not param or param == 'self':
                continue
            
            # 解析 name: type 或 name = default
            if ':' in param:
                name, type_str = param.split(':', 1)
                name = name.strip()
                type_str = type_str.strip().split('=')[0].strip()
            elif '=' in param:
                name = param.split('=')[0].strip()
                type_str = "Any"
            else:
                name = param
                type_str = "Any"
            
            parameters.append(Parameter(
                name=name,
                type=TypeInfo(name=type_str)
            ))
        
        return_type = TypeInfo(name=return_type_str.strip()) if return_type_str else None
        
        is_async = 'async def' in source[:source.find('def')+10]
        
        return Signature(
            name=func_name,
            parameters=parameters,
            return_type=return_type,
            is_async=is_async
        )
    
    def _parse_signature_string(self, sig_str: str, func_name: str) -> Optional[Signature]:
        """解析签名字符串"""
        # 简单解析，可以后续增强
        return self._regex_extract_signature(func_name, f"def {sig_str}")
    
    def _infer_function_contract(
        self,
        symbol: CodeSymbol,
        source_code: str
    ) -> Contract:
        """推断函数契约"""
        from ai_codegen.extractor.contract_inferencer import ContractInferencer
        
        if self.contract_inferencer is None:
            self.contract_inferencer = ContractInferencer()
        
        return self.contract_inferencer.infer_contract(symbol, source_code)
    
    def _infer_class_contract(
        self,
        symbol: CodeSymbol,
        source_code: str
    ) -> Contract:
        """推断类契约"""
        contract = Contract()
        
        # 类的不变量可以从文档字符串或代码中提取
        if symbol.docstring:
            if 'invariant' in symbol.docstring.lower():
                contract.invariants = ["类不变量需要在文档中定义"]
        
        return contract
    
    def _extract_class_boundary(
        self,
        symbol: CodeSymbol,
        source_code: str,
        parse_result: Any
    ) -> Boundary:
        """提取类边界"""
        from ai_codegen.extractor.boundary_detector import ModuleBoundaryDetector
        
        detector = ModuleBoundaryDetector()
        return detector.detect_boundary(parse_result)
    
    def _extract_function_dependencies(
        self,
        symbol: CodeSymbol,
        source_code: str,
        parse_result: Any
    ) -> List[Dependency]:
        """提取函数依赖"""
        dependencies = []
        
        # 从导入中提取依赖
        for imp in parse_result.imports:
            if isinstance(imp, dict):
                module = imp.get('module', '')
                if module:
                    dependencies.append(Dependency(
                        target_id=module,
                        relation_type=RelationType.IMPORTS,
                        context="导入模块",
                        line=symbol.location.start_line
                    ))
        
        return dependencies
    
    def _extract_module_path(self, file_path: str) -> str:
        """提取模块路径"""
        path = Path(file_path)
        parts = path.parts
        
        # 找到项目根目录
        try:
            idx = next(i for i, p in enumerate(parts) if p in ('ai_codegen', 'src', 'lib', 'app'))
            module_parts = parts[idx:]
        except StopIteration:
            module_parts = parts
        
        # 移除文件扩展名
        module_parts = list(module_parts)
        if module_parts:
            module_parts[-1] = Path(module_parts[-1]).stem
            if module_parts[-1] == '__init__':
                module_parts.pop()
        
        return '.'.join(module_parts) if module_parts else 'unknown'
    
    def _extract_class_snippet(self, source_code: str, symbol: CodeSymbol) -> str:
        """提取类代码片段"""
        start_line = symbol.location.start_line
        end_line = symbol.location.end_line
        
        lines = source_code.split('\n')
        snippet = '\n'.join(lines[max(0, start_line-1):min(len(lines), end_line)])
        return snippet[:500]
    
    def _extract_function_snippet(self, source_code: str, symbol: CodeSymbol) -> str:
        """提取函数代码片段"""
        start_line = symbol.location.start_line
        end_line = symbol.location.end_line
        
        lines = source_code.split('\n')
        snippet = '\n'.join(lines[max(0, start_line-1):min(len(lines), end_line)])
        return snippet[:500]
    
    def _extract_examples(self, symbol: CodeSymbol, source_code: str) -> List[str]:
        """提取使用示例（从文档字符串）"""
        examples = []
        if symbol.docstring:
            # 简单提取示例代码块
            example_pattern = r'```python\n(.*?)```'
            matches = re.findall(example_pattern, symbol.docstring, re.DOTALL)
            examples.extend(matches)
        return examples
    
    def _infer_purpose(self, description: str, name: str) -> str:
        """推断用途"""
        name_lower = name.lower()
        desc_lower = description.lower()
        
        if 'get' in name_lower or 'fetch' in name_lower or 'retrieve' in name_lower:
            return "获取数据"
        elif 'create' in name_lower or 'add' in name_lower or 'new' in name_lower:
            return "创建数据"
        elif 'update' in name_lower or 'modify' in name_lower or 'edit' in name_lower:
            return "更新数据"
        elif 'delete' in name_lower or 'remove' in name_lower:
            return "删除数据"
        elif 'validate' in name_lower or 'check' in name_lower or 'verify' in name_lower:
            return "验证数据"
        elif 'service' in name_lower or 'service' in desc_lower:
            return "提供业务逻辑服务"
        elif 'controller' in name_lower:
            return "处理请求和响应"
        elif 'model' in name_lower:
            return "数据模型定义"
        else:
            return "执行操作"
    
    def _infer_domain(self, name: str, description: str) -> str:
        """推断领域"""
        text = (name + " " + description).lower()
        
        if 'user' in text:
            return "user_management"
        elif 'auth' in text or 'login' in text or 'token' in text:
            return "authentication"
        elif 'data' in text or 'db' in text or 'database' in text:
            return "data_access"
        elif 'api' in text or 'http' in text or 'rest' in text:
            return "api"
        elif 'cache' in text:
            return "caching"
        elif 'file' in text or 'storage' in text:
            return "storage"
        elif 'email' in text or 'mail' in text:
            return "notification"
        else:
            return "general"
    
    def _extract_tags(self, name: str, description: str) -> List[str]:
        """提取标签"""
        tags = []
        text = (name + " " + description).lower()
        
        if 'async' in text or 'await' in text:
            tags.append("async")
        if not name.startswith('_'):
            tags.append("public")
        if 'service' in name.lower():
            tags.append("service")
        if 'controller' in name.lower():
            tags.append("controller")
        if 'model' in name.lower():
            tags.append("model")
        if 'test' in name.lower():
            tags.append("test")
        
        return tags
    
    def _estimate_complexity(self, symbol: CodeSymbol, source_code: str) -> int:
        """估算复杂度（1-10）"""
        start_line = symbol.location.start_line
        end_line = symbol.location.end_line
        lines = end_line - start_line
        
        if lines < 10:
            return 1
        elif lines < 30:
            return 2
        elif lines < 50:
            return 3
        elif lines < 100:
            return 5
        else:
            return 7
