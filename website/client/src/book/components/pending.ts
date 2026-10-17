/** Print readiness: async components (Mermaid, images) register here; the PDF script waits for zero. */
declare global {
  interface Window {
    __BOOK_PENDING__?: number;
    __BOOK_READY__?: boolean;
    __BOOK_ERRORS__?: string[];
  }
}

export function beginPending(): () => void {
  window.__BOOK_PENDING__ = (window.__BOOK_PENDING__ ?? 0) + 1;
  let done = false;
  return () => {
    if (done) return;
    done = true;
    window.__BOOK_PENDING__ = Math.max(0, (window.__BOOK_PENDING__ ?? 1) - 1);
  };
}

export function reportBookError(message: string) {
  (window.__BOOK_ERRORS__ ??= []).push(message);
}
