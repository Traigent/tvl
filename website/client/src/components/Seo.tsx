import { useEffect } from "react";

interface SeoProps {
  title: string;
  description: string;
  path?: string;
  robots?: string;
}

function upsertMeta(
  selector: string,
  attrs: Record<string, string>,
  content: string,
) {
  let el = document.head.querySelector<HTMLMetaElement>(selector);
  if (!el) {
    el = document.createElement("meta");
    Object.entries(attrs).forEach(([key, value]) => el!.setAttribute(key, value));
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertCanonical(href: string) {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", "canonical");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

export default function Seo({
  title,
  description,
  path = "/",
  robots,
}: SeoProps) {
  useEffect(() => {
    document.title = title;

    const origin = window.location.origin;
    const url = new URL(path, origin).toString();

    upsertMeta('meta[name="description"]', { name: "description" }, description);
    upsertMeta('meta[property="og:title"]', { property: "og:title" }, title);
    upsertMeta(
      'meta[property="og:description"]',
      { property: "og:description" },
      description,
    );
    upsertMeta('meta[property="og:url"]', { property: "og:url" }, url);
    upsertMeta(
      'meta[property="twitter:title"]',
      { property: "twitter:title" },
      title,
    );
    upsertMeta(
      'meta[property="twitter:description"]',
      { property: "twitter:description" },
      description,
    );
    upsertMeta(
      'meta[name="robots"]',
      { name: "robots" },
      robots ?? "index,follow",
    );
    upsertCanonical(url);
  }, [description, path, robots, title]);

  return null;
}
