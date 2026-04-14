import rawManifest from "@/generated/book/manifest.json";

import type {
  BookChapterMeta,
  BookConceptMeta,
  BookManifest,
  BookMaterialMeta,
  BookPatternMeta,
  BookPathMeta,
  BookSectionMeta,
} from "@/book/types";

export const bookManifest = rawManifest as BookManifest;

export const chapters = bookManifest.chapters;
export const materials = bookManifest.materials;
export const patterns = bookManifest.patterns;
export const guidedPaths = bookManifest.paths;
export const concepts = bookManifest.concepts;
export const searchEntries = bookManifest.search;
export const orderedSections = chapters.flatMap((chapter) => chapter.sections);

export const chapterBySlug = new Map<string, BookChapterMeta>(
  chapters.map((chapter) => [chapter.slug, chapter]),
);

export const sectionByKey = new Map<string, BookSectionMeta>(
  orderedSections.map((section) => [`${section.chapter}/${section.slug}`, section] as const),
);

export const conceptById = new Map<string, BookConceptMeta>(
  concepts.map((concept) => [concept.id, concept]),
);

export const materialBySlug = new Map<string, BookMaterialMeta>(
  materials.map((material) => [material.slug, material]),
);

export const patternBySlug = new Map<string, BookPatternMeta>(
  patterns.map((pattern) => [pattern.slug, pattern]),
);

export const pathById = new Map<string, BookPathMeta>(
  guidedPaths.map((path) => [path.id, path]),
);

export function getChapter(chapterSlug: string | undefined): BookChapterMeta | null {
  if (!chapterSlug) {
    return null;
  }
  return chapterBySlug.get(chapterSlug) ?? null;
}

export function getSection(
  chapterSlug: string | undefined,
  sectionSlug: string | undefined,
): BookSectionMeta | null {
  if (!chapterSlug || !sectionSlug) {
    return null;
  }
  return sectionByKey.get(`${chapterSlug}/${sectionSlug}`) ?? null;
}

export function getMaterial(materialSlug: string | undefined): BookMaterialMeta | null {
  if (!materialSlug) {
    return null;
  }
  return materialBySlug.get(materialSlug) ?? null;
}

export function getPattern(patternSlug: string | undefined): BookPatternMeta | null {
  if (!patternSlug) {
    return null;
  }
  return patternBySlug.get(patternSlug) ?? null;
}

export function getConceptsForSection(section: BookSectionMeta): BookConceptMeta[] {
  return section.conceptRefs
    .map((conceptId) => conceptById.get(conceptId))
    .filter((concept): concept is BookConceptMeta => Boolean(concept));
}

export function getConceptsForPattern(pattern: BookPatternMeta): BookConceptMeta[] {
  return pattern.conceptRefs
    .map((conceptId) => conceptById.get(conceptId))
    .filter((concept): concept is BookConceptMeta => Boolean(concept));
}

export function getSectionKey(section: BookSectionMeta): string {
  return `${section.chapter}/${section.slug}`;
}

export function getPathsForSection(section: BookSectionMeta): BookPathMeta[] {
  const sectionKey = getSectionKey(section);
  return guidedPaths.filter((path) => path.sections.includes(sectionKey));
}

export function getSiblingSection(section: BookSectionMeta, offset: number): BookSectionMeta | null {
  const index = orderedSections.findIndex(
    (candidate) => candidate.chapter === section.chapter && candidate.slug === section.slug,
  );
  if (index < 0) {
    return null;
  }
  return orderedSections[index + offset] ?? null;
}

export function getNextSectionInPath(
  path: BookPathMeta,
  section: BookSectionMeta,
): BookSectionMeta | null {
  const index = path.sections.indexOf(getSectionKey(section));
  if (index < 0) {
    return sectionByKey.get(path.sections[0] ?? "") ?? null;
  }
  return sectionByKey.get(path.sections[index + 1] ?? "") ?? null;
}

export function getPrerequisiteConceptsForSection(section: BookSectionMeta): BookConceptMeta[] {
  const currentConceptIds = new Set(section.conceptRefs);
  const prerequisites: BookConceptMeta[] = [];
  const seen = new Set<string>();

  for (const conceptId of section.conceptRefs) {
    const concept = conceptById.get(conceptId);
    if (!concept) {
      continue;
    }

    for (const prerequisiteId of concept.prerequisites) {
      if (currentConceptIds.has(prerequisiteId) || seen.has(prerequisiteId)) {
        continue;
      }
      const prerequisite = conceptById.get(prerequisiteId);
      if (!prerequisite) {
        continue;
      }
      seen.add(prerequisiteId);
      prerequisites.push(prerequisite);
    }
  }

  return prerequisites;
}

export function getBestReviewSectionForConcept(
  concept: BookConceptMeta,
  section: BookSectionMeta,
): BookSectionMeta | null {
  const currentIndex = orderedSections.findIndex(
    (candidate) => candidate.chapter === section.chapter && candidate.slug === section.slug,
  );

  const conceptSections = concept.sections
    .map((sectionKey) => sectionByKey.get(sectionKey))
    .filter((candidate): candidate is BookSectionMeta => Boolean(candidate));

  const earlierSections = conceptSections.filter((candidate) => {
    const candidateIndex = orderedSections.findIndex(
      (orderedSection) =>
        orderedSection.chapter === candidate.chapter && orderedSection.slug === candidate.slug,
    );
    return candidateIndex >= 0 && candidateIndex < currentIndex;
  });

  return earlierSections.at(-1) ?? conceptSections[0] ?? null;
}
