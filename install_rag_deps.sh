#!/bin/bash
# RAG 系统依赖安装脚本（增强版）

set -e  # 遇到错误立即退出

echo "=========================================="
echo "RAG 系统依赖安装"
echo "=========================================="
echo ""

# 检查虚拟环境
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "❌ 错误: 未找到虚拟环境 .venv"
    echo "   请先创建虚拟环境: python -m venv .venv"
    exit 1
fi

# 激活虚拟环境
source .venv/bin/activate

# 检查 Python 版本
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "Python 版本: $PYTHON_VERSION"
echo ""

# 升级 pip
echo "1. 升级 pip..."
pip install --upgrade pip --quiet || {
    echo "⚠️  pip 升级失败，继续安装..."
}

# 安装依赖（分步安装，便于定位问题）
echo ""
echo "2. 安装基础依赖..."

# 先安装一些可能需要的系统依赖
pip install --upgrade setuptools wheel --quiet || true

echo ""
echo "3. 安装 chromadb..."
echo "   这可能需要几分钟，请耐心等待..."

# 尝试多种安装方式
if ! pip install chromadb>=0.4.22 --no-cache-dir 2>&1 | tee /tmp/chromadb_install.log; then
    echo ""
    echo "⚠️  标准安装失败，尝试使用备用源..."
    if ! pip install chromadb>=0.4.22 -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir 2>&1 | tee /tmp/chromadb_install.log; then
        echo ""
        echo "❌ chromadb 安装失败"
        echo "   错误日志: /tmp/chromadb_install.log"
        echo ""
        echo "   建议尝试:"
        echo "   1. 检查网络连接"
        echo "   2. 手动安装: pip install chromadb"
        echo "   3. 使用国内镜像: pip install chromadb -i https://pypi.tuna.tsinghua.edu.cn/simple"
        exit 1
    fi
fi

echo ""
echo "4. 安装 sentence-transformers..."
echo "   这可能需要几分钟（需要下载模型文件）..."

if ! pip install sentence-transformers>=2.2.0 --no-cache-dir 2>&1 | tee /tmp/sentence_transformers_install.log; then
    echo ""
    echo "⚠️  标准安装失败，尝试使用备用源..."
    if ! pip install sentence-transformers>=2.2.0 -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir 2>&1 | tee /tmp/sentence_transformers_install.log; then
        echo ""
        echo "❌ sentence-transformers 安装失败"
        echo "   错误日志: /tmp/sentence_transformers_install.log"
        echo ""
        echo "   建议尝试:"
        echo "   1. 检查网络连接"
        echo "   2. 手动安装: pip install sentence-transformers"
        echo "   3. 使用国内镜像: pip install sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "验证安装..."
echo "=========================================="

# 验证安装
python -c "
import sys
errors = []

try:
    import chromadb
    version = chromadb.__version__ if hasattr(chromadb, '__version__') else 'installed'
    print('✓ chromadb:', version)
except ImportError as e:
    errors.append(f'chromadb: {e}')
    print('❌ chromadb 导入失败')

try:
    from sentence_transformers import SentenceTransformer
    print('✓ sentence-transformers: installed')
except ImportError as e:
    errors.append(f'sentence-transformers: {e}')
    print('❌ sentence-transformers 导入失败')

if errors:
    print('')
    print('安装验证失败:')
    for error in errors:
        print(f'  - {error}')
    sys.exit(1)
else:
    print('')
    print('✅ RAG 系统依赖已就绪')
"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ 安装成功！"
    echo "=========================================="
    echo ""
    echo "下一步:"
    echo "  1. 测试 RAG 系统: python -c \"from ai_codegen.rag import RAGManager; print('RAG 系统可用')\""
    echo "  2. 同步数据: 使用 MCP 工具 sync_rag"
else
    echo ""
    echo "=========================================="
    echo "❌ 验证失败"
    echo "=========================================="
    exit 1
fi
