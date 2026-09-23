// Build the frontend as a static bundle and stage it for Capacitor.
//
// Kept as a script rather than a shell one-liner so the same command works on
// macOS (where the iOS build has to run) and on the Linux CI runner.
import { execFileSync } from "node:child_process";
import { cpSync, rmSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const mobileDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const frontendDir = resolve(mobileDir, "..", "frontend");
const exportDir = resolve(frontendDir, "out");
const wwwDir = resolve(mobileDir, "www");

const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const run = (cmd, args, cwd, env) =>
  execFileSync(cmd, args, { cwd, stdio: "inherit", env: { ...process.env, ...env } });

// NEXT_PUBLIC_* is baked in at build time, so the API the app talks to is fixed
// when the binary is built — there is no runtime config inside a store build.
const apiUrl = process.env.NEXT_PUBLIC_API_URL;
if (!apiUrl) {
  console.error(
    "NEXT_PUBLIC_API_URL is not set.\n" +
      "A mobile build bakes the backend URL into the binary, so it must be the\n" +
      "real production URL — e.g. https://bruno-backend-xxxx.onrender.com"
  );
  process.exit(1);
}

if (!existsSync(resolve(frontendDir, "node_modules"))) run(npm, ["ci"], frontendDir);

rmSync(exportDir, { recursive: true, force: true });
run(npm, ["run", "build"], frontendDir, { MOBILE_BUILD: "1", NEXT_PUBLIC_API_URL: apiUrl });

rmSync(wwwDir, { recursive: true, force: true });
cpSync(exportDir, wwwDir, { recursive: true });
console.log(`Staged the static export at ${wwwDir} (API: ${apiUrl})`);
