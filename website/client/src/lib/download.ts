/**
 * Save `content` as a file named `filename` through a temporary anchor.
 * The Blob's object URL is revoked on the next task, after the click has handed
 * the download to the browser, so the text is not pinned in memory for the life
 * of the tab.
 */
export function downloadText(content: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
  const element = document.createElement("a");
  element.href = url;
  element.download = filename;
  document.body.appendChild(element);
  try {
    element.click();
  } finally {
    document.body.removeChild(element);
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}
