import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "..");
const cacheDir = resolve(repoRoot, "var", "tmp", "uv-cache");

mkdirSync(cacheDir, { recursive: true });

const result = spawnSync(
  "uv",
  ["run", "--project", "apps/api", "python", "scripts/generate_client.py"],
  {
    cwd: repoRoot,
    env: {
      ...process.env,
      UV_CACHE_DIR: cacheDir,
    },
    stdio: "inherit",
  },
);

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}
