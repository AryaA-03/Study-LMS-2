import React, { useMemo, useRef, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import { Sparkles, BookmarkPlus } from 'lucide-react';

interface MarkdownViewProps {
  markdown: string;
  onSeekTimestamp?: (sec: number) => void;
  onExplainSelection?: (text: string) => void;
  onSaveSelectionToNotes?: (text: string) => void;
  activeTimeSec?: number;
  className?: string;
}

export function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .replace(/\[.*?\]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

export function extractMarkdownHeadings(markdown: string): Array<{ id: string; text: string }> {
  if (!markdown) return [];
  const headings: Array<{ id: string; text: string }> = [];
  const seen = new Set<string>();
  for (const line of markdown.split('\n')) {
    const m = line.match(/^##\s+(.+)$/);
    if (m) {
      const clean = m[1].replace(/\[\d{1,2}:\d{2}(?::\d{2})?\]/g, '').replace(/[*_`]/g, '').trim();
      const id = slugifyHeading(clean);
      if (clean && id && !seen.has(id)) {
        seen.add(id);
        headings.push({ id, text: clean });
      }
    }
  }
  return headings;
}

export function parseTimestampToSec(ts: string): number {
  const parts = ts.split(':').map((p) => parseInt(p, 10) || 0);
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
  let out = raw.replace(/\$\$([\s\S]+?)\$\$/g, (_, expr) => {
    try {
      return `<div class="my-2.5 overflow-x-auto">${katex.renderToString(expr.trim(), { displayMode: true, throwOnError: false })}</div>`;
    } catch {
      return `<code>${expr}</code>`;
    }
  });
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
  activeTimeSec,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectionPopup, setSelectionPopup] = useState<{ text: string; top: number; left: number } | null>(null);

  const sanitizedHtml = useMemo(() => {
    if (!markdown) return '';
    // Strip any leaked internal chunk references
    const cleaned = markdown.replace(/\[ref:[^\]]+\]/gi, '').replace(/\bchk_[a-f0-9]{4,}\b/gi, '');
    const codePlaceholders: string[] = [];
    const protectedMd = cleaned
      .replace(/```[\s\S]*?```/g, (m) => {
        codePlaceholders.push(m);
        return `@@CODE_BLOCK_${codePlaceholders.length - 1}@@`;
      })
      .replace(/`[^`\n]+`/g, (m) => {
        codePlaceholders.push(m);
        return `@@CODE_BLOCK_${codePlaceholders.length - 1}@@`;
      });
    const withMath = renderLatex(protectedMd).replace(/@@CODE_BLOCK_(\d+)@@/g, (_, idx) => codePlaceholders[Number(idx)] || '');
    const rawHtml = marked.parse(withMath, { async: false, gfm: true, breaks: false }) as string;

    // Add anchor IDs to H2 headings for sticky section jump bar
    const withIds = rawHtml.replace(/<h2>([\s\S]*?)<\/h2>/gi, (_, inner) => {
      const plain = inner.replace(/<[^>]+>/g, '').trim();
      const slug = slugifyHeading(plain);
      return `<h2 id="sec-${slug}">${inner}</h2>`;
    });

    // Style [!IMPORTANT], [!TIP], [!NOTE] blockquotes cleanly
    const styledCallouts = withIds
      .replace(
        /<blockquote>\s*<p>\[!IMPORTANT\]\s*/gi,
        '<blockquote class="callout-important"><div class="text-xs font-bold uppercase tracking-wider text-[var(--accent)] mb-1">IMPORTANT</div><p>',
      )
      .replace(
        /<blockquote>\s*<p>\[!TIP\]\s*/gi,
        '<blockquote class="callout-tip"><div class="text-xs font-bold uppercase tracking-wider text-[var(--success)] mb-1">EXAM TIP</div><p>',
      )
      .replace(
        /<blockquote>\s*<p>\[!NOTE\]\s*/gi,
        '<blockquote class="callout-important"><div class="text-xs font-bold uppercase tracking-wider text-[var(--accent)] mb-1">NOTE</div><p>',
      );

    // Wrap <pre> blocks with a 1-click Copy button and protect code blocks before timestamp pills
    const htmlCodeBlocks: string[] = [];
    const withCopyPre = styledCallouts.replace(/<pre\b[^>]*>[\s\S]*?<\/pre>/gi, (m) => {
      const wrapped = `<div class="code-block-wrap"><button type="button" class="code-copy-btn" data-copy-code="1">Copy</button>${m}</div>`;
      htmlCodeBlocks.push(wrapped);
      return `@@HTML_CODE_${htmlCodeBlocks.length - 1}@@`;
    });
    const htmlProtected = withCopyPre.replace(/<code\b[^>]*>[\s\S]*?<\/code>/gi, (m) => {
      htmlCodeBlocks.push(m);
      return `@@HTML_CODE_${htmlCodeBlocks.length - 1}@@`;
    });

    const withPills = htmlProtected
      .replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g, (_, ts) => {
        const sec = parseTimestampToSec(ts);
        const isActive =
          activeTimeSec !== undefined && activeTimeSec >= sec && activeTimeSec < sec + 90;
        return `<button type="button" class="ts-pill${isActive ? ' ts-pill-active' : ''}" data-seek-sec="${sec}" title="Jump video to ${ts}">▶ ${ts}</button>`;
      })
      .replace(/@@HTML_CODE_(\d+)@@/g, (_, idx) => htmlCodeBlocks[Number(idx)] || '');

    return DOMPurify.sanitize(withPills, {
      FORBID_TAGS: ['script', 'iframe', 'object', 'embed'],
      ADD_TAGS: ['button', 'svg', 'path', 'math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'annotation'],
      ADD_ATTR: ['id', 'data-seek-sec', 'data-copy-code', 'type', 'class', 'title', 'aria-hidden', 'xmlns', 'encoding'],
    });
  }, [markdown, activeTimeSec]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const copyBtn = target.closest('[data-copy-code]') as HTMLElement | null;
    if (copyBtn) {
      const pre = copyBtn.parentElement?.querySelector('pre');
      if (pre?.textContent) {
        navigator.clipboard?.writeText(pre.textContent).catch(() => {});
        const orig = copyBtn.textContent;
        copyBtn.textContent = 'Copied';
        setTimeout(() => {
          copyBtn.textContent = orig || 'Copy';
        }, 1500);
      }
      return;
    }
    const btn = target.closest('[data-seek-sec]') as HTMLElement | null;
    if (btn && onSeekTimestamp) {
      const sec = parseInt(btn.getAttribute('data-seek-sec') || '0', 10);
      onSeekTimestamp(sec);
    }
  };

  const handleMouseUp = () => {
    if (!onExplainSelection && !onSaveSelectionToNotes) return;
    const sel = window.getSelection();
    const txt = sel?.toString().trim() || '';
    if (txt.length < 6 || !containerRef.current || !sel || sel.rangeCount === 0) {
      setSelectionPopup(null);
      return;
    }
    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const parentRect = containerRef.current.getBoundingClientRect();
    setSelectionPopup({
      text: txt,
      top: Math.max(4, rect.top - parentRect.top - 42),
      left: Math.min(parentRect.width - 240, Math.max(8, rect.left - parentRect.left)),
    });
  };

  return (
    <div ref={containerRef} className="relative" onMouseUp={handleMouseUp}>
      {selectionPopup && (
        <div
          style={{ top: selectionPopup.top, left: selectionPopup.left }}
          className="no-print absolute z-30 flex items-center gap-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-card)] px-2.5 py-1.5 shadow-lg text-xs"
        >
          {onExplainSelection && (
            <button
              type="button"
              onClick={() => {
                onExplainSelection(selectionPopup.text);
                setSelectionPopup(null);
              }}
              className="inline-flex items-center gap-1 rounded px-2 py-0.5 font-medium text-[var(--accent-text)] hover:bg-[var(--accent-soft)]"
            >
              <Sparkles className="h-3.5 w-3.5" /> Explain
            </button>
          )}
          {onSaveSelectionToNotes && (
            <button
              type="button"
              onClick={() => {
                onSaveSelectionToNotes(selectionPopup.text);
                setSelectionPopup(null);
              }}
              className="inline-flex items-center gap-1 rounded px-2 py-0.5 font-medium text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              <BookmarkPlus className="h-3.5 w-3.5" /> Save
            </button>
          )}
        </div>
      )}
      <div
        className={`prose-study ${className}`}
        onClick={handleClick}
        dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
      />
    </div>
  );
};
