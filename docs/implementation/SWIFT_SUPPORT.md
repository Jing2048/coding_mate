# Swift 语言支持实现文档

## 概述

本文档描述了为 AI CodeGen MCP Server 添加 Swift 语言专项支持的实现细节。Swift 支持使得系统能够更好地理解和分析 iOS/macOS 代码，提供更准确的代码生成建议。

## 实现内容

### 1. 代码解析器支持 (`ai_codegen/parser/tree_sitter_parser.py`)

#### 1.1 语言注册
- 在 `SUPPORTED_LANGUAGES` 字典中添加了 `.swift: "swift"` 映射
- 支持识别 `.swift` 文件扩展名

#### 1.2 解析器初始化
- 在 `_init_parsers()` 方法中添加了 Swift 解析器初始化逻辑
- 使用 `tree_sitter_swift` 包进行 AST 解析
- 支持延迟初始化，如果包不可用会优雅降级

#### 1.3 Swift 特定提取函数

实现了以下 Swift 语言特性的提取函数：

- **`_extract_swift_class()`**: 提取类定义
  - 支持类继承和协议遵循
  - 提取类签名和位置信息

- **`_extract_swift_struct()`**: 提取结构体定义
  - Swift 结构体视为类类型（NodeType.CLASS）
  - 支持协议遵循

- **`_extract_swift_protocol()`**: 提取协议定义
  - 协议视为接口类型（NodeType.INTERFACE）
  - 提取协议签名

- **`_extract_swift_enum()`**: 提取枚举定义
  - 枚举视为类型（NodeType.TYPE）
  - 支持关联值枚举

- **`_extract_swift_extension()`**: 提取扩展定义
  - 扩展视为类类型
  - 提取扩展的目标类型

- **`_extract_swift_function()`**: 提取函数/方法定义
  - 区分函数和方法（基于是否有父类）
  - 提取函数签名（包含参数和返回类型）

- **`_extract_swift_import()`**: 提取导入语句
  - 支持 `import ModuleName` 和 `import ModuleName.Submodule` 格式

#### 1.4 AST 遍历逻辑

在 `_parse_with_tree_sitter()` 的 `traverse()` 函数中添加了 Swift 特定的节点处理：

- `class_declaration`: 类定义
- `struct_declaration`: 结构体定义
- `protocol_declaration`: 协议定义
- `enum_declaration`: 枚举定义
- `extension_declaration`: 扩展定义
- `function_declaration`: 函数/方法定义
- `import_declaration`: 导入语句

### 2. 类型检查器支持 (`ai_codegen/verifier/type_checker.py`)

#### 2.1 工具检测
- 在 `_check_available_tools()` 中添加了 `swiftc` 编译器检测
- 检查系统是否安装了 Swift 编译器

#### 2.2 Swift 类型检查
- 实现了 `_check_swift()` 方法
- 使用 `swiftc -typecheck` 进行类型检查
- 解析编译器输出，提取错误和警告信息

#### 2.3 基本类型检查
- 实现了 `_basic_swift_type_check()` 作为后备方案
- 检查函数是否缺少显式返回类型
- 提供改进建议

### 3. 语法检查器支持 (`ai_codegen/verifier/syntax_checker.py`)

#### 3.1 Swift 语法检查
- 在 `_basic_syntax_check()` 中添加了 Swift 支持
- 使用括号匹配检查作为基本语法验证
- Tree-sitter 解析器会自动进行语法检查

### 4. 服务器配置更新 (`ai_codegen/mcp_server/server.py`)

#### 4.1 语言映射更新
- 在 `tool_index()` 方法中添加了 Swift 语言映射
- 在 `tool_search()` 方法中添加了 Swift 语言映射
- 确保 Swift 文件能被正确识别和处理

### 5. 验证器配置 (`ai_codegen/verifier/verifier.py`)

#### 5.1 语言检测
- 在 `_detect_language()` 方法中添加了 `.swift: "swift"` 映射
- 支持自动检测 Swift 文件

