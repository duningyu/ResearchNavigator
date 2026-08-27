# ADR-0005：MCP 只调用本地 API

- 状态：Accepted

MCP Server 不直接绕过数据库权限或文档安全层，而是用用户 token 调用 API。这样 Web 与 MCP 共享主张、版权、用户隔离和错误规则。缺点是需要运行 API 和管理 user-scoped token。
