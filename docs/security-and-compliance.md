# 安全、隐私与合规

## 1. 认证

- PBKDF2-HMAC-SHA256 + 随机 salt；
- opaque session token；数据库只存 SHA256；
- token 有过期和撤销时间；
- API Bearer；
- 当前没有密码重置和 2FA，公网部署前必须补足。

## 2. 用户隔离

项目、档案、收藏、笔记、标签、阅读状态、上传、分析、gap、计划、任务和审计均按 user_id。任何按 ID 获取的用户资源必须同时过滤 user_id；集成测试覆盖跨用户拒绝。

## 3. API Key

- 仅服务端 `.env`；
- 前端不接收；
- 日志脱敏；
- `.env.example` 为空值；
- 源健康页只显示 configured boolean，不回传 key；
- 正式部署建议 secrets manager 或只读环境文件。

## 4. PDF

- 用户确认有权使用；
- `.pdf`、MIME、magic、大小和安全文件名；
- 文件按 user/paper/SHA256 存储；
- 不执行 PDF 内脚本或附件；
- PyPDF 文本解析不是恶意文档沙箱，生产应增加容器隔离、反病毒和资源限制；
- 当前无 OCR。

## 5. SSRF

文档安全模块拒绝 loopback、private、link-local、保留地址和非 HTTP(S)；MCP 上传只允许指定本地根目录。当前 API 不实现任意 URL fetch。

## 6. 版权

- 元数据和摘要按各源条款使用；
- 公开链接不等于全文许可；
- 不模拟出版社登录；
- 不绕过付费墙；
- 不批量下载受限全文；
- 删除本地文档不声称删除出版商副本。

## 7. 日志与数据最小化

禁止记录：密码、完整 token、API Key、受限全文、未脱敏请求头。AgentRun 应保存必要 query/tool/output hash；大段全文只保存文档表和 chunk，不复制到日志。

## 8. 部署

局域网 HTTP 仅适合可信网络。公网必须：HTTPS、反向代理、CSRF/CORS 审计、速率限制、密码策略、2FA/SSO、漏洞扫描、备份加密和隐私政策。

## 2.2 远程 OA PDF 与 Provider 安全

- OA resolver 只处理公开标识符和公开入口；不携带用户 cookie、机构代理凭据或浏览器 session；
- 每个 redirect hop 都重新解析 DNS 并拒绝 private/loopback/link-local/reserved IP；
- URL 中的 userinfo 被拒绝；重定向次数和下载字节数有硬上限；
- 同时验证 `Content-Type` 和 `%PDF-` magic，拒绝 HTML 登录页与错误页；
- 保存内容 SHA256、响应元数据哈希、来源 URL、license/rights basis 与 run ID；
- LLM/API key 只从服务端环境读取；`AgentRun`/`ToolCall` 只保存 provider/model/prompt、输入标识/哈希、输出哈希、延迟和 token usage，不保存 Authorization；
- Admin 浏览器接口只返回“是否配置”布尔值和 provider/prompt 名称，不返回密钥；
- 历史摘要回填默认 dry-run，且只允许管理员启动；跨用户论文/项目访问在外部调用前拒绝。
