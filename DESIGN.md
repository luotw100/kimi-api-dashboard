# Kimi API 调用看板设计文档

## 1. 目标

为 Claude Code（当前使用 Kimi API）构建一个本地调用看板，满足：

- **L7 透明转发**：只观察、记录、转发，不修改请求和响应语义。
- **Source of Truth**：JSONL 分片文件完整保存每一次 API 调用过程。
- **双端口**：代理端口只负责透明转发；看板端口独立提供 UI/API/WebSocket。
- **体积循环删**：数据目录超过 20GB 后，删除最老的分片，直到低于 20GB。
- **实时**：WebSocket 推送新请求事件。
- **初期只支持 Anthropic 协议**：核心路径 `/v1/messages`；其余路径仅做原始记录。

## 2. 总体架构

```text
Claude Code
    │
    │  http://localhost:8787/v1/...
    ▼
┌─────────────────────────────────────┐
│  Python + FastAPI + uvicorn         │
│  单进程服务（个人使用，暂不考虑多 worker）│
│                                     │
│  ┌─ 端口 8788: Dashboard            │
│  │    ├─ /           React 静态资源 │
│  │    ├─ /api/*      查询 JSONL 数据 │
│  │    └─ /ws          WebSocket 推送 │
│  │                                  │
│  └─ 端口 8787: 透明代理             │
│       └─ /*          流式转发到 Kimi│
│                      + 异步写入 JSONL│
│                      + 异步 WS 广播 │
└──────────────┬──────────────────────┘
               │ HTTPS
               ▼
    https://api.kimi.com/coding
```

## 3. 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端 | Python 3.12 + FastAPI + uvicorn | 同时处理代理、API、WebSocket、静态文件 |
| HTTP Client | httpx | 异步流式转发到上游 |
| 包管理 | uv | 你要求的 |
| 数据存储 | 分片 JSONL | 完全保存 API 调用过程，作为 source of truth |
| 前端 | React 18 + TypeScript + Vite | 引入框架 |
| 样式 | Tailwind CSS | 快写 UI |
| 图表 | Recharts | React 生态，够用 |
| 部署 | Docker + Docker Compose | 单容器即可 |

## 4. 双端口路由

| 端口 | 路径 | 说明 |
|------|------|------|
| 8787 | `/*` | 所有请求原样转发到 Kimi API |
| 8788 | `/` | 看板首页（React 路由入口） |
| 8788 | `/*` | 看板静态资源，`html=True` fallback 到 `index.html` |
| 8788 | `/api/health` | 健康检查 |
| 8788 | `/api/requests` | 请求列表（分页/过滤） |
| 8788 | `/api/requests/{id}` | 单个请求详情 |
| 8788 | `/api/metrics` | 聚合指标 |
| 8788 | `/ws` | WebSocket 实时通道 |

Claude Code 只需要配置：
```bash
ANTHROPIC_BASE_URL=http://localhost:8787/
```

浏览器访问看板：
```text
http://localhost:8788
```

## 5. 数据模型：分片 JSONL

### 5.1 记录结构

每一行一个 JSON 对象，完整保存一次 API 调用：

```json
{
  "id": "req_xxx",
  "timestamp": "2026-07-15T09:00:00.000Z",
  "method": "POST",
  "path": "/v1/messages",
  "model": "kimi-for-coding",
  "request": {
    "headers": { "authorization": "Bearer sk-...", "anthropic-version": "2023-06-01" },
    "body": { "model": "kimi-for-coding", "messages": [...], "max_tokens": 100, "stream": true }
  },
  "response": {
    "status": 200,
    "headers": { "content-type": "text/event-stream" },
    "body": "data: {...}\n\ndata: {...}\n\ndata: [DONE]\n\n"
  },
  "parsed": {
    "input_tokens": 120,
    "output_tokens": 450,
    "total_tokens": 570,
    "duration_ms": 1234,
    "ttfb_ms": 890,
    "is_streaming": true,
    "stop_reason": "end_turn",
    "error": null
  }
}
```

### 5.2 字段说明

