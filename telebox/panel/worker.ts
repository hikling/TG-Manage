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
async function shutdown() {
  if (stop) return;
  stop = true;
  try { if (initialized) await (await import("../src/utils/runtimeManager")).shutdownRuntime(); }
  finally { process.exit(0); }
}
process.on("SIGTERM", () => void shutdown());
process.on("SIGINT", () => void shutdown());

async function initialize(input: any) {
  if (initialized) throw new Error("already initialized");
  initialized = true;
  const { TelegramClient } = await import("teleproto");
  const { StringSession } = await import("teleproto/sessions");
  const old = fs.existsSync("config.json") ? JSON.parse(fs.readFileSync("config.json", "utf8")) : {};
  const config = { ...old, api_id: input.api_id, api_hash: input.api_hash, proxy: input.proxy || undefined };
  fs.writeFileSync("config.json", JSON.stringify(config), { mode: 0o600 });
  const client = new TelegramClient(new StringSession(old.session || ""), input.api_id, input.api_hash, {
    connectionRetries: 3, deviceModel: "SignPulse TeleBox", proxy: config.proxy,
  });
  try {
    await client.connect();
    if (!(await client.checkAuthorization())) {
      await client.signInUserWithQrCode({ apiId: input.api_id, apiHash: input.api_hash }, {
        qrCode: async ({ token }: { token: Buffer }) => { emit({ event: "login_token", token: token.toString("base64") }); },
        password: async () => {
          emit({ event: "state", status: "password_required" });
          return new Promise<string>((resolve, reject) => {
            const timer = setTimeout(() => { passwordResolve = undefined; reject(new Error("password timeout")); }, 180000);
            passwordResolve = (value) => { clearTimeout(timer); passwordResolve = undefined; resolve(value); };
          });
        },
        onError: async () => true,
      });
    }
    config.session = (client.session as InstanceType<typeof StringSession>).save();
    fs.writeFileSync("config.json", JSON.stringify(config), { mode: 0o600 });
  } finally { await client.destroy(); }
  const { initPluginBaseConfig } = await import("../src/utils/pluginBase");
  initPluginBaseConfig();
  await import("../src/hook/patches/telegram.patch");
  await (await import("../src/utils/runtimeManager")).startRuntime();
  emit({ event: "state", status: "running" });
}
async function pluginOperation(action: string, name?: string) {
  if (!["install", "uninstall", "update", "reload"].includes(action)) throw new Error("invalid action");
  if (name && !/^[a-zA-Z0-9_-]{1,80}$/.test(name)) throw new Error("invalid plugin name");
  if (["install", "uninstall"].includes(action) && (!name || name === "all")) throw new Error("one plugin name required");
  if (action === "reload") {
    await (await import("../src/utils/runtimeManager")).reloadRuntime();
    return;
  }
  const outputs: string[] = [];
  // TPM writes progress through a local UI message transport, never a Telegram chat.
  const write = async (value: any) => { const text = String(value.text || value.message || value || ""); outputs.push(text); console.info(text); return sink; };
  const sink: any = { __panelStatus: true, id: 0, message: `.tpm ${action} ${name || ""}`,
    edit: write, reply: write, delete: async () => {}, client: { sendMessage: async (_: unknown, value: unknown) => write(value) } };
  const tpm = (await import("../src/plugin/tpm")).default;
  await tpm.cmdHandlers.tpm(sink);
  if (outputs.some(text => /❌|安装失败|卸载失败|更新失败/.test(text))) throw new Error("TPM operation failed; see logs");
}
const input = readline.createInterface({ input: process.stdin, terminal: false });
input.on("close", () => void shutdown());
input.on("line", (line) => {
  if (line.length > 65536) return;
  let command: any;
  try { command = JSON.parse(line); } catch { return; }
  if (command.action === "password") { passwordResolve?.(String(command.password || "")); return; }
  queue = queue.then(async () => {
    try {
      if (command.action === "init") await initialize(command);
      else if (command.action === "plugin") await pluginOperation(command.operation, command.name);
      else throw new Error("invalid command");
      emit({ event: "result", id: command.id, ok: true });
    } catch (error) {
      // Error objects can contain login secrets; emit a bounded safe category only.
      console.error("TeleBox operation failed", error instanceof Error ? error.name : "Error");
      emit({ event: "result", id: command.id, ok: false, message: "TeleBox 操作失败，请检查依赖、网络或授权状态" });
      if (command.action === "init") { emit({ event: "state", status: "failed" }); await shutdown(); }
    }
  });
});
