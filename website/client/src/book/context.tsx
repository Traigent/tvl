import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

/** True when the book is rendered for the paged print route. */
export const PrintContext = createContext<boolean>(false);
export const usePrint = () => useContext(PrintContext);

/** The source commit the print route was stamped with (?commit=); null on the web. */
export const CommitContext = createContext<string | null>(null);

export interface PredictAnswer {
  id: string;
  question: ReactNode;
  answer: ReactNode;
}

/** One cited source in a chapter: print numbers it [n] and lists it at the chapter end. */
export interface RefEntry {
  to: string;
  /** The parts of the source cited in this chapter, in order of first citation. */
  sections: string[];
}

interface ChapterContextValue {
  slug: string;
  answers: PredictAnswer[];
  register: (a: PredictAnswer) => void;
  refs: RefEntry[];
  registerRef: (to: string, section?: string) => void;
}

export const ChapterContext = createContext<ChapterContextValue | null>(null);
export const useChapter = () => useContext(ChapterContext);

/**
 * Collects Predict answers and cited sources so print can list them at the end
 * of the chapter. Sources are numbered in order of first citation: effects run
 * in document order for leaf components such as Ref.
 */
export function ChapterProvider({ slug, children }: { slug: string; children: ReactNode }) {
  const [answers, setAnswers] = useState<PredictAnswer[]>([]);
  const [refs, setRefs] = useState<RefEntry[]>([]);
  const register = useCallback((a: PredictAnswer) => {
    setAnswers((prev) => (prev.some((p) => p.id === a.id) ? prev : [...prev, a]));
  }, []);
  const registerRef = useCallback((to: string, section?: string) => {
    setRefs((prev) => {
      const i = prev.findIndex((r) => r.to === to);
      if (i < 0) return [...prev, { to, sections: section ? [section] : [] }];
      if (!section || prev[i].sections.includes(section)) return prev;
      const next = prev.slice();
      next[i] = { ...prev[i], sections: [...prev[i].sections, section] };
      return next;
    });
  }, []);
  const value = useMemo(() => ({ slug, answers, register, refs, registerRef }), [slug, answers, register, refs, registerRef]);
  return <ChapterContext.Provider value={value}>{children}</ChapterContext.Provider>;
}
