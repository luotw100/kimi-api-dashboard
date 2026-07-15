# Multi-stage build using locally available base images

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install --production=false --registry=https://registry.npmmirror.com

COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim

WORKDIR /app

# 使用阿里云 PyPI 镜像安装 uv
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ uv

# Copy backend files to /app/backend to mirror project structure
COPY backend/pyproject.toml ./backend/
COPY backend/README.md ./backend/
COPY backend/src ./backend/src

# Install Python dependencies (also use Aliyun mirror)
RUN uv pip install --system -i https://mirrors.aliyun.com/pypi/simple/ ./backend

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8787 8788

CMD ["python", "backend/src/main.py"]
