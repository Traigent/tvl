/**
 * Track a series of async requests so only the most recent one may apply its result.
 * `begin()` supersedes every earlier request and returns an `isCurrent` check for the
 * new one; `cancel()` supersedes all of them (for example on unmount).
 */
export function latestOnly() {
  let generation = 0;
  return {
    begin(): () => boolean {
      const mine = ++generation;
      return () => mine === generation;
    },
    cancel(): void {
      generation++;
    },
  };
}
