import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "..");
const cacheDir = resolve(repoRoot, "var", "tmp", "uv-cache");
const args = new Set(process.argv.slice(2));

mkdirSync(cacheDir, { recursive: true });

const env = {
  ...loadDotEnv(resolve(repoRoot, ".env")),
  ...process.env,
  UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? cacheDir,
};

if (!args.has("--skip-migrate")) {
  const migrateResult = spawnSync(
    "uv",
    ["run", "--project", "apps/api", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"],
    {
      cwd: repoRoot,
      env,
      stdio: "inherit",
    },
  );

  if (migrateResult.status !== 0) {
    process.exit(migrateResult.status ?? 1);
  }
}

if (args.has("--migrate-only")) {
  process.exit(0);
}

const server = spawn(
  "uv",
  ["run", "--project", "apps/api", "uvicorn", "skysort_api.main:app", "--app-dir", "apps/api/src", "--reload", "--port", "8000"],
  {
    cwd: repoRoot,
    env,
    stdio: "inherit",
  },
);

server.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (!server.killed) {
      server.kill(signal);
    }
  });
}

function loadDotEnv(filePath) {
  if (!existsSync(filePath)) {
    return {};
  }

  const parsed = {};
  const lines = readFileSync(filePath, "utf8").split(/\r?\n/u);

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const normalized = line.startsWith("export ") ? line.slice(7).trim() : line;
    const separatorIndex = normalized.indexOf("=");
    if (separatorIndex <= 0) {
      continue;
    }

    const key = normalized.slice(0, separatorIndex).trim();
    const value = normalized.slice(separatorIndex + 1).trim();
    if (!key) {
      continue;
    }

    parsed[key] = unquote(value);
  }

  return parsed;
}

function unquote(value) {
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1);
    }
  }
  return value;
}