# TG Manage API 认证

本文面向需要访问自托管 TG Manage API 的客户端。面板使用本地管理员账号和 JWT Bearer 认证；公开文档站本身无需登录。

## 获取访问令牌

首次部署后，运行 `bash scripts/install.sh`，用一次性设置码在网页创建管理员密码。后续客户端使用同一账号调用登录接口：

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "<password>"
}
```

启用 TOTP 时还需提交 `totp_code`。成功响应包含 `access_token`，后续请求使用 `Authorization: Bearer <access_token>`。请勿把密码或 JWT 提交到公共仓库。

面板没有第三方 OAuth 客户端动态注册功能。具体 API 以当前部署的服务端路由为准；OpenAPI 文档仅在启用 `ENABLE_API_DOCS` 时可访问。

源码：[hikling/TG-Manage](https://github.com/hikling/TG-Manage)。
