declare const __BOOK_COMMIT__: string | undefined;

/**
 * The commit the site was built from, injected by vite.config.ts at build time
 * (scripts/book_lib.mjs, sourceCommit: GITHUB_SHA in CI, else git HEAD).
 */
export const BUILD_COMMIT: string =
  typeof __BOOK_COMMIT__ === "string" && __BOOK_COMMIT__ ? __BOOK_COMMIT__ : "unknown";
