# BugFix: 项目列表页面"无法连接后端服务"错误

## 日期

2026-05-17

## 问题描述

通过 `start.bat` 启动项目后，浏览器打开项目列表页面显示：

```
加载失败：无法连接后端服务：http://127.0.0.1:8000
```

## 根因分析

前端 JS 打包时（`backend/static/assets/index-dDm-Gfk4.js`）将 API 基础地址硬编码为 `http://127.0.0.1:8000`：

```js
Vn = "http://127.0.0.1:8000"   // API 基地址，用于所有 fetch 请求
```

而 `start.bat` 启动后打开浏览器访问的是 `http://localhost:8000`。

浏览器安全策略将 `localhost` 和 `127.0.0.1` 视为**不同源**（different origins），导致：

1. 页面从 `http://localhost:8000` 加载
2. JS 向 `http://127.0.0.1:8000/api/projects` 发起请求
3. 浏览器判定为跨域请求
4. CORS 中间件只允许了 `localhost:5173` / `127.0.0.1:5173`（Vite 开发端口），拒绝 8000 端口的来源
5. `fetch()` 抛出 `TypeError: Failed to fetch`
6. 前端捕获后显示"无法连接后端服务"

## 修改内容

### 1. `.env` — CORS 允许来源追加 8000 端口

```
# 修改前
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# 修改后
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000
```

### 2. `.env.example` — 同步更新（供新环境参考）

同上。

### 3. `start.bat` — 浏览器打开地址与 JS 硬编码对齐

| 位置 | 修改前 | 修改后 |
|------|--------|--------|
| 第 152 行 echo 提示 | `http://localhost:8000` | `http://127.0.0.1:8000` |
| 第 153 行 echo 提示 | `http://localhost:8000/docs` | `http://127.0.0.1:8000/docs` |
| 第 160 行 start 命令 | `http://localhost:8000` | `http://127.0.0.1:8000` |

## 原理说明

双保险策略：

- **CORS 放行**（`.env`）：即使未来通过 `localhost` 访问，跨域请求也不会被拦截
- **URL 对齐**（`start.bat`）：浏览器地址与 JS 硬编码地址一致，属同源请求，无需触发 CORS 流程，彻底消除隐患
