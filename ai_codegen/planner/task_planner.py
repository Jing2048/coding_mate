"""
DAG 任务规划器

将改动点转换为可执行的 DAG 任务计划。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from enum import Enum
import json
from collections import deque
import hashlib


class TaskType(Enum):
    """任务类型"""
    INTERFACE_DESIGN = "interface_design"
    IMPLEMENTATION = "implementation"
    UNIT_TEST = "unit_test"
    INTEGRATION_TEST = "integration_test"
    DOCUMENTATION = "documentation"
    REVIEW = "review"
    REFACTOR = "refactor"
    MIGRATION = "migration"


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    READY = "ready"  # 依赖已满足，可以执行
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """
    任务
    
    表示 DAG 中的一个可执行任务。
    """
    id: str
    title: str
    task_type: TaskType
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    
    # 目标
    target: str = ""  # 目标模块/接口/函数
    target_file: Optional[str] = None
    
    # 依赖
    dependencies: List[str] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)
    
    # 输入输出
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    
    # 上下文
    interface_ref: Optional[str] = None  # 引用的接口定义
    context: Dict[str, Any] = field(default_factory=dict)
    
    # 执行结果
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # 元数据
    priority: int = 0  # 执行优先级
    estimated_tokens: int = 0  # 预估 token 消耗
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "task_type": self.task_type.value,
            "description": self.description,
            "status": self.status.value,
            "target": self.target,
            "target_file": self.target_file,
            "dependencies": self.dependencies,
            "blocked_by": self.blocked_by,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "interface_ref": self.interface_ref,
            "context": self.context,
            "priority": self.priority,
            "estimated_tokens": self.estimated_tokens,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            task_type=TaskType(data.get("task_type", "implementation")),
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "pending")),
            target=data.get("target", ""),
            target_file=data.get("target_file"),
            dependencies=data.get("dependencies", []),
            blocked_by=data.get("blocked_by", []),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            interface_ref=data.get("interface_ref"),
            context=data.get("context", {}),
            priority=data.get("priority", 0),
            estimated_tokens=data.get("estimated_tokens", 0),
        )
    
    def is_ready(self) -> bool:
        """检查任务是否就绪（所有依赖已完成）"""
        return self.status == TaskStatus.READY
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retry_count < self.max_retries


@dataclass
class TaskDAG:
    """
    任务 DAG
    
    表示任务的有向无环图。
    """
    id: str
    name: str
    tasks: Dict[str, Task] = field(default_factory=dict)
    
    # 图结构
    adjacency: Dict[str, Set[str]] = field(default_factory=dict)  # 出边
    reverse_adjacency: Dict[str, Set[str]] = field(default_factory=dict)  # 入边
    
    # 元数据
    created_at: Optional[str] = None
    source_prd: Optional[str] = None
    
    def add_task(self, task: Task) -> str:
        """添加任务"""
        self.tasks[task.id] = task
        
        if task.id not in self.adjacency:
            self.adjacency[task.id] = set()
        if task.id not in self.reverse_adjacency:
            self.reverse_adjacency[task.id] = set()
        
        # 添加依赖边
        for dep_id in task.dependencies:
            if dep_id not in self.adjacency:
                self.adjacency[dep_id] = set()
            self.adjacency[dep_id].add(task.id)
            
            if task.id not in self.reverse_adjacency:
                self.reverse_adjacency[task.id] = set()
            self.reverse_adjacency[task.id].add(dep_id)
        
        return task.id
    
    def remove_task(self, task_id: str):
        """移除任务"""
        if task_id not in self.tasks:
            return
        
        # 移除相关边
        for target in self.adjacency.get(task_id, set()):
            self.reverse_adjacency[target].discard(task_id)
        
        for source in self.reverse_adjacency.get(task_id, set()):
            self.adjacency[source].discard(task_id)
        
        del self.tasks[task_id]
        self.adjacency.pop(task_id, None)
        self.reverse_adjacency.pop(task_id, None)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def get_ready_tasks(self) -> List[Task]:
        """获取所有就绪的任务"""
        ready = []
        
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING:
                # 检查所有依赖是否完成
                deps_completed = all(
                    self.tasks.get(dep_id, Task(id="")).status == TaskStatus.COMPLETED
                    for dep_id in task.dependencies
                )
                
                if deps_completed:
                    task.status = TaskStatus.READY
                    ready.append(task)
            elif task.status == TaskStatus.READY:
                ready.append(task)
        
        return sorted(ready, key=lambda t: t.priority, reverse=True)
    
    def mark_completed(self, task_id: str, result: Any = None):
        """标记任务完成"""
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.result = result
            
            # 更新下游任务状态
            self._update_downstream_status(task_id)
    
    def mark_failed(self, task_id: str, error: str):
        """标记任务失败"""
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = error
            
            # 标记下游任务为阻塞
            self._mark_downstream_blocked(task_id)
    
    def _update_downstream_status(self, task_id: str):
        """更新下游任务状态"""
        for downstream_id in self.adjacency.get(task_id, set()):
            downstream = self.tasks.get(downstream_id)
            if downstream and downstream.status == TaskStatus.PENDING:
                deps_completed = all(
                    self.tasks.get(dep_id, Task(id="")).status == TaskStatus.COMPLETED
                    for dep_id in downstream.dependencies
                )
                if deps_completed:
                    downstream.status = TaskStatus.READY
    
    def _mark_downstream_blocked(self, task_id: str):
        """标记下游任务为阻塞"""
        visited = set()
        queue = list(self.adjacency.get(task_id, set()))
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            task = self.tasks.get(current)
            if task and task.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                task.status = TaskStatus.BLOCKED
                task.blocked_by.append(task_id)
                queue.extend(self.adjacency.get(current, set()))
    
    def topological_sort(self) -> List[str]:
        """拓扑排序"""
        in_degree = {task_id: len(deps) for task_id, deps in self.reverse_adjacency.items()}
        
        # 添加没有入边的节点
        for task_id in self.tasks:
            if task_id not in in_degree:
                in_degree[task_id] = 0
        
        queue = deque([t for t, d in in_degree.items() if d == 0])
        result = []
        
        while queue:
            task_id = queue.popleft()
            result.append(task_id)
            
            for downstream in self.adjacency.get(task_id, set()):
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    queue.append(downstream)
        
        if len(result) != len(self.tasks):
            raise ValueError("Graph contains cycles")
        
        return result
    
    def get_critical_path(self) -> List[str]:
        """获取关键路径"""
        # 使用拓扑排序计算最长路径
        sorted_tasks = self.topological_sort()
        
        distances = {task_id: 0 for task_id in self.tasks}
        predecessors = {task_id: None for task_id in self.tasks}
        
        for task_id in sorted_tasks:
            task = self.tasks.get(task_id)
            if not task:
                continue
                
            # 使用预估 token 作为权重
            weight = task.estimated_tokens or 1
            
            for downstream in self.adjacency.get(task_id, set()):
                if distances[task_id] + weight > distances[downstream]:
                    distances[downstream] = distances[task_id] + weight
                    predecessors[downstream] = task_id
        
        # 找到最长路径的终点
        end_task = max(distances.keys(), key=lambda t: distances[t])
        
        # 回溯构建路径
        path = []
        current = end_task
        while current:
            path.append(current)
            current = predecessors[current]
        
        return list(reversed(path))
    
    def validate(self) -> List[str]:
        """验证 DAG 的有效性"""
        errors = []
        
        # 检查是否有环
        try:
            self.topological_sort()
        except ValueError:
            errors.append("DAG contains cycles")
        
        # 检查依赖引用
        for task in self.tasks.values():
            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    errors.append(f"Task {task.id} references non-existent dependency {dep_id}")
        
        # 检查孤立任务
        all_deps = set()
        for deps in self.adjacency.values():
            all_deps.update(deps)
        
        root_tasks = [
            t for t in self.tasks
            if not self.reverse_adjacency.get(t)
        ]
        
        if not root_tasks:
            errors.append("No root tasks found")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tasks": [t.to_dict() for t in self.tasks.values()],
            "source_prd": self.source_prd,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDAG":
        dag = cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            source_prd=data.get("source_prd"),
            created_at=data.get("created_at"),
        )
        
        for task_data in data.get("tasks", []):
            task = Task.from_dict(task_data)
            dag.add_task(task)
        
        return dag
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        status_counts = {}
        type_counts = {}
        total_estimated = 0
        
        for task in self.tasks.values():
            status = task.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            
            task_type = task.task_type.value
            type_counts[task_type] = type_counts.get(task_type, 0) + 1
            
            total_estimated += task.estimated_tokens
        
        return {
            "total_tasks": len(self.tasks),
            "by_status": status_counts,
            "by_type": type_counts,
            "total_estimated_tokens": total_estimated,
            "critical_path_length": len(self.get_critical_path()),
        }


class TaskPlanner:
    """
    任务规划器
    
    将 PRD 改动点转换为可执行的 DAG 任务计划。
    """
    
    def __init__(
        self,
        interface_registry: Optional[Any] = None,
        knowledge_graph: Optional[Any] = None,
        llm_client: Optional[Any] = None
    ):
        """
        初始化规划器
        
        Args:
            interface_registry: 接口注册表
            knowledge_graph: 代码知识图谱
            llm_client: LLM 客户端
        """
        self._interface_registry = interface_registry
        self._knowledge_graph = knowledge_graph
        self._llm_client = llm_client
    
    def create_plan(
        self,
        prd_document: Any,
        plan_name: Optional[str] = None
    ) -> TaskDAG:
        """
        创建执行计划
        
        Args:
            prd_document: PRD 文档
            plan_name: 计划名称
            
        Returns:
            TaskDAG: 任务 DAG
        """
        # 生成计划 ID
        plan_id = hashlib.md5(
            f"{prd_document.title}:{len(prd_document.change_points)}".encode()
        ).hexdigest()[:8]
        
        dag = TaskDAG(
            id=f"plan-{plan_id}",
            name=plan_name or prd_document.title,
            source_prd=prd_document.title,
        )
        
        # 为每个改动点创建任务
        task_id_counter = 0
        change_point_tasks: Dict[str, List[str]] = {}
        
        for cp in prd_document.change_points:
            tasks = self._create_tasks_for_change_point(cp, task_id_counter)
            change_point_tasks[cp.id] = [t.id for t in tasks]
            
            for task in tasks:
                dag.add_task(task)
            
            task_id_counter += len(tasks)
        
        # 处理改动点之间的依赖
        self._add_cross_change_point_dependencies(
            dag, 
            prd_document.change_points,
            change_point_tasks
        )
        
        # 验证 DAG
        errors = dag.validate()
        if errors:
            raise ValueError(f"Invalid DAG: {errors}")
        
        return dag
    
    def _create_tasks_for_change_point(
        self,
        change_point: Any,
        start_id: int
    ) -> List[Task]:
        """为单个改动点创建任务"""
        tasks = []
        base_id = f"t{start_id}"
        
        # 1. 接口设计任务
        interface_task = Task(
            id=f"{base_id}-interface",
            title=f"Design interface for {change_point.title}",
            task_type=TaskType.INTERFACE_DESIGN,
            description=f"Define interface for: {change_point.description}",
            target=change_point.title,
            priority=10,
            estimated_tokens=2000,
        )
        tasks.append(interface_task)
        
        # 2. 实现任务
        impl_task = Task(
            id=f"{base_id}-impl",
            title=f"Implement {change_point.title}",
            task_type=TaskType.IMPLEMENTATION,
            description=change_point.description,
            target=change_point.title,
            dependencies=[interface_task.id],
            interface_ref=interface_task.id,
            priority=8,
            estimated_tokens=5000,
        )
        tasks.append(impl_task)
        
        # 3. 单元测试任务
        unit_test_task = Task(
            id=f"{base_id}-unit-test",
            title=f"Unit tests for {change_point.title}",
            task_type=TaskType.UNIT_TEST,
            description=f"Write unit tests based on acceptance criteria",
            target=f"{change_point.title}.test",
            dependencies=[impl_task.id],
            context={"acceptance_criteria": change_point.acceptance_criteria},
            priority=6,
            estimated_tokens=3000,
        )
        tasks.append(unit_test_task)
        
        # 4. 集成测试任务（如果有多个受影响模块）
        if len(change_point.affected_modules) > 1:
            integration_task = Task(
                id=f"{base_id}-integration",
                title=f"Integration tests for {change_point.title}",
                task_type=TaskType.INTEGRATION_TEST,
                description="Verify integration with affected modules",
                target=change_point.title,
                dependencies=[unit_test_task.id],
                context={"affected_modules": change_point.affected_modules},
                priority=4,
                estimated_tokens=4000,
            )
            tasks.append(integration_task)
        
        # 5. 文档任务
        doc_task = Task(
            id=f"{base_id}-doc",
            title=f"Documentation for {change_point.title}",
            task_type=TaskType.DOCUMENTATION,
            description="Update documentation",
            target=change_point.title,
            dependencies=[impl_task.id],
            priority=2,
            estimated_tokens=1000,
        )
        tasks.append(doc_task)
        
        return tasks
    
    def _add_cross_change_point_dependencies(
        self,
        dag: TaskDAG,
        change_points: List[Any],
        change_point_tasks: Dict[str, List[str]]
    ):
        """添加改动点之间的依赖关系"""
        for cp in change_points:
            if not cp.depends_on:
                continue
            
            # 获取当前改动点的第一个任务（接口设计）
            current_tasks = change_point_tasks.get(cp.id, [])
            if not current_tasks:
                continue
            
            first_task = dag.get_task(current_tasks[0])
            if not first_task:
                continue
            
            # 添加对依赖改动点最后一个任务的依赖
            for dep_cp_id in cp.depends_on:
                dep_tasks = change_point_tasks.get(dep_cp_id, [])
                if dep_tasks:
                    last_dep_task_id = dep_tasks[-1]
                    if last_dep_task_id not in first_task.dependencies:
                        first_task.dependencies.append(last_dep_task_id)
                        
                        # 更新 DAG 的边
                        dag.adjacency[last_dep_task_id].add(first_task.id)
                        dag.reverse_adjacency[first_task.id].add(last_dep_task_id)
    
    async def refine_plan_with_llm(
        self,
        dag: TaskDAG,
        context: str
    ) -> TaskDAG:
        """
        使用 LLM 优化计划
        
        Args:
            dag: 原始任务 DAG
            context: 代码上下文
            
        Returns:
            TaskDAG: 优化后的任务 DAG
        """
        if not self._llm_client:
            return dag
        
        prompt = self._build_refinement_prompt(dag, context)
        response = await self._llm_client.complete(prompt)
        
        # 解析响应并更新 DAG
        # 这里可以添加更复杂的逻辑来处理 LLM 的建议
        
        return dag
    
    def _build_refinement_prompt(self, dag: TaskDAG, context: str) -> str:
        """构建优化提示"""
        tasks_json = json.dumps([t.to_dict() for t in dag.tasks.values()], indent=2)
        
        return f"""Review and optimize the following task execution plan.

Current Plan:
{tasks_json}

Code Context:
{context}

Please suggest:
1. Any missing tasks
2. Tasks that can be parallelized
3. Potential risks or blockers
4. Estimated complexity adjustments

Respond in JSON format with your suggestions.
"""
    
    def estimate_resources(self, dag: TaskDAG) -> Dict[str, Any]:
        """估算资源需求"""
        total_tokens = sum(t.estimated_tokens for t in dag.tasks.values())
        
        # 估算并行度
        sorted_tasks = dag.topological_sort()
        levels = {}
        
        for task_id in sorted_tasks:
            task = dag.get_task(task_id)
            if not task:
                continue
                
            level = 0
            for dep_id in task.dependencies:
                if dep_id in levels:
                    level = max(level, levels[dep_id] + 1)
            levels[task_id] = level
        
        max_parallel = max(
            sum(1 for t, l in levels.items() if l == level)
            for level in set(levels.values())
        ) if levels else 1
        
        return {
            "total_estimated_tokens": total_tokens,
            "max_parallelism": max_parallel,
            "total_tasks": len(dag.tasks),
            "critical_path_tasks": len(dag.get_critical_path()),
        }
