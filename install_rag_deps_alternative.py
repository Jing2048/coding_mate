#!/usr/bin/env python3
"""
RAG 依赖安装脚本（Python 版本）

提供更详细的错误信息和多种安装方式
"""

import sys
import subprocess
import importlib
from pathlib import Path


def run_command(cmd, description=""):
    """运行命令并显示输出"""
    if description:
        print(f"\n{description}")
    print(f"执行: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 错误: {e}")
        if e.stderr:
            print(f"错误信息: {e.stderr}")
        return False


def check_package(package_name, import_name=None):
    """检查包是否已安装"""
    if import_name is None:
        import_name = package_name
    
    try:
        module = importlib.import_module(import_name)
        version = getattr(module, '__version__', 'installed')
        print(f"✓ {package_name}: {version}")
        return True
    except ImportError:
        print(f"✗ {package_name}: 未安装")
        return False


def install_with_pip(package, use_mirror=False):
    """使用 pip 安装包"""
    cmd = ["pip", "install", package, "--no-cache-dir", "--upgrade"]
    
    if use_mirror:
        cmd.extend(["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
    
    return run_command(cmd, f"安装 {package}...")


def main():
    print("=" * 60)
    print("RAG 系统依赖安装（Python 版本）")
    print("=" * 60)
    
    # 检查 Python 版本
    print(f"\nPython 版本: {sys.version}")
    
    # 检查虚拟环境
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✓ 虚拟环境已激活")
    else:
        print("⚠️  警告: 未检测到虚拟环境")
        response = input("是否继续? (y/n): ")
        if response.lower() != 'y':
            print("已取消")
            return 1
    
    # 升级 pip
    print("\n1. 升级 pip...")
    run_command(["pip", "install", "--upgrade", "pip", "--quiet"], "")
    
    # 安装基础依赖
    print("\n2. 安装基础依赖...")
    run_command(["pip", "install", "--upgrade", "setuptools", "wheel", "--quiet"], "")
    
    # 安装 chromadb
    print("\n3. 安装 chromadb...")
    chromadb_installed = check_package("chromadb")
    
    if not chromadb_installed:
        print("\n尝试安装 chromadb...")
        success = install_with_pip("chromadb>=0.4.22")
        
        if not success:
            print("\n⚠️  标准源安装失败，尝试使用国内镜像...")
            success = install_with_pip("chromadb>=0.4.22", use_mirror=True)
        
        if not success:
            print("\n❌ chromadb 安装失败")
            print("\n建议:")
            print("  1. 检查网络连接")
            print("  2. 手动安装: pip install chromadb")
            print("  3. 查看详细错误信息")
            return 1
    
    # 安装 sentence-transformers
    print("\n4. 安装 sentence-transformers...")
    st_installed = check_package("sentence-transformers", "sentence_transformers")
    
    if not st_installed:
        print("\n尝试安装 sentence-transformers...")
        print("注意: 首次安装会下载模型文件（约 80MB），可能需要几分钟")
        success = install_with_pip("sentence-transformers>=2.2.0")
        
        if not success:
            print("\n⚠️  标准源安装失败，尝试使用国内镜像...")
            success = install_with_pip("sentence-transformers>=2.2.0", use_mirror=True)
        
        if not success:
            print("\n❌ sentence-transformers 安装失败")
            print("\n建议:")
            print("  1. 检查网络连接")
            print("  2. 手动安装: pip install sentence-transformers")
            print("  3. 查看详细错误信息")
            return 1
    
    # 验证安装
    print("\n" + "=" * 60)
    print("验证安装...")
    print("=" * 60)
    
    chromadb_ok = check_package("chromadb")
    st_ok = check_package("sentence-transformers", "sentence_transformers")
    
    if chromadb_ok and st_ok:
        print("\n✅ 所有依赖已成功安装！")
        print("\n下一步:")
        print("  测试 RAG 系统:")
        print("    python -c \"from ai_codegen.rag import RAGManager; print('RAG 系统可用')\"")
        return 0
    else:
        print("\n❌ 验证失败，部分依赖未正确安装")
        return 1


if __name__ == "__main__":
    sys.exit(main())
