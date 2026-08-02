# Golf Mate

高尔夫伙伴应用 — **从空白状态开始**，按需求迭代开发。

## 技术栈

- React 19 + TypeScript
- Vite 8

## 本地开发

```bash
cd golf-mate
npm install
npm run dev
```

浏览器打开终端提示的本地地址（默认 `http://localhost:5173`）。

## 项目结构

```
golf-mate/
├── src/
│   ├── App.tsx          # 应用入口页（空白起点）
│   ├── components/      # UI 组件（待建）
│   ├── features/        # 业务功能（待建）
│   └── pages/           # 页面（待建）
├── docs/
│   └── PRD.md           # 产品需求（待补充）
└── package.json
```

## 开发约定

- 当前为 **空状态骨架**：可运行、无业务功能
- 新功能通过 PRD → 任务拆分 → 实现 → 验证 的流程推进
