# DNS for AI Discovery (DNS-AID)

只有在你控制文档站域名时才需要配置 DNS。下面以 `docs.example.com` 为示例；将其替换为你实际拥有的域名。

## 推荐记录（HTTPS / SVCB）

先确认站点已在该域名可访问，再添加发现记录。

```text
; 索引入口：指向文档站根
_index._agents.docs.example.com. 3600 IN HTTPS 1 docs.example.com. alpn="h2,h3" port=443

; MCP / 文档发现入口
_mcp._agents.docs.example.com. 3600 IN HTTPS 1 docs.example.com. alpn="h2,h3" port=443

; 可选 TXT 索引（部分解析器回退）
_index._agents.docs.example.com. 3600 IN TXT "https://docs.example.com/.well-known/agent-skills/index.json"
_index._agents.docs.example.com. 3600 IN TXT "https://docs.example.com/.well-known/mcp/server-card.json"
```

若提供商不支持 HTTPS 记录类型，可改用 SVCB：

```text
_index._agents.docs.example.com. 3600 IN SVCB 1 docs.example.com. alpn="h2,h3" port=443
```

## DNSSEC

公开发现区建议开启 DNSSEC，以便验证解析器返回经认证数据。Cloudflare / 多数 DNS 托管可一键启用。

## 验证

```bash
# DNS-over-HTTPS 查询示例（Cloudflare）
curl -sG 'https://cloudflare-dns.com/dns-query' \
  --data-urlencode 'name=_index._agents.docs.example.com' \
  --data-urlencode 'type=HTTPS' \
  -H 'accept: application/dns-json' | jq .

# 或重新扫描
curl -s https://isitagentready.com/api/scan \
  -H 'content-type: application/json' \
  -d '{"url":"https://docs.example.com"}' | jq '.checks.discoverability.dnsAid'
```

## 说明

- 本页仅运维指引，不参与站点构建产物。
- 无 DNS 写权限时，其余 Agent 发现项（robots / sitemap / well-known / Link 头）仍可独立通过。
