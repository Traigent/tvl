/**
 * Fetch `url` and return its body as text. `fetch` resolves on 404 and 5xx, so this
 * rejects on any non-2xx status: callers' error paths then run instead of rendering,
 * caching or copying an error page as if it were the requested file.
 */
export async function fetchText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} failed: HTTP ${response.status} ${response.statusText}`.trimEnd());
  }
  return response.text();
}
