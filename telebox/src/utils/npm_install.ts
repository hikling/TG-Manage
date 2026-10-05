import { execFileSync } from "child_process";
import fs from "fs";
import path from "path";

const pluginDir = path.join(process.cwd(), "plugins");

function buildCleanNpmEnv(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env };

  // 当前进程若由 npm 启动，会携带大量 npm_* 环境变量。
  // 其中 workspace / argv 等参数在子 npm 进程里可能被错误继承，
  // 造成类似 “No workspaces found: --workspace=--loglevel” 的噪音报错。
  for (const key of Object.keys(env)) {
    if (/^npm_(config_|package_|lifecycle_|command)/i.test(key)) {
      delete env[key];
    }
  }

  return env;
}

function runNpm(args: string[], cwd = pluginDir): void {
  fs.mkdirSync(cwd, { recursive: true });
  execFileSync(
    "npm",
    [...args, "--no-fund", "--no-audit", "--loglevel=error"],
    {
      cwd,
      env: buildCleanNpmEnv(),
      stdio: "pipe",
      encoding: "utf-8",
    }
  );
}

/**
 * npm_install - 安装指定的 npm 包
 * @param pkg 包名
 * @param version 版本号（可选）
 */
export function npm_install(pkg: string, version?: string) {
  const fullName = version ? `${pkg}@${version}` : pkg;

  try {
    require.resolve(pkg, { paths: [pluginDir, process.cwd()] });
    console.log(`Package "${pkg}" is already installed.`);
  } catch {
    console.log(`Installing ${fullName}...`);
    try {
      runNpm(["install", fullName]);
      console.log(`Package "${fullName}" installed successfully.`);
    } catch (error: any) {
      const stderr = error?.stderr?.toString?.() || error?.message || String(error);
      console.error(`Failed to install ${fullName}: ${stderr}`);
      throw error;
    }
  }
}

export function npm_install_project_dependencies() {
  // The image owns the shared core node_modules directory. Installing from
  // inside one account would mutate it for every other running account.
  if (fs.existsSync(path.join(process.cwd(), "node_modules"))) {
    console.log("Core dependencies are managed by the image; plugin dependencies install into plugins/.");
    return;
  }
  console.log("Installing project dependencies...");
  try {
    runNpm(["install"], path.resolve(process.cwd()));
    console.log("Project dependencies installed successfully.");
  } catch (error: any) {
    const stderr = error?.stderr?.toString?.() || error?.message || String(error);
    console.error(`Failed to install project dependencies: ${stderr}`);
    throw error;
  }
}
