# Golf Mate

高尔夫腕部 AI 助手 — 算法核心 + Apple Watch 全速采集 E2E 验证版。

## 目录

```
golf-mate/
├── algo/                 # Python 算法包（P0，可严格 UT）
│   ├── golfmate_algo/
│   ├── tests/
│   └── README.md
├── docs/
│   ├── PRD.md
│   └── research/         # 行业 / 学术 / 开源调研归档
├── apple/                # watchOS 800/200 Hz 采集 + iPhone 可靠传输
├── src/                  # 前端空骨架（本轮不扩展）
└── package.json
```

## 算法快速开始

```bash
cd algo
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

详见 [`algo/README.md`](algo/README.md) 与 [`docs/research/00_synthesis.md`](docs/research/00_synthesis.md)。

## Apple Watch 验证版

```bash
cd apple
brew install xcodegen
./scripts/regenerate_xcode.sh
open GolfAiJing.xcodeproj
```

不要打开旧的 `GolfMate.xcodeproj`（若本地还在，先删掉）。需 Series 8 / Ultra 或更新真机。详见 [`apple/README.md`](apple/README.md) 与
[`docs/PRD_APPLE_WATCH.md`](docs/PRD_APPLE_WATCH.md)。

## 前端骨架（未改产品功能）

```bash
npm install
npm run dev
```

## 能力分层

- **P0（已完成）**：门控 AHRS → 相位 → 轨迹 → 腕部特征 → 代理诊断 + UT
- **Watch E2E（验证版）**：800 Hz ACC + 200 Hz Motion → iPhone → 原算法
- **P1**：单腕→全身、真实数据集回归
- **P2**：运动签名、前向动力学教师信号
