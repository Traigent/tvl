import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, useLocation } from "wouter";
import Layout from "@/components/Layout";
import { useTheme } from "@/contexts/ThemeContext";
import type { Chapter } from "./chapters";
import "./book.css";

function readTheme(): "dark" | "light" {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/**
 * Theme switch. The site's ThemeProvider owns the theme: when it is switchable the
 * button simply calls its toggle. The site mounts it with `switchable` off, so there is
 * nothing to call; then the book keeps a reader preference of its own. The provider only
 * writes the document class from its own effect (at mount, after ours), so the preference
 * is applied after that effect and the provider's value is the default when none is saved.
 */
function ThemeToggle() {
  const site = useTheme();
  const [own, setOwn] = useState<"dark" | "light">(site.theme);
  useEffect(() => {
    if (site.switchable) return;
    const id = window.setTimeout(() => {
      try {
        const saved = localStorage.getItem("book-theme");
        if (saved === "light" || saved === "dark") {
          document.documentElement.classList.toggle("dark", saved === "dark");
        }
      } catch {
        /* storage blocked: keep the site theme */
      }
      setOwn(readTheme());
    }, 0);
    return () => window.clearTimeout(id);
  }, [site.switchable]);
  const theme = site.switchable ? site.theme : own;
  const toggle = () => {
    if (site.switchable && site.toggleTheme) {
      site.toggleTheme();
      return;
    }
    const next = readTheme() === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem("book-theme", next);
    } catch {
      /* ignore */
    }
    setOwn(next);
  };
  return (
    <button type="button" className="book-btn" onClick={toggle} aria-label="Switch between light and dark theme">
      {theme === "dark" ? "Light theme" : "Dark theme"}
    </button>
  );
}

function ProgressBar() {
  const [pct, setPct] = useState(0);
  useEffect(() => {
    const onScroll = () => {
      const h = document.documentElement;
      const max = h.scrollHeight - h.clientHeight;
      setPct(max > 0 ? Math.min(100, (h.scrollTop / max) * 100) : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <div className="book-progress" role="progressbar" aria-label="Reading progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
      <div style={{ width: `${pct}%` }} />
    </div>
  );
}

export function DraftBadge() {
  return <span className="book-badge">Draft &middot; TVL 1.3</span>;
}

interface ShellProps {
  chapters: Chapter[];
  currentSlug?: string;
  pilotQuery: string;
  children: ReactNode;
}

export default function BookShell({ chapters, currentSlug, pilotQuery, children }: ShellProps) {
  const [open, setOpen] = useState(false);
  const [location] = useLocation();
  useEffect(() => setOpen(false), [location]);
  return (
    <Layout>
      <ProgressBar />
      <div className="book-root book-shell">
        <div className="book-toolbar">
          <button type="button" className="book-btn book-menu-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="book-contents">
            Contents
          </button>
          <ThemeToggle />
          <a className="book-btn" href="/book/tvl-book.pdf" download>
            Download PDF
          </a>
        </div>
        <div className="book-columns">
          <nav id="book-contents" className={`book-sidebar ${open ? "is-open" : ""}`} aria-label="Book contents">
            <Link href={`/book${pilotQuery}`} className="book-sidebar-title">
              TVL, Visually
            </Link>
            <ol>
              {chapters.filter((c) => !c.planned).map((c) => (
                <li key={c.slug}>
                  <Link href={`/book/${c.slug}${pilotQuery}`} className={c.slug === currentSlug ? "is-current" : ""}>
                    {c.title}
                  </Link>
                  {c.draft && <DraftBadge />}
                </li>
              ))}
            </ol>
            {chapters.some((c) => c.planned) && (
              <>
                <p className="book-sidebar-sub">Planned chapters</p>
                <ol className="book-planned-nav">
                  {chapters.filter((c) => c.planned).map((c) => (
                    <li key={c.slug}>
                      <span>{`${c.order}. ${c.title}`}</span>
                    </li>
                  ))}
                </ol>
              </>
            )}
          </nav>
          <main className="book-main">{children}</main>
        </div>
      </div>
    </Layout>
  );
}
