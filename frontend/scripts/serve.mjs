// Static file server + /api reverse proxy to the backend. Zero dependencies.
// usage: node scripts/serve.mjs <dir> <port>      (BACKEND_URL defaults to http://127.0.0.1:8000)
import http from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)), process.argv[2] || "src");
const port = Number(process.argv[3] || 5173);
const backend = new URL(process.env.BACKEND_URL || "http://127.0.0.1:8000");
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml" };

http.createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname.startsWith("/api/")) {
    const proxied = http.request({ host: backend.hostname, port: backend.port, path: url.pathname + url.search, method: req.method,
      headers: { ...req.headers, host: backend.host } }, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
    proxied.on("error", () => { res.writeHead(502, { "Content-Type": "application/json" }); res.end(JSON.stringify({ error: { code: "backend_unavailable", message: "We couldn’t connect to the service. Check your connection and try again." } })); });
    req.pipe(proxied);
    return;
  }
  let file = normalize(join(root, decodeURIComponent(url.pathname)));
  if (!file.startsWith(root)) { res.writeHead(403); res.end(); return; }
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  if (!existsSync(file)) { res.writeHead(404, { "Content-Type": "text/plain" }); res.end("Not found"); return; }
  res.writeHead(200, { "Content-Type": types[extname(file)] || "application/octet-stream", "X-Content-Type-Options": "nosniff" });
  createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => console.log(`Serving ${root} on http://localhost:${port} (proxying /api to ${backend.origin})`));
