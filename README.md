# Kimi API Dashboard

本地透明代理 + 看板，用于观察 Claude Code 调用 Kimi API 的全过程。

> 本仓库仅支持 Docker 方式运行，不维护本地开发环境。

## 访问地址

- **看板 UI**：http://localhost:8788/
- **代理端口**：http://localhost:8787/

## 快速启动

1. 复制环境变量模板并填入你的 API Key：

```bash
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY
```

2. 启动服务：

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
- 完整记录每一次请求和响应到 `data/requests-*.jsonl`，包括代理失败（502）的请求
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
│   ├── src/                  # 看板前端源码
│   └── dist/                 # 构建后的看板前端（由 Dockerfile 生成）
├── data/                     # JSONL 数据目录（自动创建）
├── .env                      # API Key 等配置（已加入 gitignore）
├── Dockerfile                # Docker 镜像构建
├── docker-compose.yml        # Docker Compose 配置
└── README.md                 # 本文件
```

## 说明

- JSONL 中保存了完整请求头（包括 `Authorization`）和请求体，请妥善保管，不要共享。
- 当前为单进程单 worker 实现，适合个人本地使用。
- 前端构建由 Dockerfile 自动完成，无需在本地执行 `npm install` / `npm run build`。
