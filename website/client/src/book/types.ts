export interface BookSectionMeta {
  id: string;
  slug: string;
  title: string;
  summary: string;
  chapter: string;
  estimatedMinutes: number;
  interactive: boolean;
  conceptRefs: string[];
  exampleRefs: string[];
  opalBridge: boolean;
  route: string;
  modulePath: string;
  excerpt: string[];
}

export interface BookChapterMeta {
  id: number;
  slug: string;
  title: string;
  summary: string;
  estimatedMinutes: number;
  learningObjectives: string[];
  prerequisites: string[];
  pathTags: string[];
  primaryExample: string;
  introModulePath: string;
  introExcerpt: string[];
  sections: BookSectionMeta[];
}

export interface BookPathMeta {
  id: string;
  title: string;
  audience: string;
  goal: string;
  sections: string[];
  entrySections: string[];
  completionSections: string[];
  estimatedMinutes: number;
}

export interface BookMaterialMeta {
  id: string;
  slug: string;
  title: string;
  summary: string;
  audience: string;
  materialType: string;
  estimatedMinutes: number;
  objectives: string[];
  relatedSections: string[];
  route: string;
  modulePath: string;
  downloadPath: string;
}

export interface BookPatternMeta {
  id: string;
  slug: string;
  title: string;
  summary: string;
  family: string;
  sortOrder: number;
  estimatedMinutes: number;
  tunedVariables: string[];
  decisionAxes: string[];
  failureModes: string[];
  relatedSections: string[];
  conceptRefs: string[];
  primaryExample: string;
  route: string;
  modulePath: string;
}

export interface BookConceptMeta {
  id: string;
  term: string;
  definition: string;
  prerequisites: string[];
  sections: string[];
}

export interface BookSearchEntry {
  id: string;
  kind: "section" | "pattern";
  title: string;
  summary: string;
  route: string;
  conceptRefs: string[];
  pathTags: string[];
  text: string;
  chapterSlug?: string;
  chapterTitle?: string;
  sectionSlug?: string;
  sectionKey?: string;
  patternSlug?: string;
  family?: string;
}

export interface BookManifest {
  chapters: BookChapterMeta[];
  materials: BookMaterialMeta[];
  patterns: BookPatternMeta[];
  paths: BookPathMeta[];
  concepts: BookConceptMeta[];
  search: BookSearchEntry[];
}
