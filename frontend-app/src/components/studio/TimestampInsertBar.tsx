import React from 'react';
import { Clock } from 'lucide-react';
import { formatSecToPill } from '../MarkdownView';

export const TimestampInsertButton: React.FC<{
  currentTimeSec?: number;
  onInsert: (pill: string) => void;
  label?: string;
}> = ({ currentTimeSec = 0, onInsert, label }) => {
  const pill = `[${formatSecToPill(currentTimeSec)}]`;
  return (
    <button
      type="button"
      onClick={() => onInsert(pill)}
      title={`Insert current video timestamp ${pill}`}
      className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
    >
      <Clock className="h-3.5 w-3.5 text-[var(--accent)]" />
      {label || `Insert ${pill}`}
    </button>
  );
};
