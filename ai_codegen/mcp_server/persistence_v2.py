"""
持久化存储模块 V2

支持 CodeEntity 存储和 RAG 向量存储。
"""

import sqlite3
import json
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from ai_codegen.models import CodeEntity


class PersistenceManagerV2:
    """
    持久化管理器 V2
    
    支持 CodeEntity 存储和查询。
    """
    
    def __init__(self, workspace_path: str):
        """
        初始化
        
        Args:
            workspace_path: 工作空间路径
        """
        self.workspace_path = Path(workspace_path)
        self.db_path = self.workspace_path / ".ai_codegen_v2.db"
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        # 实体表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                module TEXT,
                file_path TEXT,
                description TEXT,
                purpose TEXT,
                domain TEXT,
                tags TEXT,
                complexity INTEGER,
                last_modified REAL,
                embedding_text TEXT,
                data TEXT
            )
        """)
        
        # 依赖关系表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dependencies (
                source_id TEXT,
                target_id TEXT,
                relation_type TEXT,
                context TEXT,
                line INTEGER,
                PRIMARY KEY (source_id, target_id, relation_type),
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            )
        """)
        
        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_module ON entities(module)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_domain ON entities(domain)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deps_source ON dependencies(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deps_target ON dependencies(target_id)")
        
        try:
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def save_entity(self, entity: CodeEntity):
        """
        保存实体
        
        Args:
            entity: CodeEntity 对象
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        # 生成 embedding_text（如果还没有）
        if not entity.embedding_text:
            entity.generate_embedding_text()
        
        # 保存实体
        cursor.execute("""
            INSERT OR REPLACE INTO entities
            (id, type, name, module, file_path, description, purpose, domain,
             tags, complexity, last_modified, embedding_text, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity.id,
            entity.type.value,
            entity.name,
            entity.module,
            entity.file_path,
            entity.description,
            entity.purpose,
            entity.domain,
            json.dumps(entity.tags),
            entity.complexity,
            entity.last_modified,
            entity.embedding_text,
            json.dumps(entity.to_dict(), ensure_ascii=False)
        ))
        
        # 保存依赖关系
        cursor.execute("DELETE FROM dependencies WHERE source_id = ?", (entity.id,))
        for dep in entity.dependencies:
            cursor.execute("""
                INSERT INTO dependencies (source_id, target_id, relation_type, context, line)
                VALUES (?, ?, ?, ?, ?)
            """, (
                entity.id,
                dep.target_id,
                dep.relation_type.value,
                dep.context,
                dep.line
            ))
        
        try:
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_entity(self, entity_id: str) -> Optional[CodeEntity]:
        """
        获取实体
        
        Args:
            entity_id: 实体 ID
        
        Returns:
            CodeEntity 对象或 None
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT data FROM entities WHERE id = ?", (entity_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            data = json.loads(row[0])
            return CodeEntity.from_dict(data)
        return None
    
    def get_entities_by_module(self, module: str) -> List[CodeEntity]:
        """按模块获取实体"""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT data FROM entities WHERE module = ?", (module,))
        rows = cursor.fetchall()
        conn.close()
        
        return [CodeEntity.from_dict(json.loads(row[0])) for row in rows]
    
    def get_entities_by_type(self, entity_type: str) -> List[CodeEntity]:
        """按类型获取实体"""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT data FROM entities WHERE type = ?", (entity_type,))
        rows = cursor.fetchall()
        conn.close()
        
        return [CodeEntity.from_dict(json.loads(row[0])) for row in rows]
    
    def search_entities(
        self,
        query: str,
        limit: int = 20,
        entity_type: Optional[str] = None,
        domain: Optional[str] = None
    ) -> List[CodeEntity]:
        """
        搜索实体（基于 embedding_text，简单文本搜索）
        
        Args:
            query: 搜索查询
            limit: 返回数量限制
            entity_type: 实体类型过滤
            domain: 领域过滤
        
        Returns:
            CodeEntity 列表
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        conditions = ["embedding_text LIKE ?"]
        params = [f"%{query}%"]
        
        if entity_type:
            conditions.append("type = ?")
            params.append(entity_type)
        
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        
        sql = f"""
            SELECT data FROM entities
            WHERE {' AND '.join(conditions)}
            LIMIT ?
        """
        params.append(limit)
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [CodeEntity.from_dict(json.loads(row[0])) for row in rows]
    
    def get_all_entities(self, limit: Optional[int] = None) -> List[CodeEntity]:
        """
        获取所有实体
        
        Args:
            limit: 数量限制（None 表示不限制）
        
        Returns:
            CodeEntity 列表
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        sql = "SELECT data FROM entities"
        if limit:
            sql += f" LIMIT {limit}"
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        
        return [CodeEntity.from_dict(json.loads(row[0])) for row in rows]
    
    def get_dependencies(self, entity_id: str) -> List[Dict]:
        """获取实体的依赖关系"""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT target_id, relation_type, context, line
            FROM dependencies
            WHERE source_id = ?
        """, (entity_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "target_id": row[0],
                "relation_type": row[1],
                "context": row[2],
                "line": row[3]
            }
            for row in rows
        ]
    
    def get_dependents(self, entity_id: str) -> List[str]:
        """获取依赖此实体的实体列表"""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT source_id FROM dependencies WHERE target_id = ?", (entity_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [row[0] for row in rows]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM entities")
        total_entities = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM dependencies")
        total_dependencies = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT module) FROM entities")
        total_modules = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT domain) FROM entities WHERE domain != ''")
        total_domains = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_entities": total_entities,
            "total_dependencies": total_dependencies,
            "total_modules": total_modules,
            "total_domains": total_domains
        }
