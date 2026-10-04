# 2C2G 多账号容量实测

这里的“容量”指**已授权账号在目标服务器上可持续使用**：面板保持健康、没有 OOM，并且开启 TeleBox 时每个账号的独立 Node 进程都在运行。仅把 session 文件存入面板并不等于账号一直在线；不开 TeleBox 时，Python Telegram 客户端通常按操作建立连接，用完后释放。因此还要在每个测试档位执行平时会用到的账号检查、任务和聊天操作。

这不是“同一秒发起多少个验证码或扫码登录”的测试。登录流程有独立的频率限制和待验证会话上限，不能用突发授权请求来推算长期可用账号数。

必须在目标机器上运行，使用同一批**本人可授权的真实账号**分别测量关闭、开启 TeleBox。不要复制同一个 session 文件充数；那不会产生独立的 Telegram 连接。不要在生产账号上集中请求登录验证码。这里的采样脚本只读资源指标，不登录账号，也不改变 TeleBox 状态。

## 准备

1. 在已部署本仓库的服务器进入项目目录，确认 `docker compose ps` 正常。Compose 的 `app` 服务默认限制为 2 CPU、2 GiB。
2. 在面板登录一批可用于测试的真实账号。每档增加账号后等待连接和任务稳定，再运行采样。关闭档需确认所有 TeleBox 工作进程已停；开启档需确认每个账号 TeleBox 已完成独立授权且状态为 `running`。
3. 尽量保持插件、代理、任务频率及聊天流量与实际使用相同。两组测试使用相同账号和负载。采样至少 15 分钟，目标档再做 24 小时观察，以覆盖定时任务和内存增长。

## 采样

以下示例以已登录 `N=5` 个账号为例。命令里的 `--accounts` 和 `--expected-workers` 要填实际值。工具从容器内的 cgroup v2 读取限额、内存、CPU、OOM 事件以及 TeleBox 工作进程数，只输出汇总数字，不读取或打印账号凭据。

```bash
# 关闭这 5 个账号的 TeleBox，确认它们都已停止后执行
docker compose exec -T app python -u - --phase off --accounts 5 --expected-workers 0 --duration 900 < tools/capacity_probe.py | tee off-5.jsonl

# 同一批账号开启 TeleBox，全部显示 running 后执行
docker compose exec -T app python -u - --phase on --accounts 5 --expected-workers 5 --duration 900 < tools/capacity_probe.py | tee on-5.jsonl
```

按 1、2、5、10……逐步增加真实账号，到接近资源上限时每次只加 1 个。每档同时做正常的账号状态检查、任务和聊天操作；观察登录成功率、响应时间、连接中断和 Telegram 错误。脚本自身的 `/readyz` 探测只说明面板存活，不能代替业务验证。

每个文件最后一行 `type=summary` 包含 `memory_peak_mib`、`working_set_peak_mib`、`cpu_p95_cores`、`oom_kill_delta`、`ready_all` 和 `workers_all_expected`。`memory_peak_mib` 包括容器缓存，是 2 GiB 限额与 OOM 的直接观察值；`working_set_peak_mib` 扣除了可回收的 inactive file，便于比较账号增量。即使汇总退出码为 0，也只是采样期间没有检测到 OOM、健康检查失败或工作进程缺失，**不代表已找到最大容量**。

如果容器因 OOM 被终止，采样可能来不及写出最后一行；应结合 `docker compose ps`、`docker inspect tg-signpulse --format '{{.State.OOMKilled}}'` 和容器日志确认，不要把缺少 summary 当作通过。

比较两种模式时，用同一账号数的 `off-N` 与 `on-N` 数据；每种模式能稳定通过的最高**实际测试档位**才是已验证数。达到内存约 80%（约 1.6 GiB）或 CPU 长期接近 2 核时应放慢增量；OOM、健康失败、TeleBox 进程掉线或业务错误出现时停止增加，回退到前一稳定档，并留出插件波动及定时峰值余量。不同插件的内存和 CPU 开销不同，不应从一两个账号的平均值线性外推“最多可登录 X 个”。

向协作者提供 `off-*.jsonl` 和 `on-*.jsonl` 即可分析；文件不包含 session、手机号或 API 密钥，但在分享前仍可检查内容。若容器不是 cgroup v2 或资源限额不是 2C2G，脚本会拒绝作为目标环境运行。
