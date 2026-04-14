import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "tvl-book-progress:v1";
const EVENT_NAME = "tvl-book-progress-updated";

function readCompletedSectionKeys(): string[] {
  if (typeof window === "undefined") {
    return [];
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((value): value is string => typeof value === "string");
  } catch {
    return [];
  }
}

function writeCompletedSectionKeys(sectionKeys: string[]) {
  if (typeof window === "undefined") {
    return;
  }

  const unique = Array.from(new Set(sectionKeys));
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(unique));
  window.dispatchEvent(new Event(EVENT_NAME));
}

export function useBookProgress() {
  const [completedSectionKeys, setCompletedSectionKeys] = useState<string[]>([]);

  useEffect(() => {
    const sync = () => {
      setCompletedSectionKeys(readCompletedSectionKeys());
    };

    sync();
    window.addEventListener("storage", sync);
    window.addEventListener(EVENT_NAME, sync as EventListener);

    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(EVENT_NAME, sync as EventListener);
    };
  }, []);

  const markSectionComplete = useCallback((sectionKey: string) => {
    if (!sectionKey) {
      return;
    }

    const nextKeys = readCompletedSectionKeys();
    if (nextKeys.includes(sectionKey)) {
      return;
    }

    nextKeys.push(sectionKey);
    writeCompletedSectionKeys(nextKeys);
  }, []);

  return {
    completedSectionKeys,
    completedSectionKeySet: new Set(completedSectionKeys),
    markSectionComplete,
  };
}
