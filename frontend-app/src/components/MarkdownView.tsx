import React, { useMemo, useRef, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface MarkdownViewProps {
  markdown: string;
  onSeekTimestamp?: (seconds: number) => void;
  onExplainSelection?: (selectedText: string) => void;
  onSaveSelectionToNotes?: (selectedText: string) => void;
  className?: string;
}

export function parseTimestampToSec(ts: string): number {
  const parts = ts.split(':').map((p) => parseInt(p, 10));
  if (parts.some((n) => Number.isNaN(n))) return 0;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] || 0;
}

export function formatSecToPill(sec?: number | null): string {
  const s = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
}

function renderLatex(raw: string): string {
  // Display math $$...$$
  let out = raw.replace(/\$\$([\s\S]+?)\$\$/g, (_, expr) => {
    try {
      return `<div class="my-2 overflow-x-auto">${katex.renderToString(expr.trim(), { displayMode: true, throwOnError: false })}</div>`;
    } catch {
      return `<code>${expr}</code>`;
    }
  });
  // Inline math $...$
  out = out.replace(/(?<!\$)\$(?!\$)([^\n$]+?)(?<!\$)\$(?!\$)/g, (_, expr) => {
    try {
      return katex.renderToString(expr.trim(), { displayMode: false, throwOnError: false });
    } catch {
      return `<code>${expr}</code>`;
    }
  });
  return out;
}

export const MarkdownView: React.FC<MarkdownViewProps> = ({
  markdown,
  onSeekTimestamp,
  onExplainSelection,
  onSaveSelectionToNotes,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectionPopup, setSelectionPopup] = useState<{ text: string; top: number; left: number } | null>(null);

  const sanitizedHtml = useMemo(() => {
    if (!markdown) return '';
    // Pre-process GitHub callout markers
    const withMath = renderLatex(markdown);
    const rawHtml = marked.parse(withMath, { async: false, gfm: true, breaks: false }) as string;

    // Style [!IMPORTANT], [!TIP], [!NOTE] blockquotes cleanly
    const styledCallouts = rawHtml
      .replace(
        /<blockquote>\s*<p>\[!IMPORTANT\]\s*/gi,
        '<blockquote class="callout-important"><div class="text-[11px] font-bold uppercase tracking-wider text-[var(--accent)] mb-1">IMPORTANT</div><p>',
      )
      .replace(
        /<blockquote>\s*<p>\[!TIP\]\s*/gi,
        '<blockquote class="callout-tip"><div class="text-[11px] font-bold uppercase tracking-wider text-[var(--success)] mb-1">EXAM TIP</div><p>',
      )
      .replace(
        /<blockquote>\s*<p>\[!NOTE\]\s*/gi,
        '<blockquote class="callout-important"><div class="text-[11px] font-bold uppercase tracking-wider text-[var(--accent)] mb-1">NOTE</div><p>',
      );

    // Replace [MM:SS] or [HH:MM:SS] with clickable timestamp buttons
    const withPills = styledCallouts.replace(
      /\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g,
      (_, ts) => {
        const sec = parseTimestampToSec(ts);
        return `<button type="button" class="ts-pill" data-seek-sec="${sec}" title="Jump video to ${ts}">▶ ${ts}</button>`;
      },
    );

    return DOMPurify.sanitize(withPills, {
      ADD_TAGS: ['button', 'svg', 'path', 'math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'annotation'],
      ADD_ATTR: ['data-seek-sec', 'type', 'class', 'title', 'aria-hidden', 'xmlns', 'encoding'],
    });
  }, [markdown]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const btn = target.closest('[data-seek-sec]') as HTMLElement | null;
    if (btn && onSeekTimestamp) {
      const sec = parseInt(btn.getAttribute('data-seek-sec') || '0', 10);
      onSeekTimestamp(sec);
    }
  };

  const handleMouseUp = () => {
    if (!onExplainSelection && !onSaveSelectionToNotes) return;
    const sel = window.getSelection();
    const text = sel?.toString().trim() || '';
    if (text.length < 4 || text.length > 400 || !containerRef.current) {
      setSelectionPopup(null);
      return;
    }
    const range = sel?.getRangeAt(0);
    if (!range) return;
    const rect = range.getBoundingClientRect();
    const hostRect = containerRef.current.getBoundingClientRect();
    setSelectionPopup({
      text,
      top: Math.max(4, rect.top - hostRect.top - 40),
      left: Math.min(Math.max(8, rect.left - hostRect.left), Math.max(8, hostRect.width - 230)),
    });
  };

  return (
    <div
      ref={containerRef}
      className={`relative prose-study ${className}`}
      onClick={handleClick}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => setTimeout(() => setSelectionPopup(null), 200)}
    >
      {selectionPopup && (
        <div
          className="no-print absolute z-30 flex items-center gap-1 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-card)] px-1.5 py-1 shadow-lg"
          style={{ top: selectionPopup.top, left: selectionPopup.left }}
          onMouseDown={(e) => e.preventDefault()}
        >
          {onExplainSelection && (
            <button
              type="button"
              onClick={() => {
                onExplainSelection(selectionPopup.text);
                setSelectionPopup(null);
              }}
              className="rounded px-2 py-1 text-xs font-medium bg-[var(--accent)] text-white hover:opacity-90"
            >
              ✨ Explain with AI
            </button>
          )}
          {onSaveSelectionToNotes && (
            <button
              type="button"
              onClick={() => {
                onSaveSelectionToNotes(selectionPopup.text);
                setSelectionPopup(null);
              }}
              className="rounded px-2 py-1 text-xs font-medium border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              📌 Save
            </button>
          )}
        </div>
      )}
      <div dangerouslySetInnerHTML={{ __html: sanitizedHtml }} />
    </div>
  );
};
