declare module "*.yaml?raw" {
  const content: string;
  export default content;
}

declare module "*.mdx" {
  import type { ComponentType } from "react";

  const MDXComponent: ComponentType<Record<string, unknown>>;
  export default MDXComponent;
}

declare module "pagedjs" {
  export class Previewer {
    constructor(options?: Record<string, unknown>);
    preview(
      content?: HTMLElement | DocumentFragment | string,
      stylesheets?: Record<string, string>[],
      renderTo?: HTMLElement,
    ): Promise<{ total: number }>;
  }
}
