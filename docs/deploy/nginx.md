# Nginx 反向代理（生产）

用于在 TG Manage 容器前终止 TLS，并转发面板与 API 请求。

## 最小配置示例

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream tg_manage {
    server 127.0.0.1:8080;
    keepalive 16;
}

server {
    listen 443 ssl http2;
    server_name panel.example.com;

    # ssl_certificate     /etc/ssl/certs/panel.fullchain.pem;
    # ssl_certificate_key /etc/ssl/private/panel.key;

    client_max_body_size 20m;

    # 默认 API / 静态
    location / {
        proxy_pass http://tg_manage;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
    }

    location = /readyz {
        proxy_pass http://tg_manage;
        access_log off;
    }

    location = /healthz {
        proxy_pass http://tg_manage;
        access_log off;
    }

    # 生产安全加固：屏蔽文档与规范端点探测（纵深防御，可选）
    # location ~ ^/(docs|redoc|openapi\.json) {
    #     return 404;
    # }
}
```

## 注意

- 与 Docker 联用时，将 `upstream` 指到 compose 服务名或宿主机映射端口。
