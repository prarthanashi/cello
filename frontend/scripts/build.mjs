// Production build: validates every module, copies src -> dist, and writes a build manifest.
// No bundler is needed because the app is dependency-free native ES modules.
import { cpSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const base = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(base, "src"), dist = join(base, "dist");

function walk(dir) {
  return readdirSync(dir).flatMap((n) => { const p = join(dir, n); return statSync(p).isDirectory() ? walk(p) : [p]; });
}

// 1. Syntax-check every JS file (node --check) so a broken module fails the build.
for (const f of walk(src).filter((p) => p.endsWith(".js"))) {
  const r = spawnSync(process.execPath, ["--check", f], { encoding: "utf8" });
  if (r.status !== 0) { console.error(`Syntax error in ${relative(base, f)}\n${r.stderr}`); process.exit(1); }
}
// 2. Verify relative imports resolve.
for (const f of walk(src).filter((p) => p.endsWith(".js"))) {
  for (const m of readFileSync(f, "utf8").matchAll(/from\s+"(\.[^"]+)"/g)) {
    try { statSync(resolve(dirname(f), m[1])); } catch { console.error(`Unresolved import ${m[1]} in ${relative(base, f)}`); process.exit(1); }
  }
}
// 3. Guard: no secrets or AI-provider URLs in frontend code.
for (const f of walk(src)) {
  if (/api\.anthropic\.com|sk-[A-Za-z0-9]{20,}|AI_API_KEY/.test(readFileSync(f, "utf8"))) { console.error(`Forbidden secret/provider reference in ${relative(base, f)}`); process.exit(1); }
}
rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
cpSync(src, dist, { recursive: true });
const files = walk(dist).map((p) => ({ file: relative(dist, p), bytes: statSync(p).size }));
writeFileSync(join(dist, "build-manifest.json"), JSON.stringify({ builtAt: new Date().toISOString(), files }, null, 2));
console.log(`Build OK: ${files.length} files -> frontend/dist`);