| 字段 | 说明 |
|------|------|
| `id` | 请求 UUID，由代理生成 |
| `timestamp` | 请求开始时间（ISO 8601） |
| `method` / `path` | HTTP 方法和路径 |
| `model` | 从请求体解析出的模型名 |
| `request.headers` | 请求头（原始保存，包括 Authorization） |
| `request.body` | 请求体完整 JSON |
| `response.status` / `response.headers` | 上游响应状态与头部 |
| `response.body` | 响应体完整内容；SSE 流保存原始 SSE 字符串 |
| `parsed.*` | 解析后的派生字段：token 用量、耗时、是否流式、错误信息 |

### 5.3 分片策略

- 数据目录：`data/`
- 活跃文件：`data/requests-active.jsonl`（持续追加）
- 当活跃文件达到 **256MB** 时，关闭并重命名为 `data/requests-YYYYMMDDTHHMMSS-XXXXXX.jsonl`，例如 `data/requests-20260715T090000-000001.jsonl`。
- 新请求继续写入新的 `requests-active.jsonl`。
- 文件按创建时间自然有序，老文件时间戳小，新文件时间戳大。

这种分片方式让“删除最老记录”等价于“删除最老的分片文件”，无需重写整个数据集。

## 6. 体积循环删除（20GB）

- 后台任务每 **10 分钟** 检查 `data/` 目录总大小。
- 如果总大小 > **20GB**：
  - 找出最老的分片文件（按时间戳排序）。
  - 删除该文件。
  - 重复直到总大小 < 20GB。
- `requests-active.jsonl` 正在写入，不参与删除。
- 由于删除的是 256MB 的整数文件，实际大小会略小于 20GB（可能 19.75GB 左右），随后继续上涨到 20.25GB 左右再次触发删除，符合“常态略微大于 20G”的预期。
- 20GB 和 256MB 为硬编码值，无需配置。

### 删除与并发读

个人使用场景下，删除操作与看板读取同时发生的概率极低。实现上会采取简单策略：删除前检查文件是否被占用，或先重命名为 `.deleted` 后再真正删除，避免读取到一半文件消失。

## 7. Anthropic 协议解析

只针对 `/v1/messages` 做深度解析，其余路径原样记录但不解析 `parsed`。

- 非流式响应：直接读取 `response.body` 中的 `usage` 和 `stop_reason`。
- 流式响应（SSE）：保存原始 SSE 字符串，解析各事件类型中的 `usage` 字段。
- 具体解析逻辑以实际 Kimi API 返回的响应结构为准，不预先猜测 event 类型和字段位置。

### 错误处理

- 如果响应状态 >= 400，记录 `parsed.error` 为错误信息。
- 如果解析失败，记录 `parsed.error` 为解析错误，但原样保存 `response.body`。
- 如果 SSE 流中出现错误事件，也记录 `parsed.error`。

## 8. 代理流程

1. 收到请求，生成 `request_id`，记录开始时间。
2. 异步读取请求体（使用 `request.stream()` 避免阻塞）。
3. 将请求转发到 `https://api.kimi.com/coding`（保持方法、路径、头部、请求体不变）。
4. 收到上游首字节时记录 `ttfb_ms`。
5. 边流式返回给客户端，边把响应内容拼接成完整 `response.body`。
6. 响应结束后记录 `duration_ms`。
7. 根据实际响应结构解析 token 用量（Anthropic 协议）。
8. 将完整记录追加到 `data/requests-active.jsonl`。
9. 异步广播 WebSocket 事件（携带摘要，不包含完整请求体）。

写 JSONL 和 WebSocket 广播都走后台任务，不阻塞响应流。

## 9. 看板 API

| 端点 | 说明 | 参数 |
|------|------|------|
| `GET /api/health` | 健康检查 | - |
| `GET /api/requests` | 请求列表 | `limit`, `offset`, `before`, `after`, `model`, `path`, `status` |
| `GET /api/requests/{id}` | 单个请求 | - |
| `GET /api/metrics` | 聚合指标 | `window`（最近 N 分钟） |

实现方式：从最新分片往最老分片扫描，直到满足 `limit` 或 `window`。

