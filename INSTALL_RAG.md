# RAG 系统依赖安装指南

## 📦 依赖要求

- `chromadb>=0.4.22` - 向量数据库
- `sentence-transformers>=2.2.0` - 文本嵌入模型

## 🚀 安装方式

### 方式 1: 使用安装脚本（推荐）

```bash
# Bash 版本（增强版，包含错误处理）
./install_rag_deps.sh

# Python 版本（更详细的错误信息）
python install_rag_deps_alternative.py
```

### 方式 2: 使用 pip 直接安装

```bash
# 激活虚拟环境
source .venv/bin/activate

# 标准安装
pip install chromadb sentence-transformers

# 或使用国内镜像（如果网络较慢）
pip install chromadb sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 方式 3: 分步安装（便于定位问题）

```bash
# 激活虚拟环境
source .venv/bin/activate

# 1. 升级 pip
pip install --upgrade pip

# 2. 安装 chromadb
pip install chromadb>=0.4.22

# 3. 安装 sentence-transformers
pip install sentence-transformers>=2.2.0
```

### 方式 4: 使用 requirements.txt

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装所有依赖（包括 RAG）
pip install -r requirements.txt
```

## 🔍 验证安装

安装完成后，验证是否成功：

```bash
python -c "
import chromadb
from sentence_transformers import SentenceTransformer
print('✓ chromadb:', chromadb.__version__ if hasattr(chromadb, '__version__') else 'installed')
print('✓ sentence-transformers: installed')
print('✅ RAG 系统依赖已就绪')
"
```

或测试 RAG 系统：

```bash
python -c "
from ai_codegen.mcp_server.server import AICodeGenServer
server = AICodeGenServer('.')
rag = server.rag_manager
if rag:
    print('✅ RAG 系统可用')
else:
    print('❌ RAG 系统不可用')
"
```

## ⚠️ 常见问题

### 1. 安装超时

**问题**: 安装过程中超时

**解决方案**:
- 使用国内镜像: `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple chromadb sentence-transformers`
- 增加超时时间: `pip install --default-timeout=100 chromadb sentence-transformers`
- 使用 `--no-cache-dir` 避免缓存问题

### 2. chromadb 安装失败

**可能原因**:
- 缺少系统依赖
- 网络问题
- Python 版本不兼容

**解决方案**:
```bash
# 检查 Python 版本（需要 >= 3.8）
python --version

# 尝试安装特定版本
pip install chromadb==0.4.22

# 或使用预编译版本
pip install chromadb --no-build-isolation
```

### 3. sentence-transformers 安装失败

**可能原因**:
- 模型下载失败
- 磁盘空间不足
- 网络问题

**解决方案**:
```bash
# 先安装基础依赖
pip install torch torchvision torchaudio

# 再安装 sentence-transformers
pip install sentence-transformers

# 或指定模型缓存目录
export SENTENCE_TRANSFORMERS_HOME=/path/to/cache
pip install sentence-transformers
```

### 4. 内存不足

**问题**: 安装或运行时内存不足

**解决方案**:
- sentence-transformers 首次运行会下载模型（约 80MB）
- 确保有足够的磁盘空间（至少 500MB）
- 如果内存不足，考虑使用更小的模型

### 5. 权限问题

**问题**: 权限不足

**解决方案**:
```bash
# 使用用户安装
pip install --user chromadb sentence-transformers

# 或确保虚拟环境有写权限
chmod -R u+w .venv
```

## 📝 安装日志

如果安装失败，可以查看详细日志：

```bash
# Bash 脚本会保存日志到 /tmp/
cat /tmp/chromadb_install.log
cat /tmp/sentence_transformers_install.log

# Python 脚本会直接显示错误信息
```

## 🎯 最小化安装（仅核心功能）

如果只需要基本功能，可以只安装 chromadb：

```bash
pip install chromadb
```

但这样会失去语义搜索功能，只能使用 SQLite 降级模式。

## 💡 提示

1. **首次安装较慢**: sentence-transformers 首次安装需要下载模型文件，可能需要几分钟
2. **网络问题**: 如果网络较慢，建议使用国内镜像
3. **虚拟环境**: 确保在虚拟环境中安装，避免污染系统环境
4. **版本兼容**: 确保 Python 版本 >= 3.8

## 📚 相关文档

- [RAG 系统实施文档](docs/implementation/RAG_SYSTEM.md)
- [系统架构文档](docs/design/ARCHITECTURE.md)
- [测试报告](docs/implementation/TEST_REPORT.md)
