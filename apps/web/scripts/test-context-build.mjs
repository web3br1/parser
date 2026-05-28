import { rmSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const outDir = ".context-build-test";
const testFile = join(outDir, "context-build.test.js");
const tscBin = process.platform === "win32" ? "node_modules\\.bin\\tsc.cmd" : "node_modules/.bin/tsc";

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: "apps/web",
    shell: process.platform === "win32",
    stdio: "inherit"
  });
  if (result.status !== 0) {
    process.exitCode = result.status ?? 1;
    throw new Error(`${command} ${args.join(" ")} failed`);
  }
}

try {
  rmSync(join("apps/web", outDir), { recursive: true, force: true });
  run(tscBin, [
    "src/lib/context-build.ts",
    "src/lib/context-build.test.ts",
    "--module",
    "commonjs",
    "--target",
    "ES2022",
    "--moduleResolution",
    "node",
    "--skipLibCheck",
    "--outDir",
    outDir
  ]);
  run("node", [testFile]);
} finally {
  rmSync(join("apps/web", outDir), { recursive: true, force: true });
}
