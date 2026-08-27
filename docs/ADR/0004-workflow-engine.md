# ADR-0004：显式 Python 状态机而非 LangGraph

- 状态：Accepted

V2 当前只有可枚举节点和关键确认门，使用路由+域函数+数据库状态更透明。LangGraph 仅在多分支、中断恢复和并行工具调用变成稳定需求时引入。普通 CRUD 永不包装成 Agent。
