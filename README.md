# Kimi API Dashboard

本地透明代理 + 看板，用于观察 Claude Code 调用 Kimi API 的全过程。

## 访问地址

- **看板 UI**：http://localhost:8788/
- **代理端口**：http://localhost:8787/

## 快速启动

### 方式一：本地直接运行

```bash
cd backend
uv run python src/main.py
```

### 方式二：Docker（推荐）

确保 `.env` 文件已配置好（API Key 等）。然后：

```bash
docker-compose up --build -d
```

停止：

```bash
docker-compose down
```

查看日志：

```bash
docker-compose logs -f
```

服务会同时启动两个端口：
- `8787`：透明代理，转发到 Kimi API
- `8788`：看板，展示请求列表和指标

## Claude Code 配置

把 `ANTHROPIC_BASE_URL` 从 `https://api.kimi.com/coding/` 改成：

```bash
ANTHROPIC_BASE_URL=http://localhost:8787/
```

API Key 保持不变（代理会原样转发 `Authorization` 头）。

## 功能

- 透明转发所有请求到 Kimi API，不修改语义
- 完整记录每一次请求和响应到 `data/requests-*.jsonl`
- 实时 WebSocket 推送新请求到看板
- 解析 Anthropic `/v1/messages` 的 token 用量（含 cache token）
- 数据目录超过 20GB 自动删除最老的分片

## 项目结构

```
.
├── backend/
│   └── src/
│       ├── main.py           # 双端口启动入口
│       ├── proxy.py          # 透明代理
│       ├── dashboard_api.py  # 看板 REST API
│       ├── dashboard_ws.py   # WebSocket 广播
│       ├── storage.py        # JSONL 分片管理
│       ├── parser.py         # Anthropic 响应解析
│       └── config.py         # 配置
├── frontend/
│   └── dist/                 # 构建后的看板前端
├── data/                     # JSONL 数据目录（自动创建）
├── .env                      # API Key 等配置（已加入 gitignore）
├── Dockerfile                # Docker 镜像构建
├── docker-compose.yml        # Docker Compose 配置
├── run.sh                    # 本地启动脚本
└── DESIGN.md                 # 设计文档
```

## 重新构建前端

```bash
cd frontend
npm install
npm run build
```

## 说明

- JSONL 中保存了完整请求头（包括 `Authorization`）和请求体，请妥善保管，不要共享。
- 当前为单进程单 worker 实现，适合个人本地使用。
