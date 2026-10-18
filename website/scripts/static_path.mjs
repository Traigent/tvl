// Resolve a request pathname to a file inside `root`, or report why it cannot be served.
import fs from "node:fs";
import path from "node:path";

export function resolveStaticPath(root, pathname) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return { status: 400 };
  }
  if (decoded.includes("\0")) return { status: 400 };
  const inside = (candidate) => {
    const rel = path.relative(root, candidate);
    return !(rel === ".." || rel.startsWith(".." + path.sep) || path.isAbsolute(rel));
  };
  let file = path.resolve(root, "." + path.posix.normalize("/" + decoded));
  if (!inside(file)) return { status: 403 };
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) {
    file = path.join(file, "index.html");
    if (!inside(file)) return { status: 403 };
  }
  if (!fs.existsSync(file)) {
    file = path.join(root, "index.html"); // SPA fallback
    if (!inside(file)) return { status: 403 };
  }
  return { status: 200, file };
}
