"""
数据模型使用示例

展示如何使用 CodeEntity 数据模型。
"""

from ai_codegen.models import (
    CodeEntity,
    EntityType,
    RelationType,
    Signature,
    Parameter,
    TypeInfo,
    Contract,
    Boundary,
    Dependency,
    ThrowSpec,
)


def example_method_entity():
    """示例：方法实体"""
    
    # 创建方法实体
    entity = CodeEntity(
        id="services.user:UserService.get_user",
        type=EntityType.METHOD,
        name="get_user",
        module="services.user",
        file_path="src/services/user.py",
        
        description="根据用户 ID 获取用户信息",
        purpose="查询单个用户数据",
        domain="user_management",
        
        signature=Signature(
            name="get_user",
            parameters=[
                Parameter(
                    name="user_id",
                    type=TypeInfo(name="int", is_optional=False),
                    description="用户 ID，必须大于 0"
                )
            ],
            return_type=TypeInfo(name="Optional[User]", is_optional=True),
            is_async=True
        ),
        
        contract=Contract(
            preconditions=[
                "user_id > 0",
                "user_id is not None"
            ],
            postconditions=[
                "如果用户存在，返回 User 对象",
                "如果用户不存在，返回 None"
            ],
            throws=[
                ThrowSpec(
                    exception_type="ValueError",
                    condition="当 user_id <= 0 时"
                )
            ]
        ),
        
        boundary=Boundary(
            inputs=["Database"],
            outputs=["User"],
            side_effects=["database_query"]
        ),
        
        dependencies=[
            Dependency(
                target_id="db:Database.query",
                relation_type=RelationType.CALLS,
                context="查询用户数据",
                line=25
            )
        ],
        
        source_snippet="""
async def get_user(self, user_id: int) -> Optional[User]:
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    return await self.db.query(User, id=user_id)
        """.strip(),
        
        examples=[
            "user = await service.get_user(123)"
        ],
        
        tags=["async", "public", "query"],
        complexity=2,
        last_modified=1706457600.0
    )
    
    # 生成 embedding_text
    embedding_text = entity.generate_embedding_text()
    print("=== Embedding Text ===")
    print(embedding_text)
    print()
    
    # 格式化为 LLM 可读
    llm_text = entity.format_for_llm()
    print("=== LLM Format ===")
    print(llm_text)
    print()
    
    # 转换为字典
    entity_dict = entity.to_dict()
    print("=== Entity Dict (keys) ===")
    print(list(entity_dict.keys()))
    print()
    
    return entity


def example_class_entity():
    """示例：类实体"""
    
    entity = CodeEntity(
        id="services.user:UserService",
        type=EntityType.CLASS,
        name="UserService",
        module="services.user",
        file_path="src/services/user.py",
        
        description="用户服务类，提供用户相关的业务逻辑",
        purpose="管理用户数据的增删改查操作",
        domain="user_management",
        
        contract=Contract(
            invariants=["数据库连接必须有效"]
        ),
        
        boundary=Boundary(
            inputs=["Database", "Cache", "Logger"],
            outputs=["User", "UserList"],
            side_effects=["database_query", "cache_write"]
        ),
        
        dependencies=[
            Dependency(
                target_id="db:Database",
                relation_type=RelationType.USES,
                context="用于查询用户数据",
                line=15
            ),
            Dependency(
                target_id="models.user:User",
                relation_type=RelationType.USES,
                context="返回用户对象",
                line=20
            )
        ],
        
        source_snippet="""
class UserService:
    def __init__(self, db: Database):
        self.db = db
    
    async def get_user(self, user_id: int) -> Optional[User]:
        return await self.db.query(User, id=user_id)
        """.strip(),
        
        examples=[
            "service = UserService(db)\nuser = await service.get_user(123)"
        ],
        
        tags=["service", "async", "public"],
        complexity=3
    )
    
    embedding_text = entity.generate_embedding_text()
    print("=== Class Embedding Text ===")
    print(embedding_text)
    print()
    
    return entity


def example_serialization():
    """示例：序列化和反序列化"""
    
    # 创建实体
    entity = example_method_entity()
    
    # 序列化
    entity_dict = entity.to_dict()
    json_str = json.dumps(entity_dict, indent=2, ensure_ascii=False)
    
    print("=== Serialized JSON ===")
    print(json_str[:500] + "...")
    print()
    
    # 反序列化
    loaded_dict = json.loads(json_str)
    loaded_entity = CodeEntity.from_dict(loaded_dict)
    
    print("=== Deserialized Entity ===")
    print(f"ID: {loaded_entity.id}")
    print(f"Name: {loaded_entity.name}")
    print(f"Type: {loaded_entity.type.value}")
    print(f"Embedding Text: {loaded_entity.embedding_text[:100]}...")
    print()
    
    return loaded_entity


if __name__ == "__main__":
    import json
    
    print("=" * 60)
    print("数据模型使用示例")
    print("=" * 60)
    print()
    
    # 方法实体示例
    print("【示例 1: 方法实体】")
    print("-" * 60)
    method_entity = example_method_entity()
    print()
    
    # 类实体示例
    print("【示例 2: 类实体】")
    print("-" * 60)
    class_entity = example_class_entity()
    print()
    
    # 序列化示例
    print("【示例 3: 序列化和反序列化】")
    print("-" * 60)
    loaded_entity = example_serialization()
    print()
    
    print("=" * 60)
    print("示例完成")
    print("=" * 60)
