"""
代码关系提取器

使用 Tree-sitter AST 遍历提取代码中的各种关系：
- 函数/方法调用 (calls)
- 类继承 (extends)
- 实例化 (instantiates)
- 属性访问 (accesses)

支持多语言，兼容新版 Tree-sitter API。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple
from enum import Enum
from pathlib import Path
import re


class RelationType(Enum):
    """关系类型"""
    IMPORTS = "imports"           # 导入模块
    CALLS = "calls"               # 函数/方法调用
    EXTENDS = "extends"           # 类继承
    IMPLEMENTS = "implements"     # 接口实现
    REFERENCES = "references"     # 类型引用
    ACCESSES = "accesses"         # 属性访问
    INSTANTIATES = "instantiates" # 实例化
    DECORATES = "decorates"       # 装饰器


@dataclass(frozen=True)
class Relationship:
    """代码关系"""
    source: str           # 源（文件:符号 或 文件）
    target: str           # 目标
    rel_type: RelationType
    line: int = 0
    context: str = ""     # 调用上下文
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.rel_type.value,
            "line": self.line,
            "context": self.context,
        }


class RelationshipExtractor:
    """
    代码关系提取器
    
    使用 Tree-sitter AST 遍历提取代码关系。
    """
    
    def __init__(self):
        self._ts_available = False
        self._parsers: Dict[str, Any] = {}
        self._languages: Dict[str, Any] = {}
        self._init_tree_sitter()
    
    def _init_tree_sitter(self):
        """初始化 Tree-sitter"""
        try:
            import tree_sitter
            
            # Python
            try:
                import tree_sitter_python
                self._languages["python"] = tree_sitter.Language(tree_sitter_python.language())
            except ImportError:
                pass
            
            # JavaScript
            try:
                import tree_sitter_javascript
                self._languages["javascript"] = tree_sitter.Language(tree_sitter_javascript.language())
            except ImportError:
                pass
            
            # TypeScript
            try:
                import tree_sitter_typescript
                self._languages["typescript"] = tree_sitter.Language(tree_sitter_typescript.language_typescript())
                self._languages["tsx"] = tree_sitter.Language(tree_sitter_typescript.language_tsx())
            except ImportError:
                pass
            
            # Swift
            try:
                import tree_sitter_swift
                self._languages["swift"] = tree_sitter.Language(tree_sitter_swift.language())
            except ImportError:
                pass
            
            if self._languages:
                self._ts_available = True
                
        except ImportError:
            pass
    
    def extract_relationships(
        self,
        source_code: str,
        file_path: str,
        language: str
    ) -> List[Relationship]:
        """
        从源代码提取所有关系
        """
        if self._ts_available and language in self._languages:
            return self._extract_with_tree_sitter(source_code, file_path, language)
        else:
            return self._extract_with_regex(source_code, file_path, language)
    
    def _extract_with_tree_sitter(
        self,
        source_code: str,
        file_path: str,
        language: str
    ) -> List[Relationship]:
        """使用 Tree-sitter AST 遍历提取关系"""
        import tree_sitter
        
        relationships = []
        lang = self._languages.get(language)
        if not lang:
            return relationships
        
        # 创建 parser
        parser = tree_sitter.Parser()
        parser.language = lang
        
        source_bytes = bytes(source_code, "utf-8")
        tree = parser.parse(source_bytes)
        
        # 构建作用域映射
        scope_stack = []  # [(name, start_line, end_line), ...]
        
        def get_current_scope() -> Optional[str]:
            """获取当前作用域名称"""
            if scope_stack:
                return scope_stack[-1][0]
            return None
        
        def get_node_text(node) -> str:
            """获取节点文本"""
            return source_bytes[node.start_byte:node.end_byte].decode('utf-8')
        
        def visit(node):
            """遍历 AST 节点"""
            node_type = node.type
            line = node.start_point[0] + 1
            
            # === Python ===
            if language == "python":
                # 类定义
                if node_type == "class_definition":
                    class_name = None
                    for child in node.children:
                        if child.type == "identifier":
                            class_name = get_node_text(child)
                            scope_stack.append((class_name, node.start_point[0], node.end_point[0]))
                            break
                    
                    # 提取父类
                    for child in node.children:
                        if child.type == "argument_list":
                            for arg in child.children:
                                if arg.type == "identifier":
                                    parent = get_node_text(arg)
                                    if parent not in ("object", "ABC", "Protocol", "Enum"):
                                        relationships.append(Relationship(
                                            source=f"{file_path}:{class_name}" if class_name else file_path,
                                            target=parent,
                                            rel_type=RelationType.EXTENDS,
                                            line=line
                                        ))
                
                # 函数定义
                elif node_type == "function_definition":
                    for child in node.children:
                        if child.type == "identifier":
                            func_name = get_node_text(child)
                            current_scope = get_current_scope()
                            full_name = f"{current_scope}.{func_name}" if current_scope else func_name
                            scope_stack.append((full_name, node.start_point[0], node.end_point[0]))
                            break
                
                # 函数调用
                elif node_type == "call":
                    func_node = node.child_by_field_name("function")
                    if func_node:
                        call_text = get_node_text(func_node)
                        scope = get_current_scope()
                        source = f"{file_path}:{scope}" if scope else file_path
                        
                        # 判断是否是实例化（首字母大写）
                        target_name = call_text.split('.')[-1]
                        if target_name and target_name[0].isupper():
                            relationships.append(Relationship(
                                source=source,
                                target=call_text,
                                rel_type=RelationType.INSTANTIATES,
                                line=line,
                                context=get_node_text(node)[:60]
                            ))
                        else:
                            relationships.append(Relationship(
                                source=source,
                                target=call_text,
                                rel_type=RelationType.CALLS,
                                line=line,
                                context=get_node_text(node)[:60]
                            ))
                
                # 装饰器
                elif node_type == "decorator":
                    for child in node.children:
                        if child.type in ("identifier", "call"):
                            decorator_name = get_node_text(child).split('(')[0]
                            relationships.append(Relationship(
                                source=file_path,
                                target=decorator_name,
                                rel_type=RelationType.DECORATES,
                                line=line
                            ))
                            break
            
            # === JavaScript/TypeScript ===
            elif language in ("javascript", "typescript", "tsx"):
                if node_type == "class_declaration":
                    class_name = None
                    for child in node.children:
                        if child.type in ("identifier", "type_identifier"):
                            class_name = get_node_text(child)
                            scope_stack.append((class_name, node.start_point[0], node.end_point[0]))
                            break
                    
                    # 提取继承
                    for child in node.children:
                        if child.type == "class_heritage":
                            for heritage in child.children:
                                if heritage.type == "extends_clause":
                                    for h_child in heritage.children:
                                        if h_child.type == "identifier":
                                            parent = get_node_text(h_child)
                                            relationships.append(Relationship(
                                                source=f"{file_path}:{class_name}" if class_name else file_path,
                                                target=parent,
                                                rel_type=RelationType.EXTENDS,
                                                line=line
                                            ))
                
                elif node_type in ("function_declaration", "method_definition", "arrow_function"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = get_node_text(name_node)
                        scope_stack.append((func_name, node.start_point[0], node.end_point[0]))
                
                elif node_type == "call_expression":
                    func_node = node.child_by_field_name("function")
                    if func_node:
                        call_text = get_node_text(func_node)
                        scope = get_current_scope()
                        source = f"{file_path}:{scope}" if scope else file_path
                        
                        target_name = call_text.split('.')[-1]
                        if target_name and target_name[0].isupper():
                            relationships.append(Relationship(
                                source=source,
                                target=call_text,
                                rel_type=RelationType.INSTANTIATES,
                                line=line
                            ))
                        else:
                            relationships.append(Relationship(
                                source=source,
                                target=call_text,
                                rel_type=RelationType.CALLS,
                                line=line
                            ))
            
            # === Swift ===
            elif language == "swift":
                # 类/结构体定义
                if node_type == "class_declaration":
                    class_name = None
                    is_struct = False
                    
                    for child in node.children:
                        if child.type == "struct":
                            is_struct = True
                        elif child.type == "type_identifier":
                            class_name = get_node_text(child)
                            scope_stack.append((class_name, node.start_point[0], node.end_point[0]))
                        elif child.type == "inheritance_specifier":
                            for inherit in child.children:
                                if inherit.type == "user_type":
                                    parent = get_node_text(inherit)
                                    if class_name:
                                        relationships.append(Relationship(
                                            source=f"{file_path}:{class_name}",
                                            target=parent,
                                            rel_type=RelationType.EXTENDS,
                                            line=line
                                        ))
                
                # 函数定义
                elif node_type == "function_declaration":
                    func_name = None
                    for child in node.children:
                        if child.type == "simple_identifier":
                            func_name = get_node_text(child)
                            current_scope = get_current_scope()
                            full_name = f"{current_scope}.{func_name}" if current_scope else func_name
                            scope_stack.append((full_name, node.start_point[0], node.end_point[0]))
                            break
                        # 方法修饰符 (attribute)
                        elif child.type == "modifiers":
                            for mod in child.children:
                                if mod.type == "attribute":
                                    attr_name = get_node_text(mod).lstrip('@')
                                    relationships.append(Relationship(
                                        source=file_path,
                                        target=attr_name,
                                        rel_type=RelationType.DECORATES,
                                        line=line
                                    ))
                
                # 函数调用
                elif node_type == "call_expression":
                    # 获取被调用的函数/方法
                    for child in node.children:
                        if child.type in ("simple_identifier", "navigation_expression"):
                            call_text = get_node_text(child)
                            scope = get_current_scope()
                            source = f"{file_path}:{scope}" if scope else file_path
                            
                            target_name = call_text.split('.')[-1]
                            if target_name and target_name[0].isupper():
                                relationships.append(Relationship(
                                    source=source,
                                    target=call_text,
                                    rel_type=RelationType.INSTANTIATES,
                                    line=line
                                ))
                            else:
                                relationships.append(Relationship(
                                    source=source,
                                    target=call_text,
                                    rel_type=RelationType.CALLS,
                                    line=line
                                ))
                            break
            
            # 递归访问子节点
            for child in node.children:
                visit(child)
            
            # 退出作用域
            while scope_stack and node.end_point[0] >= scope_stack[-1][2]:
                scope_stack.pop()
        
        visit(tree.root_node)
        return relationships
    
    def _extract_with_regex(
        self,
        source_code: str,
        file_path: str,
        language: str
    ) -> List[Relationship]:
        """使用正则表达式提取关系（后备方案）"""
        relationships = []
        lines = source_code.split('\n')
        
        current_class = None
        current_function = None
        indent_stack = [(0, None)]  # (indent_level, scope_name)
        
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            
            indent = len(line) - len(line.lstrip())
            stripped = line.strip()
            
            # 更新作用域
            while indent_stack and indent <= indent_stack[-1][0] and len(indent_stack) > 1:
                indent_stack.pop()
            
            # Python 风格
            if language == "python":
                # 类定义
                class_match = re.match(r'class\s+(\w+)(?:\(([^)]+)\))?:', stripped)
                if class_match:
                    current_class = class_match.group(1)
                    indent_stack.append((indent, current_class))
                    
                    parents = class_match.group(2)
                    if parents:
                        for parent in parents.split(','):
                            parent = parent.strip().split('[')[0]  # 处理泛型
                            if parent and parent not in ('object', 'ABC', 'Protocol', 'Enum'):
                                relationships.append(Relationship(
                                    source=f"{file_path}:{current_class}",
                                    target=parent,
                                    rel_type=RelationType.EXTENDS,
                                    line=i
                                ))
                    continue
                
                # 函数定义
                func_match = re.match(r'(?:async\s+)?def\s+(\w+)\s*\(', stripped)
                if func_match:
                    func_name = func_match.group(1)
                    current_scope = indent_stack[-1][1] if indent_stack else None
                    full_name = f"{current_scope}.{func_name}" if current_scope else func_name
                    indent_stack.append((indent, full_name))
                    current_function = full_name
                    continue
                
                # 函数调用
                call_pattern = r'(\w+(?:\.\w+)*)\s*\('
                for match in re.finditer(call_pattern, stripped):
                    call = match.group(1)
                    # 过滤关键字和内置函数
                    if call.split('.')[0] in ('if', 'for', 'while', 'def', 'class', 'return', 
                                                'yield', 'print', 'len', 'str', 'int', 'list', 
                                                'dict', 'set', 'tuple', 'range', 'enumerate',
                                                'isinstance', 'hasattr', 'getattr', 'setattr',
                                                'super', 'type', 'open', 'with', 'as', 'not',
                                                'and', 'or', 'in', 'is', 'True', 'False', 'None'):
                        continue
                    
                    scope = indent_stack[-1][1] if len(indent_stack) > 1 else None
                    source = f"{file_path}:{scope}" if scope else file_path
                    
                    # 判断是否是实例化
                    target_name = call.split('.')[-1]
                    if target_name and target_name[0].isupper():
                        relationships.append(Relationship(
                            source=source,
                            target=call,
                            rel_type=RelationType.INSTANTIATES,
                            line=i,
                            context=stripped[:50]
                        ))
                    else:
                        relationships.append(Relationship(
                            source=source,
                            target=call,
                            rel_type=RelationType.CALLS,
                            line=i,
                            context=stripped[:50]
                        ))
            
            # Swift 风格
            elif language == "swift":
                # 类/结构体定义
                class_match = re.match(r'(?:class|struct)\s+(\w+)(?:\s*:\s*([^{]+))?', stripped)
                if class_match:
                    current_class = class_match.group(1)
                    indent_stack.append((indent, current_class))
                    
                    parents = class_match.group(2)
                    if parents:
                        for parent in parents.split(','):
                            parent = parent.strip()
                            if parent:
                                relationships.append(Relationship(
                                    source=f"{file_path}:{current_class}",
                                    target=parent,
                                    rel_type=RelationType.EXTENDS,
                                    line=i
                                ))
                    continue
                
                # 函数定义
                func_match = re.match(r'func\s+(\w+)\s*[<(]', stripped)
                if func_match:
                    func_name = func_match.group(1)
                    current_scope = indent_stack[-1][1] if indent_stack else None
                    full_name = f"{current_scope}.{func_name}" if current_scope else func_name
                    indent_stack.append((indent, full_name))
                    continue
                
                # 函数调用
                call_pattern = r'(\w+(?:\.\w+)*)\s*\('
                for match in re.finditer(call_pattern, stripped):
                    call = match.group(1)
                    if call.split('.')[0] in ('if', 'for', 'while', 'func', 'class', 'struct',
                                               'return', 'guard', 'switch', 'case', 'let', 'var'):
                        continue
                    
                    scope = indent_stack[-1][1] if len(indent_stack) > 1 else None
                    source = f"{file_path}:{scope}" if scope else file_path
                    
                    target_name = call.split('.')[-1]
                    if target_name and target_name[0].isupper():
                        relationships.append(Relationship(
                            source=source,
                            target=call,
                            rel_type=RelationType.INSTANTIATES,
                            line=i
                        ))
                    else:
                        relationships.append(Relationship(
                            source=source,
                            target=call,
                            rel_type=RelationType.CALLS,
                            line=i
                        ))
        
        return relationships


def extract_all_relationships(
    files: Dict[str, str],
    language_map: Dict[str, str]
) -> List[Relationship]:
    """
    从多个文件提取所有关系
    """
    extractor = RelationshipExtractor()
    all_relationships = []
    
    for file_path, source_code in files.items():
        language = language_map.get(file_path, "python")
        relationships = extractor.extract_relationships(source_code, file_path, language)
        all_relationships.extend(relationships)
    
    return all_relationships
