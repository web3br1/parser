import { rmSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const outDir = ".pilot-flow-test";
const testFile = join(outDir, "pilot-flow.test.js");

function run(command, args) {
  const result = spawnSync(command, args, {
    shell: process.platform === "win32",
    stdio: "inherit"
  });
  if (result.status !== 0) {
    process.exitCode = result.status ?? 1;
    throw new Error(`${command} ${args.join(" ")} failed`);
  }
}

try {
  rmSync(outDir, { recursive: true, force: true });
  run("tsc", [
    "src/lib/pilot-flow.ts",
    "src/lib/pilot-flow.test.ts",
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
  rmSync(outDir, { recursive: true, force: true });
}
