# ADR-0001：React Web 与 FastAPI 分离

- 状态：Accepted
- 日期：2026-08-26

## 决策

React/TypeScript 负责交互，FastAPI 负责认证、证据、外部源、持久化和工作流。Nginx 在部署中代理 `/api`。

## 理由

API 可被 Web、MCP 和后续 CLI 复用；密钥不进入浏览器；用户隔离集中实施。

## 后果

增加两个依赖生态和 CORS/构建复杂度。必须分别执行后端和前端验证。
