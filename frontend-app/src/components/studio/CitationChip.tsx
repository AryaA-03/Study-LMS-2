import React from 'react';
import { formatSecToPill } from '../MarkdownView';

export const CitationChip: React.FC<{
  startSec: number;
  label?: string;
  quote?: string;
  onSeek: (sec: number) => void;
}> = ({ startSec, label, quote, onSeek }) => (
  <span className="group relative inline-block">
    <button
      type="button"
      onClick={() => onSeek(startSec)}
      className="ts-pill"
    >
      ▶ {label || formatSecToPill(startSec)}
    </button>
    {quote && (
      <span className="pointer-events-none absolute bottom-full left-0 z-30 mb-1.5 hidden w-64 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-card)] p-2.5 text-xs leading-snug text-[var(--fg-primary)] shadow-xl group-hover:block">
        <span className="block font-semibold text-[var(--accent-text)] mb-0.5">Lecture Quote</span>
        {quote.slice(0, 180)}{quote.length > 180 ? '…' : ''}
      </span>
    )}
  </span>
);
