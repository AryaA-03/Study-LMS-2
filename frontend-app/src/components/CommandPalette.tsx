import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';

export interface CommandItem {
  id: string;
  label: string;
  category: string;
  onSelect: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  items: CommandItem[];
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose, items }) => {
  const [query, setQuery] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .filter((it) => !q || it.label.toLowerCase().includes(q) || it.category.toLowerCase().includes(q))
      .slice(0, 14);
  }, [items, query]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command Palette"
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/50 backdrop-blur-[2px] px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-xl bg-surface border border-border-def shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2.5 px-4 py-3 border-b border-border-def">
          <Search className="w-4 h-4 text-fg-muted shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIdx(0);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.preventDefault();
                onClose();
              } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActiveIdx((i) => Math.min(i + 1, Math.max(0, filtered.length - 1)));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActiveIdx((i) => Math.max(0, i - 1));
              } else if (e.key === 'Enter' && filtered[activeIdx]) {
                e.preventDefault();
                const sel = filtered[activeIdx];
                onClose();
                sel.onSelect();
              }
            }}
            placeholder="Jump to lesson, course, or action..."
            className="w-full bg-transparent text-sm text-fg-primary placeholder:text-fg-muted focus:outline-none"
          />
          <kbd className="text-xs font-mono px-1.5 py-0.5 rounded bg-subtle text-fg-secondary border border-border-def">
            ESC
          </kbd>
        </div>
        <ul role="listbox" className="max-h-80 overflow-y-auto p-1.5 divide-y divide-border-def/40">
          {filtered.length === 0 ? (
            <li className="px-3 py-4 text-xs text-fg-muted text-center">No matching lessons or actions.</li>
          ) : (
            filtered.map((item, idx) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    item.onSelect();
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2 text-left text-sm rounded-lg transition-colors ${
                    idx === activeIdx ? 'bg-accent-soft text-accent-text font-medium' : 'text-fg-primary hover:bg-subtle'
                  }`}
                >
                  <span className="truncate pr-3">{item.label}</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-subtle text-fg-secondary shrink-0">
                    {item.category}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
};
