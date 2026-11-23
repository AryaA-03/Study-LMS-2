import React, { useEffect, useMemo, useRef } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface MarkdownViewProps {
  markdown: string;
  onSeekTimestamp?: (seconds: number) => void;
  className?: string;
}

function parseTimestampToSeconds(ts: string): number {
  const parts = ts.split(':').map((n) => parseInt(n, 10));
  if (parts.some(Number.isNaN)) return 0;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return 0;
}

function renderLatexInHtml(html: string): string {
  // Display math $$...$$
  let out = html.replace(/\$\$([\s\S]+?)\$\$/g, (_, expr: string) => {
    try {
      return katex.renderToString(expr.trim(), { displayMode: true, throwOnError: false });
    } catch {
      return expr;
    }
  });
  // Inline math $...$
  out = out.replace(/(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)/g, (_, expr: string) => {
    try {
      return katex.renderToString(expr.trim(), { displayMode: false, throwOnError: false });
    } catch {
      return expr;
    }
  });
  return out;
}

export const MarkdownView: React.FC<MarkdownViewProps> = ({ markdown, onSeekTimestamp, className = '' }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  const sanitizedHtml = useMemo(() => {
    const rawMd = markdown || '';
    // Replace clickable [MM:SS] or [HH:MM:SS] pills with safe buttons
    const withPills = rawMd.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g, (_, ts: string) => {
      const sec = parseTimestampToSeconds(ts);
      return `<button type="button" class="ts-pill" data-seek-sec="${sec}">▶ ${ts}</button>`;
    });
    const parsed = marked.parse(withPills, { async: false }) as string;
    const withMath = renderLatexInHtml(parsed);
    return DOMPurify.sanitize(withMath, {
      ALLOWED_URI_REGEXP: /^(?:https?:|\/api\/screenshots\/)/i,
      ADD_ATTR: ['data-seek-sec', 'target', 'rel'],
    });
  }, [markdown]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !onSeekTimestamp) return;
    const handler = (e: MouseEvent) => {
      const btn = (e.target as HTMLElement)?.closest<HTMLButtonElement>('[data-seek-sec]');
      if (btn) {
        const sec = parseInt(btn.getAttribute('data-seek-sec') || '0', 10);
        if (!Number.isNaN(sec)) onSeekTimestamp(sec);
      }
    };
    el.addEventListener('click', handler);
    return () => el.removeEventListener('click', handler);
  }, [onSeekTimestamp]);

  return (
    <div
      ref={containerRef}
      className={`prose-study ${className}`}
      dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
    />
  );
};
