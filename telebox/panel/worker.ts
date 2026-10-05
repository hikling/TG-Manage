/** SignPulse integration adapter. Original runtime/TPM remain authoritative. */
import fs from "node:fs";
import readline from "node:readline";
import util from "node:util";

process.umask(0o077);
const protocolWrite = process.stdout.write.bind(process.stdout);
const emit = (event: Record<string, unknown>) => protocolWrite(JSON.stringify(event) + "\n");
// Reserve stdout for framed IPC; runtime output is bounded/redacted by parent.
for (const level of ["log", "info", "warn", "error", "debug"] as const) {
  console[level] = (...args: unknown[]) => process.stderr.write(util.format(...args).slice(0, 8192) + "\n");
}
let passwordResolve: ((value: string) => void) | undefined;
let initialized = false;
let stop = false;
let queue = Promise.resolve();
let privateValues: string[] = [];
function safeError(error: unknown): string {
  let value = error instanceof Error ? error.message : String(error);
  for (const secret of privateValues) if (secret) value = value.split(secret).join("[REDACTED]");
  return value.replace(/[A-Fa-f0-9]{32,}|[A-Za-z0-9+/=_-]{80,}/g, "[REDACTED]").replace(/\+?\d{10,15}/g, "[REDACTED]").slice(0, 180);
}
function initializeRuntimeServices() {
  // Mirror upstream src/index.ts bootstrap. Without dotenv the account's
  // plugin configuration is ignored, and HTTP plugin actions bypass its proxy.
  require("dotenv/config");
  require("../src/utils/logger");
  require("../src/utils/coreDumpCleaner").cleanCoreDumps();
  const proxyValue = process.env.HTTPS_PROXY || process.env.https_proxy || process.env.HTTP_PROXY || process.env.http_proxy;
  if (proxyValue) {
    const url = new URL(proxyValue);
    if (url.protocol === "http:" || url.protocol === "https:") {
      require("axios").defaults.proxy = {
        host: url.hostname,
        port: Number(url.port || (url.protocol === "https:" ? 443 : 80)),
        protocol: url.protocol.slice(0, -1),
        ...(url.username ? { auth: { username: decodeURIComponent(url.username), password: decodeURIComponent(url.password) } } : {}),
      };
    }
  }
}
process.on("unhandledRejection", (reason) => console.error("[WARN] Unhandled promise rejection:", safeError(reason)));
process.on("uncaughtException", (error) => console.error("[ERROR] Uncaught exception:", safeError(error)));
async function shutdown(code = 0) {
  if (stop) return;
  stop = true;
  try { if (initialized) await require("../src/utils/runtimeManager").shutdownRuntime(); }
  finally { process.exit(code); }
}
process.on("SIGTERM", () => void shutdown());
process.on("SIGINT", () => void shutdown());

async function initialize(input: any) {
  if (initialized) throw new Error("already initialized");
  initialized = true;
  stage = "依赖加载";
  // The bundled TeleBox runtime and teleproto are CommonJS. Use the same
  // resolver as upstream; ESM rejects directory imports such as sessions.
  const { TelegramClient } = require("teleproto");
  const { StringSession } = require("teleproto/sessions");
  const old = fs.existsSync("config.json") ? JSON.parse(fs.readFileSync("config.json", "utf8")) : {};
  privateValues = [String(input.api_hash || ""), String(old.session || ""), String(input.proxy?.password || "")];
  const config = { ...old, api_id: input.api_id, api_hash: input.api_hash, proxy: input.proxy || undefined };
  fs.writeFileSync("config.json", JSON.stringify(config), { mode: 0o600 });
  const client = new TelegramClient(new StringSession(old.session || ""), input.api_id, input.api_hash, {
    connectionRetries: 3, deviceModel: "SignPulse TeleBox", proxy: config.proxy,
  });
  try {
    stage = "连接 Telegram";
    await client.connect();
    if (!(await client.checkAuthorization())) {
      stage = "独立会话授权";
      await client.signInUserWithQrCode({ apiId: input.api_id, apiHash: input.api_hash }, {
        qrCode: async ({ token }: { token: Buffer }) => { emit({ event: "login_token", token: token.toString("base64") }); },
        password: async () => {
          emit({ event: "state", status: "password_required" });
          return new Promise<string>((resolve, reject) => {
            const timer = setTimeout(() => { passwordResolve = undefined; reject(new Error("password timeout")); }, 180000);
            passwordResolve = (value) => { clearTimeout(timer); passwordResolve = undefined; resolve(value); };
          });
        },
        onError: async () => false,
      });
    }
    config.session = (client.session as InstanceType<typeof StringSession>).save();
    fs.writeFileSync("config.json", JSON.stringify(config), { mode: 0o600 });
  } finally { await client.destroy(); }
  stage = "加载插件";
  initializeRuntimeServices();
  const { initPluginBaseConfig } = require("../src/utils/pluginBase");
  initPluginBaseConfig();
  require("../src/hook/patches/telegram.patch");
  stage = "启动运行时";
  await require("../src/utils/runtimeManager").startRuntime();
  stage = "运行中";
  emit({ event: "state", status: "running" });
}
async function logout(): Promise<boolean> {
  const { getGlobalClient } = require("../src/utils/runtimeAccess");
  const client = await getGlobalClient();
  return await client.logOut();
}
const input = readline.createInterface({ input: process.stdin, terminal: false });
let stage = "初始化";
input.on("close", () => void shutdown());
input.on("line", (line) => {
  if (line.length > 65536) return;
  let command: any;
  try { command = JSON.parse(line); } catch { return; }
  if (command.action === "password") { passwordResolve?.(String(command.password || "")); return; }
  queue = queue.then(async () => {
    try {
      let revoked: boolean | undefined;
      if (command.action === "init") await initialize(command);
      else if (command.action === "logout") revoked = await logout();
      else throw new Error("invalid command");
      emit({ event: "result", id: command.id, ok: true, ...(revoked === undefined ? {} : { revoked }) });
    } catch (error) {
      // Error objects can contain login secrets; emit a bounded safe category only.
      const category = error instanceof Error ? error.name : "Error";
      const detail = safeError(error);
      console.error("TeleBox operation failed", stage, category, detail);
      emit({ event: "result", id: command.id, ok: false, message: `TeleBox ${stage}失败（${category}）：${detail}` });
      if (command.action === "init") { emit({ event: "state", status: "failed" }); await shutdown(1); }
    }
  });
});