#### 5.2 语言配置
- 在 `language_config` 中添加了 Swift 配置：
  ```python
  "swift": {
      "syntax_tool": "tree-sitter",
      "type_tool": "swiftc",
      "test_framework": "xctest",
  }
  ```

## 依赖要求

### Python 包
- `tree-sitter-swift>=0.0.1` (已在 requirements.txt 中)

### 系统工具（可选）
- `swiftc`: Swift 编译器（用于类型检查）
  - macOS: 通常已预装
  - Linux: 需要安装 Swift 工具链

## 使用示例

### 1. 索引 Swift 代码

```python
from ai_codegen.mcp_server.server import AICodeGenServer
import asyncio

async def main():
    server = AICodeGenServer(".")
    
    # 索引 Swift 文件
    result = await server.tool_index(
        paths=["ios_app/"],
        extensions=[".swift"],
        force=False
    )
    print(f"索引了 {result['indexed']} 个 Swift 文件")

asyncio.run(main())
```

### 2. 提取 Swift 接口

```python
async def extract_swift_interfaces():
    server = AICodeGenServer(".")
    
    result = await server.tool_extract_interfaces(
        paths=["ios_app/Models/User.swift"],
        force=True
    )
    print(f"提取了 {result['extracted']} 个接口")

asyncio.run(extract_swift_interfaces())
```

### 3. 验证 Swift 代码

```python
async def verify_swift_code():
    server = AICodeGenServer(".")
    
    result = await server.tool_verify(
        file="ios_app/Models/User.swift",
        checks=["syntax", "type"]
    )
    print(f"语法检查: {result['syntax']['valid']}")
    print(f"类型检查: {result['type']['valid']}")

asyncio.run(verify_swift_code())
```

## Swift 特性支持

### 已支持的特性

1. **类 (Class)**: 完整支持，包括继承和协议遵循
2. **结构体 (Struct)**: 完整支持
3. **协议 (Protocol)**: 完整支持，视为接口类型
4. **枚举 (Enum)**: 完整支持
5. **扩展 (Extension)**: 完整支持
6. **函数/方法**: 完整支持，包括参数和返回类型
7. **导入语句**: 完整支持

### 未来可扩展的特性

1. **泛型 (Generics)**: 可以增强提取函数以更好地处理泛型
2. **属性包装器 (Property Wrappers)**: 如 `@Published`, `@State` 等
3. **访问控制**: `private`, `public`, `internal` 等修饰符
4. **异步/等待**: `async/await` 语法支持
5. **Result Builder**: SwiftUI 的视图构建器

## 测试

创建了测试文件 `test_swift_example.swift`，包含：

- 结构体定义 (`User`)
- 协议定义 (`UserServiceProtocol`)
- 类实现 (`UserService`)
- 视图模型 (`UserViewModel`)
- 枚举 (`UserStatus`)
- 扩展 (`extension User`)

可以使用此文件验证解析和提取功能。

## 注意事项

1. **Tree-sitter Swift 解析器**: 需要确保 `tree-sitter-swift` 包已正确安装
2. **Swift 编译器**: 类型检查功能需要系统安装 Swift 编译器
3. **macOS 优先**: Swift 在 macOS 上支持最好，Linux 支持可能有限
4. **Xcode 项目**: 对于复杂的 Xcode 项目，可能需要额外的配置

## 相关文件

- `ai_codegen/parser/tree_sitter_parser.py`: 核心解析器实现
- `ai_codegen/verifier/type_checker.py`: 类型检查器
- `ai_codegen/verifier/syntax_checker.py`: 语法检查器
- `ai_codegen/mcp_server/server.py`: MCP 服务器
- `ai_codegen/verifier/verifier.py`: 验证器主类
- `requirements.txt`: Python 依赖列表

## 总结

Swift 语言支持已完整实现，包括：

✅ 代码解析和符号提取
✅ 接口提取（类、结构体、协议、枚举、扩展）
✅ 语法检查
✅ 类型检查（使用 swiftc）
✅ 语言检测和配置

系统现在可以更好地理解和分析 iOS/macOS Swift 代码，为 AI 编码助手提供更准确的上下文和建议。
