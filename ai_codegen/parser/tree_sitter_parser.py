"""
Tree-sitter 代码解析器

使用 Tree-sitter 解析多种编程语言的源代码，生成 AST 并提取结构化信息。
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import json

# Tree-sitter 语言支持
SUPPORTED_LANGUAGES = {
    ".py": "python",
    ".js": "javascript", 
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".rb": "ruby",
}


class NodeType(Enum):
    """AST 节点类型"""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    TYPE = "type"
    VARIABLE = "variable"
    IMPORT = "import"
    EXPORT = "export"
    DECORATOR = "decorator"
    COMMENT = "comment"


@dataclass
class CodeLocation:
    """代码位置信息"""
    file_path: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_column": self.start_column,
            "end_column": self.end_column,
        }


@dataclass
class CodeSymbol:
    """代码符号"""
    name: str
    node_type: NodeType
    location: CodeLocation
    docstring: Optional[str] = None
    signature: Optional[str] = None
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    annotations: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "node_type": self.node_type.value,
            "location": self.location.to_dict(),
            "docstring": self.docstring,
            "signature": self.signature,
            "parent": self.parent,
            "children": self.children,
            "annotations": self.annotations,
        }


@dataclass
class ParseResult:
    """解析结果"""
    file_path: str
    language: str
    symbols: List[CodeSymbol]
    imports: List[Dict[str, Any]]
    exports: List[str]
    raw_ast: Optional[Any] = None
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "symbols": [s.to_dict() for s in self.symbols],
            "imports": self.imports,
            "exports": self.exports,
            "errors": self.errors,
        }


class TreeSitterParser:
    """
    基于 Tree-sitter 的代码解析器
    
    支持多种编程语言的 AST 解析和符号提取。
    """
    
    def __init__(self, languages: Optional[List[str]] = None):
        """
        初始化解析器
        
        Args:
            languages: 要支持的语言列表，默认支持所有已配置语言
        """
        self._parsers: Dict[str, Any] = {}
        self._languages = languages or list(set(SUPPORTED_LANGUAGES.values()))
        self._initialized = False
        
    def _init_parsers(self):
        """延迟初始化 tree-sitter 解析器"""
        if self._initialized:
            return
            
        try:
            from tree_sitter import Language, Parser
            
            # 尝试初始化 Python 解析器
            try:
                import tree_sitter_python
                if "python" in self._languages:
                    parser = Parser()
                    parser.language = Language(tree_sitter_python.language())
                    self._parsers["python"] = parser
            except (ImportError, AttributeError) as e:
                print(f"Python parser not available: {e}")
            
            # 尝试初始化 JavaScript 解析器
            try:
                import tree_sitter_javascript
                if "javascript" in self._languages:
                    parser = Parser()
                    parser.language = Language(tree_sitter_javascript.language())
                    self._parsers["javascript"] = parser
            except (ImportError, AttributeError) as e:
                print(f"JavaScript parser not available: {e}")
            
            # 尝试初始化 TypeScript 解析器
            try:
                import tree_sitter_typescript
                if "typescript" in self._languages:
                    parser = Parser()
                    # tree_sitter_typescript 使用 language_typescript 而不是 language
                    parser.language = Language(tree_sitter_typescript.language_typescript())
                    self._parsers["typescript"] = parser
                if "tsx" in self._languages:
                    parser = Parser()
                    parser.language = Language(tree_sitter_typescript.language_tsx())
                    self._parsers["tsx"] = parser
            except (ImportError, AttributeError) as e:
                print(f"TypeScript parser not available: {e}")
                    
            self._initialized = True
        except ImportError as e:
            # 如果 tree-sitter 不可用，使用备用解析
            print(f"Tree-sitter not available, using fallback parser: {e}")
            self._initialized = True
    
    def get_language(self, file_path: str) -> Optional[str]:
        """根据文件扩展名获取语言"""
        ext = Path(file_path).suffix.lower()
        return SUPPORTED_LANGUAGES.get(ext)
    
    def parse_file(self, file_path: str) -> ParseResult:
        """
        解析单个文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            ParseResult: 解析结果
        """
        self._init_parsers()
        
        file_path = str(Path(file_path).resolve())
        language = self.get_language(file_path)
        
        if not language:
            return ParseResult(
                file_path=file_path,
                language="unknown",
                symbols=[],
                imports=[],
                exports=[],
                errors=[f"Unsupported file type: {file_path}"]
            )
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
        except Exception as e:
            return ParseResult(
                file_path=file_path,
                language=language,
                symbols=[],
                imports=[],
                exports=[],
                errors=[f"Failed to read file: {e}"]
            )
        
        return self.parse_source(source_code, file_path, language)
    
    def parse_source(
        self, 
        source_code: str, 
        file_path: str,
        language: str
    ) -> ParseResult:
        """
        解析源代码字符串
        
        Args:
            source_code: 源代码
            file_path: 文件路径（用于位置信息）
            language: 编程语言
            
        Returns:
            ParseResult: 解析结果
        """
        self._init_parsers()
        
        if language in self._parsers:
            return self._parse_with_tree_sitter(source_code, file_path, language)
        else:
            return self._parse_with_fallback(source_code, file_path, language)
    
    def _parse_with_tree_sitter(
        self,
        source_code: str,
        file_path: str,
        language: str
    ) -> ParseResult:
        """使用 tree-sitter 解析"""
        parser = self._parsers[language]
        source_bytes = bytes(source_code, "utf-8")
        tree = parser.parse(source_bytes)
        
        symbols = []
        imports = []
        exports = []
        errors = []
        
        # 辅助函数：从字节偏移获取文本
        def get_text(node) -> str:
            return source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        
        # 遍历 AST 提取符号
        def traverse(node, parent_name=None):
            node_type = node.type
            
            # Python 特定处理
            if language == "python":
                if node_type == "function_definition":
                    symbol = self._extract_python_function(node, file_path, source_bytes, parent_name)
                    if symbol:
                        symbols.append(symbol)
                        for child in node.children:
                            traverse(child, symbol.name)
                    return
                    
                elif node_type == "class_definition":
                    symbol = self._extract_python_class(node, file_path, source_bytes)
                    if symbol:
                        symbols.append(symbol)
                        for child in node.children:
                            traverse(child, symbol.name)
                    return
                    
                elif node_type == "import_statement":
                    imp = self._extract_python_import(node, source_bytes)
                    if imp:
                        imports.append(imp)
                        
                elif node_type == "import_from_statement":
                    imp = self._extract_python_from_import(node, source_bytes)
                    if imp:
                        imports.append(imp)
            
            # JavaScript/TypeScript 特定处理
            elif language in ("javascript", "typescript", "tsx"):
                if node_type in ("function_declaration", "arrow_function", "function"):
                    symbol = self._extract_js_function(node, file_path, source_bytes, parent_name)
                    if symbol:
                        symbols.append(symbol)
                        
                elif node_type == "class_declaration":
                    symbol = self._extract_js_class(node, file_path, source_bytes)
                    if symbol:
                        symbols.append(symbol)
                        for child in node.children:
                            traverse(child, symbol.name)
                    return
                    
                elif node_type == "interface_declaration":
                    symbol = self._extract_ts_interface(node, file_path, source_bytes)
                    if symbol:
                        symbols.append(symbol)
                        
                elif node_type == "import_statement":
                    imp = self._extract_js_import(node, source_bytes)
                    if imp:
                        imports.append(imp)
                        
                elif node_type == "export_statement":
                    exp = self._extract_js_export(node, source_bytes)
                    if exp:
                        exports.extend(exp)
            
            # 递归遍历子节点
            for child in node.children:
                traverse(child, parent_name)
        
        traverse(tree.root_node)
        
        # 检查语法错误
        if tree.root_node.has_error:
            errors.append("Source code contains syntax errors")
        
        return ParseResult(
            file_path=file_path,
            language=language,
            symbols=symbols,
            imports=imports,
            exports=exports,
            raw_ast=tree,
            errors=errors
        )
    
    def _extract_python_function(
        self, 
        node, 
        file_path: str,
        source_bytes: bytes,
        parent_name: Optional[str]
    ) -> Optional[CodeSymbol]:
        """提取 Python 函数信息"""
        name_node = None
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break
        
        if not name_node:
            return None
        
        # 使用字节切片然后解码
        name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
        
        # 提取 docstring
        docstring = None
        body = None
        for child in node.children:
            if child.type == "block":
                body = child
                break
        
        if body and body.children:
            first_stmt = body.children[0]
            if first_stmt.type == "expression_statement":
                expr = first_stmt.children[0] if first_stmt.children else None
                if expr and expr.type == "string":
                    docstring = source_bytes[expr.start_byte:expr.end_byte].decode("utf-8").strip('\"\'')
        
        # 提取函数签名
        full_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        signature = full_text.split(":")[0] + ":"
        if "\n" in signature:
            signature = signature.split("\n")[0]
        
        return CodeSymbol(
            name=name,
            node_type=NodeType.METHOD if parent_name else NodeType.FUNCTION,
            location=CodeLocation(
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1],
                end_column=node.end_point[1],
            ),
            docstring=docstring,
            signature=signature.strip(),
            parent=parent_name,
        )
    
    def _extract_python_class(
        self,
        node,
        file_path: str,
        source_bytes: bytes
    ) -> Optional[CodeSymbol]:
        """提取 Python 类信息"""
        name_node = None
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break
        
        if not name_node:
            return None
        
        name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
        
        # 提取 docstring
        docstring = None
        body = None
        for child in node.children:
            if child.type == "block":
                body = child
                break
        
        if body and body.children:
            first_stmt = body.children[0]
            if first_stmt.type == "expression_statement":
                expr = first_stmt.children[0] if first_stmt.children else None
                if expr and expr.type == "string":
                    docstring = source_bytes[expr.start_byte:expr.end_byte].decode("utf-8").strip('\"\'')
        
        # 提取类签名
        full_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        colon_pos = full_text.find(":")
        if colon_pos > 0:
            signature = full_text[:colon_pos + 1]
        else:
            signature = f"class {name}:"
        
        return CodeSymbol(
            name=name,
            node_type=NodeType.CLASS,
            location=CodeLocation(
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1],
                end_column=node.end_point[1],
            ),
            docstring=docstring,
            signature=signature.strip(),
        )
    
    def _extract_python_import(self, node, source_bytes: bytes) -> Dict[str, Any]:
        """提取 Python import 语句"""
        text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        module = text.replace("import ", "").strip()
        return {
            "type": "import",
            "module": module,
            "names": [module.split(".")[0]],
            "raw": text,
        }
    
    def _extract_python_from_import(self, node, source_bytes: bytes) -> Dict[str, Any]:
        """提取 Python from ... import 语句"""
        text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        parts = text.replace("from ", "").split(" import ")
        module = parts[0].strip() if parts else ""
        names = [n.strip() for n in parts[1].split(",")] if len(parts) > 1 else []
        return {
            "type": "from_import",
            "module": module,
            "names": names,
            "raw": text,
        }
    
    def _extract_js_function(
        self,
        node,
        file_path: str,
        source_bytes: bytes,
        parent_name: Optional[str]
    ) -> Optional[CodeSymbol]:
        """提取 JavaScript/TypeScript 函数信息"""
        name = None
        for child in node.children:
            if child.type == "identifier":
                name = source_bytes[child.start_byte:child.end_byte].decode("utf-8")
                break
        
        if not name:
            return None
        
        # 提取函数签名
        full_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        body_start = full_text.find("{")
        if body_start > 0:
            signature = full_text[:body_start].strip()
        else:
            signature = full_text[:100]
        
        return CodeSymbol(
            name=name,
            node_type=NodeType.METHOD if parent_name else NodeType.FUNCTION,
            location=CodeLocation(
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1],
                end_column=node.end_point[1],
            ),
            signature=signature,
            parent=parent_name,
        )
    
    def _extract_js_class(
        self,
        node,
        file_path: str,
        source_bytes: bytes
    ) -> Optional[CodeSymbol]:
        """提取 JavaScript/TypeScript 类信息"""
        name = None
        for child in node.children:
            if child.type == "identifier":
                name = source_bytes[child.start_byte:child.end_byte].decode("utf-8")
                break
        
        if not name:
            return None
        
        full_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        body_start = full_text.find("{")
        if body_start > 0:
            signature = full_text[:body_start].strip()
        else:
            signature = f"class {name}"
        
        return CodeSymbol(
            name=name,
            node_type=NodeType.CLASS,
            location=CodeLocation(
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1],
                end_column=node.end_point[1],
            ),
            signature=signature,
        )
    
    def _extract_ts_interface(
        self,
        node,
        file_path: str,
        source_bytes: bytes
    ) -> Optional[CodeSymbol]:
        """提取 TypeScript 接口信息"""
        name = None
        for child in node.children:
            if child.type == "type_identifier":
                name = source_bytes[child.start_byte:child.end_byte].decode("utf-8")
                break
        
        if not name:
            return None
        
        full_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        body_start = full_text.find("{")
        if body_start > 0:
            signature = full_text[:body_start].strip()
        else:
            signature = f"interface {name}"
        
        return CodeSymbol(
            name=name,
            node_type=NodeType.INTERFACE,
            location=CodeLocation(
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1],
                end_column=node.end_point[1],
            ),
            signature=signature,
        )
    
    def _extract_js_import(self, node, source_bytes: bytes) -> Dict[str, Any]:
        """提取 JavaScript/TypeScript import 语句"""
        text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        return {
            "type": "import",
            "raw": text,
        }
    
    def _extract_js_export(self, node, source_bytes: bytes) -> List[str]:
        """提取 JavaScript/TypeScript export 语句"""
        text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        exports = []
        
        if "export default" in text:
            exports.append("default")
        elif "export " in text:
            # 简化提取
            exports.append(text)
        
        return exports
    
    def _parse_with_fallback(
        self,
        source_code: str,
        file_path: str,
        language: str
    ) -> ParseResult:
        """使用正则表达式的备用解析器"""
        import re
        
        symbols = []
        imports = []
        exports = []
        lines = source_code.split("\n")
        
        if language == "python":
            # 简单的 Python 解析
            class_pattern = re.compile(r"^class\s+(\w+)")
            func_pattern = re.compile(r"^(\s*)def\s+(\w+)")
            import_pattern = re.compile(r"^(?:from\s+(\S+)\s+)?import\s+(.+)")
            
            current_class = None
            
            for i, line in enumerate(lines):
                # 检查类定义
                class_match = class_pattern.match(line)
                if class_match:
                    current_class = class_match.group(1)
                    symbols.append(CodeSymbol(
                        name=current_class,
                        node_type=NodeType.CLASS,
                        location=CodeLocation(file_path, i + 1, i + 1),
                        signature=line.strip(),
                    ))
                    continue
                
                # 检查函数定义
                func_match = func_pattern.match(line)
                if func_match:
                    indent = len(func_match.group(1))
                    name = func_match.group(2)
                    parent = current_class if indent > 0 else None
                    
                    if indent == 0:
                        current_class = None
                    
                    symbols.append(CodeSymbol(
                        name=name,
                        node_type=NodeType.METHOD if parent else NodeType.FUNCTION,
                        location=CodeLocation(file_path, i + 1, i + 1),
                        signature=line.strip(),
                        parent=parent,
                    ))
                    continue
                
                # 检查导入
                import_match = import_pattern.match(line)
                if import_match:
                    module = import_match.group(1) or import_match.group(2)
                    imports.append({
                        "type": "import",
                        "module": module,
                        "raw": line.strip(),
                    })
        
        return ParseResult(
            file_path=file_path,
            language=language,
            symbols=symbols,
            imports=imports,
            exports=exports,
        )
    
    def parse_directory(
        self,
        directory: str,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, ParseResult]:
        """
        解析目录中的所有源文件
        
        Args:
            directory: 目录路径
            recursive: 是否递归解析子目录
            exclude_patterns: 排除的文件/目录模式
            
        Returns:
            Dict[str, ParseResult]: 文件路径到解析结果的映射
        """
        import fnmatch
        
        exclude_patterns = exclude_patterns or [
            "node_modules",
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "dist",
            "build",
            "*.min.js",
        ]
        
        results = {}
        directory = Path(directory).resolve()
        
        def should_exclude(path: Path) -> bool:
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(path.name, pattern):
                    return True
                if fnmatch.fnmatch(str(path), f"*/{pattern}/*"):
                    return True
            return False
        
        def process_dir(dir_path: Path):
            for item in dir_path.iterdir():
                if should_exclude(item):
                    continue
                    
                if item.is_file():
                    if self.get_language(str(item)):
                        results[str(item)] = self.parse_file(str(item))
                        
                elif item.is_dir() and recursive:
                    process_dir(item)
        
        process_dir(directory)
        return results
