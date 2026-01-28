"""
PRD 分析器

解析产品需求文档，提取关键改动点。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import re
import json


class ChangeType(Enum):
    """改动类型"""
    NEW_FEATURE = "new_feature"
    ENHANCEMENT = "enhancement"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"
    DEPRECATION = "deprecation"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"


class Priority(Enum):
    """优先级"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ChangePoint:
    """
    改动点
    
    表示 PRD 中识别出的一个具体改动。
    """
    id: str
    title: str
    description: str
    change_type: ChangeType
    priority: Priority = Priority.MEDIUM
    
    # 影响范围
    affected_modules: List[str] = field(default_factory=list)
    affected_interfaces: List[str] = field(default_factory=list)
    
    # 依赖关系
    depends_on: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)
    
    # 约束条件
    constraints: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    
    # 元数据
    tags: List[str] = field(default_factory=list)
    estimated_complexity: str = "medium"  # low, medium, high
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "change_type": self.change_type.value,
            "priority": self.priority.value,
            "affected_modules": self.affected_modules,
            "affected_interfaces": self.affected_interfaces,
            "depends_on": self.depends_on,
            "blocks": self.blocks,
            "constraints": self.constraints,
            "acceptance_criteria": self.acceptance_criteria,
            "tags": self.tags,
            "estimated_complexity": self.estimated_complexity,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangePoint":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            change_type=ChangeType(data.get("change_type", "new_feature")),
            priority=Priority(data.get("priority", "medium")),
            affected_modules=data.get("affected_modules", []),
            affected_interfaces=data.get("affected_interfaces", []),
            depends_on=data.get("depends_on", []),
            blocks=data.get("blocks", []),
            constraints=data.get("constraints", []),
            acceptance_criteria=data.get("acceptance_criteria", []),
            tags=data.get("tags", []),
            estimated_complexity=data.get("estimated_complexity", "medium"),
        )


