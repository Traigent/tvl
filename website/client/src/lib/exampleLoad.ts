import { fetchText } from "./fetchText";

export type ExampleLoad = { ok: true; content: string } | { ok: false; error: string };

/**
 * Load one example file for preview or copy. A failure is returned as an error,
 * never as text, so the caller cannot show or copy an error message as the file.
 */
export async function loadExample(
  path: string,
  allowed: ReadonlySet<string>,
  cached: string | undefined,
  fetcher: (path: string) => Promise<string> = fetchText,
): Promise<ExampleLoad> {
  if (!allowed.has(path)) return { ok: false, error: `Unsupported example path: ${path}` };
  if (cached !== undefined) return { ok: true, content: cached };
  try {
    return { ok: true, content: await fetcher(path) };
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    return { ok: false, error: `Could not load ${path}: ${reason}` };
  }
}
