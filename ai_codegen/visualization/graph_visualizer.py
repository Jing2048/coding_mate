"""
代码依赖图可视化器

实现 IGraphVisualizer 接口，生成 Mermaid 图和 HTML 报告。
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from ..mcp_server.persistence import PersistenceManager


@dataclass
class VisualizationConfig:
    """可视化配置"""
    max_nodes: int = 500  # 增加以包含更多文件
    show_labels: bool = True
    direction: str = "LR"  # 左右布局更适合依赖图
    node_colors: Dict[str, str] = None
    
    def __post_init__(self):
        if self.node_colors is None:
            self.node_colors = {
                "class": "#4a90d9",
                "function": "#67b168",
                "method": "#9b59b6",
                "module": "#e74c3c",
            }


class GraphVisualizer:
    """
    代码依赖图可视化器
    
    从持久化存储读取知识图谱数据，生成可视化输出。
    
    @implements IGraphVisualizer
    """
    
    def __init__(self, workspace_path: str, config: VisualizationConfig = None):
        """
        初始化可视化器
        
        Args:
            workspace_path: 工作区路径
            config: 可视化配置
        """
        self.persistence = PersistenceManager(workspace_path)
        self.config = config or VisualizationConfig()
    
    def generate_mermaid(
        self, 
        graph_type: str, 
        filter_pattern: Optional[str] = None
    ) -> str:
        """
        生成 Mermaid 格式的依赖图
        
        @precondition graph_type in ['module_deps', 'class_hierarchy', 'call_graph']
        @postcondition result.startswith('graph') or result.startswith('flowchart')
        
        Args:
            graph_type: 图类型 (module_deps, class_hierarchy, call_graph)
            filter_pattern: 过滤模式 (可选)
            
        Returns:
            str: Mermaid 图定义
        """
        if graph_type not in ['module_deps', 'class_hierarchy', 'call_graph']:
            raise ValueError(f"Invalid graph_type: {graph_type}")
        
        if graph_type == 'module_deps':
            return self._generate_module_deps(filter_pattern)
        elif graph_type == 'class_hierarchy':
            return self._generate_class_hierarchy(filter_pattern)
        else:
            return self._generate_call_graph(filter_pattern)
    
    def _generate_module_deps(self, filter_pattern: Optional[str] = None) -> str:
        """生成模块依赖图"""
        nodes = self.persistence.query_graph_nodes()
        
        # 提取模块（文件）
        modules = {}
        for node in nodes:
            file_path = node.get('file_path', '')
            if filter_pattern and filter_pattern not in file_path:
                continue
            
            # 提取模块名
            module = file_path.replace('/', '_').replace('.py', '').replace('.', '_')
            if module not in modules:
                modules[module] = {
                    'classes': [],
                    'functions': [],
                    'display_name': file_path.split('/')[-1].replace('.py', '')
                }
            
            if node['type'] == 'class':
                modules[module]['classes'].append(node['name'])
            elif node['type'] in ('function', 'method'):
                modules[module]['functions'].append(node['name'])
        
        # 生成 Mermaid
        lines = [f"graph {self.config.direction}"]
        
        # 按目录分组
        dir_modules = {}
        for module, data in modules.items():
            parts = module.split('_')
            if len(parts) > 1:
                dir_name = parts[0]
                if dir_name not in dir_modules:
                    dir_modules[dir_name] = []
                dir_modules[dir_name].append((module, data))
        
        for dir_name, mods in dir_modules.items():
            safe_dir = self._safe_id(dir_name)
            lines.append(f"    subgraph {safe_dir}[{dir_name}]")
            for mod, data in mods[:self.config.max_nodes]:
                class_count = len(data['classes'])
                func_count = len(data['functions'])
                display = data['display_name']
                lines.append(f"        {mod}[\"{display}<br/>{class_count}C {func_count}F\"]")
            lines.append("    end")
        
        return "\n".join(lines)
    
    def _generate_class_hierarchy(self, filter_pattern: Optional[str] = None) -> str:
        """生成类/模块依赖关系图"""
        nodes = self.persistence.query_graph_nodes()
        edges = self.persistence.query_graph_edges()
        
        # 过滤
        if filter_pattern:
            nodes = [n for n in nodes if filter_pattern in n.get('file_path', '')]
        
        # 限制数量
        nodes = nodes[:self.config.max_nodes]
        
        lines = [f"flowchart {self.config.direction}"]
        
        # 按文件分组
        file_nodes = {}
        node_id_map = {}  # 映射 node id 到 safe id
        
        for node in nodes:
            file_path = node.get('file_path', 'unknown')
            if file_path not in file_nodes:
                file_nodes[file_path] = []
            file_nodes[file_path].append(node)
            # 记录映射
            node_id_map[node['id']] = self._safe_id(node['id'])
        
        # 生成节点子图
        for file_path, file_node_list in file_nodes.items():
            module_name = file_path.split('/')[-1].replace('.py', '')
            safe_module = self._safe_id(file_path)
            lines.append(f"    subgraph {safe_module}[\"{module_name}\"]")
            
            # 按类型分组显示
            classes = [n for n in file_node_list if n['type'] == 'class']
            funcs = [n for n in file_node_list if n['type'] in ('function', 'method')]
            
            for cls in classes[:10]:  # 限制每个文件最多 10 个类
                cls_id = self._safe_id(cls['id'])
                lines.append(f"        {cls_id}[[\"{cls['name']}\"]]")
            
            if len(funcs) > 0 and len(funcs) <= 5:
                for func in funcs:
                    func_id = self._safe_id(func['id'])
                    lines.append(f"        {func_id}((\"{func['name']}\"))")
            elif len(funcs) > 5:
                # 太多函数时只显示计数
                lines.append(f"        {safe_module}_funcs{{{{+{len(funcs)} functions}}}}")
            
            lines.append("    end")
        
        # 生成依赖边
        added_edges = set()
        
        # 获取文件路径到子图ID的映射
        file_to_subgraph = {fp: self._safe_id(fp) for fp in file_nodes.keys()}
        
        for edge in edges:
            source = edge.get('source', '')
            target = edge.get('target', '')
            edge_type = edge.get('type', 'depends_on')
            
            # 只处理文件级导入 (source 不包含冒号)
            if ':' in source:
                continue
            
            # 检查源和目标是否在文件列表中
            if source in file_to_subgraph and target in file_to_subgraph:
                safe_source = file_to_subgraph[source]
                safe_target = file_to_subgraph[target]
                
                # 避免重复边和自环
                edge_key = f"{safe_source}->{safe_target}"
                if edge_key not in added_edges and safe_source != safe_target:
                    # 根据边类型选择样式
                    if edge_type == 'imports':
                        lines.append(f"    {safe_source} -.->|import| {safe_target}")
                    elif edge_type == 'extends':
                        lines.append(f"    {safe_source} ==>|extends| {safe_target}")
                    elif edge_type == 'calls':
                        lines.append(f"    {safe_source} -->|calls| {safe_target}")
                    else:
                        lines.append(f"    {safe_source} --> {safe_target}")
                    
                    added_edges.add(edge_key)
        
        # 如果没有边，添加提示
        if not added_edges:
            lines.append("    %% No file-level dependencies found")
        
        # 添加样式
        lines.append("")
        lines.append(f"    classDef classNode fill:{self.config.node_colors['class']},color:white,stroke:#333")
        lines.append(f"    classDef funcNode fill:{self.config.node_colors['function']},color:white")
        
        return "\n".join(lines)
    
    def _generate_call_graph(self, filter_pattern: Optional[str] = None) -> str:
        """生成调用关系图"""
        nodes = self.persistence.query_graph_nodes()
        
        # 过滤函数和方法
        funcs = [n for n in nodes if n['type'] in ('function', 'method')]
        
        if filter_pattern:
            funcs = [n for n in funcs if filter_pattern in n.get('file_path', '')]
        
        funcs = funcs[:self.config.max_nodes]
        
        lines = [f"flowchart {self.config.direction}"]
        lines.append("    %% 函数/方法关系图")
        lines.append("")
        
        # 按类分组
        class_methods = {}
        standalone = []
        
        for func in funcs:
            props = func.get('properties', {})
            # 检查是否是方法（通过 signature 或 parent）
            signature = props.get('signature', '')
            
            if 'self' in signature or func['type'] == 'method':
                # 尝试从 file_path 获取类信息
                file_path = func.get('file_path', '')
                class_name = f"{file_path}_methods"
                if class_name not in class_methods:
                    class_methods[class_name] = []
                class_methods[class_name].append(func)
            else:
                standalone.append(func)
        
        # 生成类方法子图
        for class_name, methods in class_methods.items():
            short_name = class_name.split('/')[-1].replace('.py_methods', '')
            lines.append(f"    subgraph {self._safe_id(class_name)}[{short_name}]")
            for method in methods:
                method_id = self._safe_id(f"{method.get('file_path', '')}:{method['name']}")
                lines.append(f"        {method_id}(({method['name']}))")
            lines.append("    end")
        
        # 生成独立函数
        if standalone:
            lines.append("    subgraph standalone[独立函数]")
            for func in standalone:
                func_id = self._safe_id(f"{func.get('file_path', '')}:{func['name']}")
                lines.append(f"        {func_id}[/{func['name']}/]")
            lines.append("    end")
        
        # 添加样式
        lines.append("")
        lines.append("    %% 样式")
        lines.append(f"    classDef methodNode fill:{self.config.node_colors['method']},color:white")
        lines.append(f"    classDef funcNode fill:{self.config.node_colors['function']},color:white")
        
        return "\n".join(lines)
    
    def _safe_id(self, s: str) -> str:
        """生成安全的 Mermaid ID"""
        return s.replace('/', '_').replace('.', '_').replace(':', '_').replace('-', '_')
    
    def generate_html_report(
        self, 
        title: str, 
        include_stats: bool = True
    ) -> str:
        """
        生成包含交互式图表的 HTML 报告
        
        @postcondition '<html>' in result
        
        Args:
            title: 报告标题
            include_stats: 是否包含统计信息
            
        Returns:
            str: HTML 报告内容
        """
        stats = self.persistence.get_statistics()
        
        # 生成各种图
        module_mermaid = self.generate_mermaid('module_deps')
        class_mermaid = self.generate_mermaid('class_hierarchy')
        
        # 构建 HTML - Apple Liquid Glass 风格
        html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        :root {{
            --glass-bg: rgba(255, 255, 255, 0.25);
            --glass-border: rgba(255, 255, 255, 0.4);
            --glass-shadow: rgba(0, 0, 0, 0.1);
            --text-primary: rgba(0, 0, 0, 0.85);
            --text-secondary: rgba(0, 0, 0, 0.55);
            --accent: rgba(0, 122, 255, 0.9);
            --accent-light: rgba(0, 122, 255, 0.15);
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', sans-serif;
            min-height: 100vh;
            background: linear-gradient(135deg, #e0e5ec 0%, #f5f7fa 50%, #e8edf5 100%);
            background-attachment: fixed;
            padding: 40px 20px;
            -webkit-font-smoothing: antialiased;
        }}
        
        /* 动态背景光晕 */
        body::before {{
            content: '';
            position: fixed;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: 
                radial-gradient(circle at 20% 20%, rgba(120, 200, 255, 0.3) 0%, transparent 40%),
                radial-gradient(circle at 80% 80%, rgba(200, 150, 255, 0.25) 0%, transparent 40%),
                radial-gradient(circle at 50% 50%, rgba(255, 180, 200, 0.2) 0%, transparent 50%);
            animation: aurora 20s ease-in-out infinite;
            z-index: -1;
        }}
        
        @keyframes aurora {{
            0%, 100% {{ transform: translate(0, 0) rotate(0deg); }}
            33% {{ transform: translate(2%, 2%) rotate(1deg); }}
            66% {{ transform: translate(-1%, 1%) rotate(-1deg); }}
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        /* 标题 */
        .header {{
            text-align: center;
            margin-bottom: 40px;
        }}
        
        h1 {{
            font-size: 2.2rem;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.5px;
        }}
        
        .subtitle {{
            font-size: 0.95rem;
            color: var(--text-secondary);
            margin-top: 8px;
            font-weight: 400;
        }}
        
        /* Glass Card */
        .glass {{
            background: var(--glass-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            box-shadow: 
                0 8px 32px var(--glass-shadow),
                inset 0 1px 0 rgba(255, 255, 255, 0.6);
        }}
        
        /* 统计卡片网格 */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 32px;
        }}
        
        @media (max-width: 900px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        
        @media (max-width: 500px) {{
            .stats-grid {{ grid-template-columns: 1fr; }}
        }}
        
        .stat-card {{
            padding: 24px;
            text-align: center;
            transition: all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
            cursor: default;
        }}
        
        .stat-card:hover {{
            transform: translateY(-4px) scale(1.02);
            box-shadow: 
                0 16px 48px rgba(0, 0, 0, 0.15),
                inset 0 1px 0 rgba(255, 255, 255, 0.8);
        }}
        
        .stat-icon {{
            font-size: 1.5rem;
            margin-bottom: 8px;
            opacity: 0.9;
        }}
        
        .stat-value {{
            font-size: 2.5rem;
            font-weight: 600;
            color: var(--text-primary);
            line-height: 1.1;
        }}
        
        .stat-label {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: 6px;
            font-weight: 500;
        }}
        
        /* 主内容区 */
        .main-section {{
            padding: 28px;
            margin-bottom: 24px;
        }}
        
        .section-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }}
        
        .section-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
        }}
        
        /* Tab 切换 - Pill 风格 */
        .tabs {{
            display: inline-flex;
            background: rgba(0, 0, 0, 0.06);
            border-radius: 10px;
            padding: 3px;
        }}
        
        .tab {{
            padding: 8px 18px;
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-secondary);
            background: transparent;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.25s ease;
        }}
        
        .tab:hover {{
            color: var(--text-primary);
        }}
        
        .tab.active {{
            background: white;
            color: var(--text-primary);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}
        
        /* 图表容器 */
        .tab-content {{
            display: none;
            animation: fadeIn 0.3s ease;
        }}
        
        .tab-content.active {{
            display: block;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .mermaid {{
            display: flex;
            justify-content: center;
            padding: 20px;
            overflow-x: auto;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.5);
        }}
        
        .mermaid svg {{
            max-width: 100%;
        }}
        
        /* Footer */
        footer {{
            text-align: center;
            padding: 24px;
            color: var(--text-secondary);
            font-size: 0.8rem;
        }}
        
        footer a {{
            color: var(--accent);
            text-decoration: none;
        }}
        
        /* Mermaid 主题覆盖 */
        .mermaid .node rect,
        .mermaid .node polygon {{
            fill: rgba(255, 255, 255, 0.8) !important;
            stroke: rgba(0, 0, 0, 0.15) !important;
            stroke-width: 1px !important;
            rx: 8px !important;
        }}
        
        .mermaid .cluster rect {{
            fill: rgba(0, 122, 255, 0.08) !important;
            stroke: rgba(0, 122, 255, 0.2) !important;
            rx: 12px !important;
        }}
        
        .mermaid .nodeLabel {{
            color: var(--text-primary) !important;
            font-family: -apple-system, BlinkMacSystemFont, sans-serif !important;
            font-size: 12px !important;
        }}
        
        .mermaid .cluster-label .nodeLabel {{
            color: var(--accent) !important;
            font-weight: 600 !important;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>{title}</h1>
            <p class="subtitle">AI CodeGen 知识图谱可视化</p>
        </header>
'''
        
        # 添加统计信息
        if include_stats:
            html += '''
        <div class="stats-grid">
            <div class="stat-card glass">
                <div class="stat-icon">📁</div>
                <div class="stat-value">''' + str(stats['parsed_files']) + '''</div>
                <div class="stat-label">已分析文件</div>
            </div>
            <div class="stat-card glass">
                <div class="stat-icon">◆</div>
                <div class="stat-value">''' + str(stats['graph_nodes']) + '''</div>
                <div class="stat-label">代码符号</div>
            </div>
            <div class="stat-card glass">
                <div class="stat-icon">⬡</div>
                <div class="stat-value">''' + str(stats['interfaces']) + '''</div>
                <div class="stat-label">接口定义</div>
            </div>
            <div class="stat-card glass">
                <div class="stat-icon">▤</div>
                <div class="stat-value">''' + str(stats['prd_analyses']) + '''</div>
                <div class="stat-label">PRD 分析</div>
            </div>
        </div>
'''
        
        # 添加图表
        html += f'''
        <div class="main-section glass">
            <div class="section-header">
                <span class="section-title">模块结构</span>
                <div class="tabs">
                    <button class="tab active" onclick="showTab('modules', this)">依赖图</button>
                    <button class="tab" onclick="showTab('classes', this)">类结构</button>
                </div>
            </div>
            
            <div id="modules" class="tab-content active">
                <div class="mermaid">
{module_mermaid}
                </div>
            </div>
            
            <div id="classes" class="tab-content">
                <div class="mermaid">
{class_mermaid}
                </div>
            </div>
        </div>
        
        <footer>
            Powered by AI CodeGen MCP Server
        </footer>
    </div>
    
    <script>
        mermaid.initialize({{ 
            startOnLoad: false,
            theme: 'neutral',
            securityLevel: 'loose',
            flowchart: {{
                curve: 'basis',
                padding: 20
            }}
        }});
        
        // 渲染所有图表
        async function renderAllDiagrams() {{
            const elements = document.querySelectorAll('.mermaid');
            for (const el of elements) {{
                const code = el.textContent;
                el.innerHTML = '';
                try {{
                    const {{ svg }} = await mermaid.render('mermaid-' + Math.random().toString(36).substr(2, 9), code);
                    el.innerHTML = svg;
                }} catch (e) {{
                    el.innerHTML = '<p style="color:red">渲染错误</p>';
                }}
            }}
        }}
        
        // 页面加载完成后渲染
        document.addEventListener('DOMContentLoaded', renderAllDiagrams);
        
        function showTab(tabId, btn) {{
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');
        }}
    </script>
</body>
</html>
'''
        
        return html
    
    def save_html_report(self, file_path: str, title: str = "代码依赖图"):
        """保存 HTML 报告到文件"""
        html = self.generate_html_report(title)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return file_path