@dataclass
class PRDDocument:
    """
    PRD 文档
    
    表示解析后的产品需求文档。
    """
    title: str
    version: str = "1.0.0"
    description: str = ""
    
    # 改动点
    change_points: List[ChangePoint] = field(default_factory=list)
    
    # 全局约束
    global_constraints: List[str] = field(default_factory=list)
    
    # 非功能性需求
    performance_requirements: List[str] = field(default_factory=list)
    security_requirements: List[str] = field(default_factory=list)
    
    # 元数据
    authors: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "version": self.version,
            "description": self.description,
            "change_points": [cp.to_dict() for cp in self.change_points],
            "global_constraints": self.global_constraints,
            "performance_requirements": self.performance_requirements,
            "security_requirements": self.security_requirements,
            "authors": self.authors,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PRDDocument":
        return cls(
            title=data.get("title", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            change_points=[
                ChangePoint.from_dict(cp) 
                for cp in data.get("change_points", [])
            ],
            global_constraints=data.get("global_constraints", []),
            performance_requirements=data.get("performance_requirements", []),
            security_requirements=data.get("security_requirements", []),
            authors=data.get("authors", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> "PRDDocument":
        return cls.from_dict(json.loads(json_str))


class PRDAnalyzer:
    """
    PRD 分析器
    
    解析 PRD 文档并提取改动点。
    支持多种格式：Markdown, JSON, 结构化文本。
    """
    
    def __init__(self, llm_client: Optional[Any] = None):
        """
        初始化分析器
        
        Args:
            llm_client: LLM 客户端（用于智能解析）
        """
        self._llm_client = llm_client
        
        # 关键词映射
        self._change_type_keywords = {
            ChangeType.NEW_FEATURE: [
                "add", "new", "create", "implement", "introduce",
                "新增", "添加", "创建", "实现"
            ],
            ChangeType.ENHANCEMENT: [
                "improve", "enhance", "optimize", "upgrade", "update",
                "改进", "优化", "升级", "更新", "增强"
            ],
            ChangeType.BUG_FIX: [
                "fix", "resolve", "repair", "correct", "patch",
                "修复", "修正", "解决"
            ],
            ChangeType.REFACTOR: [
                "refactor", "restructure", "reorganize", "clean",
                "重构", "重组"
            ],
            ChangeType.DEPRECATION: [
                "deprecate", "remove", "delete", "drop",
                "废弃", "移除", "删除"
            ],
        }
        
        self._priority_keywords = {
            Priority.CRITICAL: ["critical", "urgent", "blocker", "紧急", "关键"],
            Priority.HIGH: ["high", "important", "必须", "重要"],
            Priority.MEDIUM: ["medium", "normal", "一般"],
            Priority.LOW: ["low", "nice to have", "可选"],
        }
    
    def analyze(self, content: str, format: str = "auto") -> PRDDocument:
        """
        分析 PRD 内容
        
        Args:
            content: PRD 内容
            format: 格式类型 ("auto", "markdown", "json", "text")
            
        Returns:
            PRDDocument: 解析后的 PRD 文档
        """
        if format == "auto":
            format = self._detect_format(content)
        
        if format == "json":
            return self._parse_json(content)
        elif format == "markdown":
            return self._parse_markdown(content)
        else:
            return self._parse_text(content)
    
    def _detect_format(self, content: str) -> str:
        """检测内容格式"""
        content = content.strip()
        
        if content.startswith("{"):
            return "json"
        elif content.startswith("#") or "## " in content:
            return "markdown"
        else:
            return "text"
    
    def _parse_json(self, content: str) -> PRDDocument:
        """解析 JSON 格式"""
        data = json.loads(content)
        return PRDDocument.from_dict(data)
    
    def _parse_markdown(self, content: str) -> PRDDocument:
        """解析 Markdown 格式"""
        lines = content.split("\n")
        
        # 提取标题
        title = ""
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break
        
        # 创建文档
        doc = PRDDocument(title=title or "Untitled PRD")
        
        # 解析各部分
        current_section = ""
        current_content = []
        change_point_id = 0
        
        for line in lines:
            if line.startswith("## "):
                # 处理上一个部分
                if current_section and current_content:
                    self._process_section(doc, current_section, current_content)
                
                current_section = line[3:].strip()
                current_content = []
            elif line.startswith("### "):
                # 子部分，可能是具体的改动点
                if current_content:
                    self._process_section(doc, current_section, current_content)
                    current_content = []
                
                # 创建改动点
                change_point_id += 1
                change_point = ChangePoint(
                    id=f"cp-{change_point_id}",
                    title=line[4:].strip(),
                    description="",
                    change_type=self._infer_change_type(line),
                )
                doc.change_points.append(change_point)
                current_content = []
            elif current_section:
                current_content.append(line)
        
        # 处理最后一个部分
        if current_section and current_content:
            self._process_section(doc, current_section, current_content)
        
        return doc
    
    def _process_section(
        self,
        doc: PRDDocument,
        section: str,
        content: List[str]
    ):
        """处理 Markdown 部分"""
        section_lower = section.lower()
        text = "\n".join(content).strip()
        
        if "description" in section_lower or "概述" in section_lower:
            doc.description = text
        elif "constraint" in section_lower or "约束" in section_lower:
            doc.global_constraints = self._extract_list_items(content)
        elif "performance" in section_lower or "性能" in section_lower:
            doc.performance_requirements = self._extract_list_items(content)
        elif "security" in section_lower or "安全" in section_lower:
            doc.security_requirements = self._extract_list_items(content)
        elif doc.change_points:
            # 添加到最近的改动点
            last_cp = doc.change_points[-1]
            if not last_cp.description:
                last_cp.description = text
            
            # 提取验收标准
            if "acceptance" in section_lower or "验收" in section_lower:
                last_cp.acceptance_criteria = self._extract_list_items(content)
    
    def _extract_list_items(self, lines: List[str]) -> List[str]:
        """提取列表项"""
        items = []
        for line in lines:
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                items.append(line[2:].strip())
            elif line.startswith("1. ") or re.match(r"^\d+\. ", line):
                items.append(re.sub(r"^\d+\. ", "", line).strip())
        return items
    
    def _parse_text(self, content: str) -> PRDDocument:
        """解析纯文本格式"""
        doc = PRDDocument(title="PRD Document")
        
        # 简单的段落分析
        paragraphs = content.split("\n\n")
        
        if paragraphs:
            doc.description = paragraphs[0].strip()
        
        change_point_id = 0
        for para in paragraphs[1:]:
            para = para.strip()
            if not para:
                continue
            
            change_point_id += 1
            change_point = ChangePoint(
                id=f"cp-{change_point_id}",
                title=para.split("\n")[0][:100],
                description=para,
                change_type=self._infer_change_type(para),
                priority=self._infer_priority(para),
            )
            doc.change_points.append(change_point)
        
        return doc
    
    def _infer_change_type(self, text: str) -> ChangeType:
        """推断改动类型"""
        text_lower = text.lower()
        
        for change_type, keywords in self._change_type_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return change_type
        
        return ChangeType.NEW_FEATURE
    
    def _infer_priority(self, text: str) -> Priority:
        """推断优先级"""
        text_lower = text.lower()
        
        for priority, keywords in self._priority_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return priority
        
        return Priority.MEDIUM
    
    async def analyze_with_llm(
        self,
        content: str,
        code_context: Optional[str] = None
    ) -> PRDDocument:
        """
        使用 LLM 进行智能分析
        
        Args:
            content: PRD 内容
            code_context: 代码上下文（可选）
            
        Returns:
            PRDDocument: 解析后的 PRD 文档
        """
        if not self._llm_client:
            return self.analyze(content)
        
        # 构建分析提示
        prompt = self._build_analysis_prompt(content, code_context)
        
        # 调用 LLM
        response = await self._llm_client.complete(prompt)
        
        # 解析响应
        return self._parse_llm_response(response)
    
    def _build_analysis_prompt(
        self,
        content: str,
        code_context: Optional[str] = None
    ) -> str:
        """构建 LLM 分析提示"""
        prompt = f"""Analyze the following Product Requirements Document (PRD) and extract structured change points.

PRD Content:
{content}

"""
        if code_context:
            prompt += f"""
Code Context (existing interfaces and modules):
{code_context}

"""
        
        prompt += """
Please extract the following information in JSON format:
1. title: Document title
2. description: Brief description
3. change_points: List of specific changes, each with:
   - id: Unique identifier
   - title: Short title
   - description: Detailed description
   - change_type: One of [new_feature, enhancement, bug_fix, refactor, deprecation]
   - priority: One of [critical, high, medium, low]
   - affected_modules: List of module names that will be affected
   - affected_interfaces: List of interface names that will be affected
   - depends_on: List of change point IDs this depends on
   - acceptance_criteria: List of acceptance criteria

Respond with valid JSON only.
"""
        return prompt
    
    def _parse_llm_response(self, response: str) -> PRDDocument:
        """解析 LLM 响应"""
        # 尝试提取 JSON
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            json_str = response.strip()
        
        try:
            data = json.loads(json_str)
            return PRDDocument.from_dict(data)
        except json.JSONDecodeError:
            # 回退到基本解析
            return self.analyze(response, format="text")
    
    def extract_affected_components(
        self,
        change_points: List[ChangePoint],
        knowledge_graph: Any
    ) -> Dict[str, List[str]]:
        """
        根据改动点和知识图谱提取受影响的组件
        
        Args:
            change_points: 改动点列表
            knowledge_graph: 代码知识图谱
            
        Returns:
            Dict: 改动点 ID 到受影响组件列表的映射
        """
        affected = {}
        
        for cp in change_points:
            components = set()
            
            # 从已标注的模块开始
            for module in cp.affected_modules:
                components.add(module)
                
                # 使用知识图谱查找依赖
                if knowledge_graph:
                    deps = knowledge_graph.get_subgraph(
                        f"module:{module}",
                        depth=2,
                        direction="incoming"
                    )
                    for node, _ in deps if isinstance(deps, tuple) else []:
                        if hasattr(node, 'properties'):
                            components.add(node.properties.get("name", node.id))
            
            affected[cp.id] = list(components)
        
        return affected
