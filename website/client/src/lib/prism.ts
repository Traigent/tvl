import Prism from "prismjs";

import "prismjs/components/prism-json";
import "prismjs/components/prism-markdown";
import "prismjs/components/prism-ebnf";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-python";
import "prismjs/components/prism-latex";

if (!Prism.languages.tvl) {
  Prism.languages.tvl = Prism.languages.extend("yaml", {
    keyword: {
      pattern:
        /(^\s*)(?:tvl|tvl_version|module|environment|evaluation_set|tvars|constraints|structural|derived|objectives|promotion_policy|chance_constraints|exploration|strategy|convergence|budgets|domain|range|resolution|direction|dominance|min_effect|require|when|then)\s*:/m,
      lookbehind: true,
      alias: "keyword",
    },
    important: {
      pattern:
        /\b(?:maximize|minimize|epsilon_pareto|nsga2|bool|int|float|enum\[str\]|enum\[int\]|enum\[float\])\b/,
      alias: "important",
    },
    number: /\b(?:\d+(?:\.\d+)?(?:ms|s|m|h|%)?)\b/,
  });
}

const LANGUAGE_ALIASES: Record<string, string> = {
  yml: "yaml",
  sh: "bash",
  py: "python",
  md: "markdown",
  tex: "latex",
  "tvl-yaml": "tvl",
};

const FALLBACK_LANGUAGE = "markdown";

export function resolvePrismLanguage(language: string): string {
  const normalized = language.toLowerCase();
  return LANGUAGE_ALIASES[normalized] ?? normalized;
}

export function languageFromPath(path: string): string {
  if (path.endsWith(".tvl.yml")) return "tvl";
  if (path.endsWith(".yml") || path.endsWith(".yaml")) return "yaml";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".py")) return "python";
  if (path.endsWith(".sh")) return "bash";
  if (path.endsWith(".ebnf")) return "ebnf";
  if (path.endsWith(".tex")) return "latex";
  return FALLBACK_LANGUAGE;
}

export function highlightCode(code: string, language: string): string {
  const resolved = resolvePrismLanguage(language);
  const grammar = Prism.languages[resolved] ?? Prism.languages[FALLBACK_LANGUAGE];
  return Prism.highlight(code, grammar, resolved);
}

