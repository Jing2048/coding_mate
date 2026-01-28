"""
持久化存储模块

使用 SQLite 存储代码分析结果、知识图谱、PRD 和任务。
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class StoredParseResult:
    """存储的解析结果"""
    file_path: str
    content_hash: str
    symbols: List[Dict]
    imports: List[Dict]
    parsed_at: str


@dataclass
class StoredPRD:
    """存储的 PRD"""
    prd_id: str
    content: str
    analysis: Dict
    created_at: str


@dataclass
class StoredTask:
    """存储的任务"""
    task_id: str
    prd_id: str
    title: str
    description: str
    status: str
    files: List[str]
    created_at: str


# ============================================================================
# Persistence Manager
# ============================================================================

class PersistenceManager:
    """
    持久化管理器
    
    管理代码分析结果、知识图谱、PRD 和任务的持久化存储。
    """
    
    def __init__(self, workspace_path: str, db_name: str = ".ai_codegen.db"):
        self.workspace_path = Path(workspace_path)
        self.db_path = self.workspace_path / db_name
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 解析结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parse_results (
                file_path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                symbols TEXT,
                imports TEXT,
                parsed_at TEXT
            )
        ''')
        
        # 知识图谱节点表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                name TEXT NOT NULL,
                file_path TEXT,
                properties TEXT,
                created_at TEXT
            )
        ''')
        
        # 知识图谱边表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS graph_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                properties TEXT,
                UNIQUE(source_id, target_id, edge_type)
            )
        ''')
        
        # PRD 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prds (
                prd_id TEXT PRIMARY KEY,
                content TEXT,
                analysis TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # 任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                prd_id TEXT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                files TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_type ON graph_nodes(node_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_file ON graph_nodes(file_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_prd ON tasks(prd_id)')
        
        conn.commit()
        conn.close()
    
    # ========================================================================
    # Parse Results
    # ========================================================================
    
    def save_parse_result(
        self, 
        file_path: str, 
        content_hash: str,
        symbols: List[Dict], 
        imports: List[Dict]
    ):
        """保存解析结果"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO parse_results 
            (file_path, content_hash, symbols, imports, parsed_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            file_path, 
            content_hash, 
            json.dumps(symbols), 
            json.dumps(imports), 
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_parse_result(self, file_path: str) -> Optional[StoredParseResult]:
        """获取解析结果"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT file_path, content_hash, symbols, imports, parsed_at FROM parse_results WHERE file_path = ?',
            (file_path,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return StoredParseResult(
            file_path=row[0],
            content_hash=row[1],
            symbols=json.loads(row[2]) if row[2] else [],
            imports=json.loads(row[3]) if row[3] else [],
            parsed_at=row[4]
        )
    
    def get_all_parse_results(self) -> List[StoredParseResult]:
        """获取所有解析结果"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT file_path, content_hash, symbols, imports, parsed_at FROM parse_results')
        rows = cursor.fetchall()
        conn.close()
        
        return [
            StoredParseResult(
                file_path=row[0],
                content_hash=row[1],
                symbols=json.loads(row[2]) if row[2] else [],
                imports=json.loads(row[3]) if row[3] else [],
                parsed_at=row[4]
            )
            for row in rows
        ]
    
    # ========================================================================
    # Knowledge Graph
    # ========================================================================
    
    def save_graph_node(
        self, 
        node_id: str, 
        node_type: str, 
        name: str,
        file_path: str = None, 
        properties: Dict = None
    ):
        """保存图节点"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO graph_nodes 
            (id, node_type, name, file_path, properties, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            node_id, 
            node_type, 
            name, 
            file_path,
            json.dumps(properties or {}), 
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def save_graph_edge(
        self, 
        source_id: str, 
        target_id: str, 
        edge_type: str, 
        properties: Dict = None
    ):
        """保存图边（去重）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO graph_edges (source_id, target_id, edge_type, properties)
            VALUES (?, ?, ?, ?)
        ''', (source_id, target_id, edge_type, json.dumps(properties or {})))
        
        conn.commit()
        conn.close()
    
    def query_graph_nodes(
        self, 
        node_type: str = None, 
        file_path: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """查询图节点"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = 'SELECT id, node_type, name, file_path, properties FROM graph_nodes WHERE 1=1'
        params = []
        
        if node_type:
            query += ' AND node_type = ?'
            params.append(node_type)
        if file_path:
            query += ' AND file_path = ?'
            params.append(file_path)
        
        query += f' LIMIT {limit}'
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            'id': row[0],
            'node_type': row[1],
            'name': row[2],
            'file_path': row[3],
            'properties': json.loads(row[4]) if row[4] else {}
        } for row in rows]
    
    def query_graph_edges(
        self, 
        source_id: str = None,
        target_id: str = None,
        edge_type: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """查询图边"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = 'SELECT source_id, target_id, edge_type, properties FROM graph_edges WHERE 1=1'
        params = []
        
        if source_id:
            query += ' AND source_id = ?'
            params.append(source_id)
        if target_id:
            query += ' AND target_id = ?'
            params.append(target_id)
        if edge_type:
            query += ' AND edge_type = ?'
            params.append(edge_type)
        
        query += f' LIMIT {limit}'
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            'source_id': row[0],
            'target_id': row[1],
            'edge_type': row[2],
            'properties': json.loads(row[3]) if row[3] else {}
        } for row in rows]
    
    def clear_graph(self):
        """清空知识图谱"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM graph_edges')
        cursor.execute('DELETE FROM graph_nodes')
        conn.commit()
        conn.close()
    
    # ========================================================================
    # PRD
    # ========================================================================
    
    def save_prd_analysis(self, prd_id: str, content: str, analysis: Dict):
        """保存 PRD"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO prds (prd_id, content, analysis, created_at, updated_at)
            VALUES (?, ?, ?, COALESCE((SELECT created_at FROM prds WHERE prd_id = ?), ?), ?)
        ''', (prd_id, content, json.dumps(analysis), prd_id, now, now))
        
        conn.commit()
        conn.close()
    
    def get_prd_analysis(self, prd_id: str) -> Optional[StoredPRD]:
        """获取 PRD"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT prd_id, content, analysis, created_at FROM prds WHERE prd_id = ?', (prd_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return StoredPRD(
            prd_id=row[0],
            content=row[1] or '',
            analysis=json.loads(row[2]) if row[2] else {},
            created_at=row[3]
        )
    
    def get_all_prd_analyses(self) -> List[StoredPRD]:
        """获取所有 PRD"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT prd_id, content, analysis, created_at FROM prds ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        
        return [
            StoredPRD(
                prd_id=row[0],
                content=row[1] or '',
                analysis=json.loads(row[2]) if row[2] else {},
                created_at=row[3]
            )
            for row in rows
        ]
    
    # ========================================================================
    # Tasks
    # ========================================================================
    
    def save_task(
        self, 
        task_id: str, 
        prd_id: str, 
        title: str, 
        description: str,
        status: str,
        files: List[str]
    ):
        """保存任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO tasks 
            (task_id, prd_id, title, description, status, files, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM tasks WHERE task_id = ?), ?), ?)
        ''', (task_id, prd_id, title, description, status, json.dumps(files), task_id, now, now))
        
        conn.commit()
        conn.close()
    
    def get_task(self, task_id: str) -> Optional[StoredTask]:
        """获取任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT task_id, prd_id, title, description, status, files, created_at FROM tasks WHERE task_id = ?',
            (task_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return StoredTask(
            task_id=row[0],
            prd_id=row[1],
            title=row[2],
            description=row[3] or '',
            status=row[4],
            files=json.loads(row[5]) if row[5] else [],
            created_at=row[6]
        )
    
    def get_tasks_by_prd(self, prd_id: str) -> List[StoredTask]:
        """获取 PRD 的所有任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT task_id, prd_id, title, description, status, files, created_at FROM tasks WHERE prd_id = ?',
            (prd_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [
            StoredTask(
                task_id=row[0],
                prd_id=row[1],
                title=row[2],
                description=row[3] or '',
                status=row[4],
                files=json.loads(row[5]) if row[5] else [],
                created_at=row[6]
            )
            for row in rows
        ]
    
    def get_all_tasks(self) -> List[StoredTask]:
        """获取所有任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT task_id, prd_id, title, description, status, files, created_at FROM tasks')
        rows = cursor.fetchall()
        conn.close()
        
        return [
            StoredTask(
                task_id=row[0],
                prd_id=row[1],
                title=row[2],
                description=row[3] or '',
                status=row[4],
                files=json.loads(row[5]) if row[5] else [],
                created_at=row[6]
            )
            for row in rows
        ]
    
    def update_task_status(self, task_id: str, status: str):
        """更新任务状态"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?
        ''', (status, datetime.now().isoformat(), task_id))
        
        conn.commit()
        conn.close()
    
    # ========================================================================
    # Statistics
    # ========================================================================
    
    def get_statistics(self) -> Dict:
        """获取存储统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        cursor.execute('SELECT COUNT(*) FROM parse_results')
        stats['parsed_files'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM graph_nodes')
        stats['graph_nodes'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM graph_edges')
        stats['graph_edges'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM prds')
        stats['prds'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM tasks')
        stats['tasks'] = cursor.fetchone()[0]
        
        conn.close()
        return stats
    
    def reset(self):
        """重置数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM graph_edges')
        cursor.execute('DELETE FROM graph_nodes')
        cursor.execute('DELETE FROM parse_results')
        cursor.execute('DELETE FROM tasks')
        cursor.execute('DELETE FROM prds')
        
        conn.commit()
        conn.close()