## 10. WebSocket

- 端点：`/ws`（看板端口 8788）
- 每个请求完成后广播一个摘要事件：

```json
{
  "type": "request_finished",
  "payload": {
    "id": "req_xxx",
    "timestamp": "2026-07-15T09:00:00.000Z",
    "model": "kimi-for-coding",
    "path": "/v1/messages",
    "status": 200,
    "duration_ms": 1234,
    "ttfb_ms": 890,
    "input_tokens": 120,
    "output_tokens": 450
  }
}
```

看板连接后：
1. 先拉 `/api/requests?limit=100` 和 `/api/metrics` 初始化。
2. 订阅 `/ws`，新请求到达时追加到表格和图表。
3. 前端实现自动重连，重连后拉取缺失数据。

## 11. 前端设计

单页看板，布局：

```text
┌────────────────────────────────────────────────────────────┐
│  Kimi API Dashboard                               [WS: 🟢]  │
├────────────────────────────────────────────────────────────┤
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐           │
│  │ 总请求 │  │ 总token│  │ 平均延迟│  │ 错误率  │           │
│  └────────┘  └────────┘  └────────┘  └────────┘           │
├────────────────────────────────────────────────────────────┤
│  [每分钟请求数]        [每分钟 input/output token]           │
│  [延迟 p50/p95 趋势]                                       │
├────────────────────────────────────────────────────────────┤
│  [模型分布]  │  [最近错误]                                  │
├────────────────────────────────────────────────────────────┤
│  最近请求列表                                               │
│  时间 | 模型 | 路径 | 状态 | 耗时 | input | output | 详情     │
└────────────────────────────────────────────────────────────┘
```

详情抽屉分四页：
- Request：headers + body
- Response：headers + body（SSE 可折叠）
- Usage：token 用量
- Timing：总耗时 / TTFB

## 12. Docker 与部署

单容器镜像：

- 多阶段构建：先用 Node 构建前端 `dist/`，再复制到 Python 镜像。
- Python 镜像使用 `uv` 安装依赖。
- 启动命令：`uv run python main.py`
- `main.py` 内部启动两个端口：8787（代理）和 8788（看板）。
- `docker-compose.yml` 挂载 `data/` 目录到宿主机，防止容器重启丢数据。
- 端口映射：
  - `8787:8787`（代理端口）
  - `8788:8788`（看板端口）

Claude Code 配置：
```bash
ANTHROPIC_BASE_URL=http://localhost:8787/
```

浏览器访问看板：
```text
http://localhost:8788
```

注意：如果 Claude Code 在 Docker 容器内运行，而代理在宿主机上，需要使用 `host.docker.internal` 或 `--network host`。

## 13. 安全与边界

- **无鉴权**：本地使用，默认绑定 `127.0.0.1`。
- **日志敏感**：JSONL 中保存了完整请求体，可能包含源代码、Authorization 等。请妥善保管，不要共享。
- **磁盘**：你要求全量存储，不限制磁盘。体积循环删在 20GB 触发。
- **性能**：JSONL 扫描在 20GB 量级下，启动或全量查询可能有几秒延迟。后续如需优化，可引入按小时聚合的 `metrics.jsonl`，但那是性能优化，不是 source of truth。
- **单进程**：当前为单进程单 worker，个人使用足够，暂不考虑多 worker。

## 14. 未完全确定的事项

| 项目 | 当前选择 | 备注 |
|------|----------|------|
| 分片大小 | 256MB | 硬编码 |
| 体积检查周期 | 10 分钟 | 硬编码 |
| 体积阈值 | 20GB | 硬编码 |
| 图表库 | Recharts | 可换成 uPlot |
| 前端路由 | React Router | 简单 hash 或 memory 路由也可 |
| 是否推送请求开始事件 | 否 | 只推送完成事件 |

## 15. 核心原则重申

- **JSONL 分片是唯一的 source of truth。**
- 看板、API、WebSocket 都只读取 JSONL。
- 代理只转发、记录，不修改业务数据。
- 初期只深度解析 Anthropic `/v1/messages`，其余路径原样记录。
