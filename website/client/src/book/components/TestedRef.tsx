import { useContext } from "react";
import { BUILD_COMMIT } from "../buildInfo";
import { CommitContext } from "../context";
import CodeBlock from "./CodeBlock";

/** The commit this edition was tested at: the print route's stamp, else the build-time one. */
export function useTestedRef(): string {
  return useContext(CommitContext) ?? BUILD_COMMIT;
}

interface TestedRefProps {
  /** Render a code block instead of inline code; every "{ref}" in it becomes the commit. */
  code?: string;
  language?: string;
}

/**
 * The book's source commit: the commit this edition was built and tested at.
 *
 *   <TestedRef />                                        inline, as code
 *   <TestedRef language="bash" code={"git checkout {ref}"} />   a code block
 *
 * Print reads the commit the PDF build stamped on the print route (the cover shows the
 * same one); the web reads the commit injected at build time. Both come from one rule
 * (scripts/book_lib.mjs, sourceCommit), and the print route reports a mismatch.
 */
export default function TestedRef({ code, language }: TestedRefProps) {
  const ref = useTestedRef();
  if (code !== undefined) return <CodeBlock code={code.split("{ref}").join(ref)} language={language} />;
  return <code className="book-tested-ref">{ref}</code>;
}
