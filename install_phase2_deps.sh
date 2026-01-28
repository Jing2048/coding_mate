#!/bin/bash
# Phase 2 依赖安装脚本

echo "安装 Phase 2 RAG 系统依赖..."
echo ""

cd "$(dirname "$0")"
source .venv/bin/activate

echo "1. 安装 chromadb..."
pip install chromadb>=0.4.22 -q

echo "2. 安装 sentence-transformers..."
pip install sentence-transformers>=2.2.0 -q

echo ""
echo "✓ 依赖安装完成"
echo ""
echo "验证安装..."
python -c "
import chromadb
from sentence_transformers import SentenceTransformer
print('✓ chromadb:', chromadb.__version__ if hasattr(chromadb, '__version__') else 'installed')
print('✓ sentence-transformers: installed')
print('')
print('Phase 2 RAG 系统依赖已就绪')
"
