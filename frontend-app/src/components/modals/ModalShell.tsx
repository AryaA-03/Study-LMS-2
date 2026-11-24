import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Database,
  Download,
  FileText,
  Globe,
  Loader2,
  Play,
  Printer,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
  Youtube,
  Zap,
} from 'lucide-react';
import { api, Course, CramSheet, JobStatus, Quiz, QuizSubmitResult, SystemSettings } from '../../api/client';
import { formatSecToPill, MarkdownView } from '../MarkdownView';

export const ModalShell: React.FC<{
  title: string;
  subtitle?: string;
  onClose: () => void;
  wide?: boolean;
  children: React.ReactNode;
}> = ({ title, subtitle, onClose, wide, children }) => (
  <div
    className="no-print fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-[2px]"
    onClick={onClose}
  >
    <div
      className={`flex max-h-[90vh] w-full flex-col overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-card)] shadow-2xl ${
        wide ? 'max-w-4xl' : 'max-w-xl'
      }`}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-3.5">
        <div>
          <h2 className="text-sm font-bold text-[var(--fg-primary)]">{title}</h2>
          {subtitle && <p className="text-xs text-[var(--fg-secondary)]">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-5">{children}</div>
    </div>
  </div>
);

export const CREATOR_PRESETS = [
  {
    label: 'Neso Academy — Theory of Computation',
    title: 'Theory of Computation (Neso Academy)',
    url: 'https://www.youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev',
  },
  {
    label: 'Gate Smashers — DBMS Complete',
    title: 'DBMS Exam Prep (Gate Smashers)',
    url: 'https://www.youtube.com/playlist?list=PLxCzCOWd7aiFAN6I8CuViBuCdJgiOkT2Y',
  },
  {
    label: 'Abdul Bari — Algorithms',
    title: 'Design & Analysis of Algorithms',
    url: 'https://www.youtube.com/playlist?list=PLDN4rrl48XKpZkf03iYFl-O29szjTrs_O',
  },
  {
    label: 'Gate Smashers — Operating Systems',
    title: 'Operating Systems (Gate Smashers)',
    url: 'https://www.youtube.com/playlist?list=PLxCzCOWd7aiGz9donHRrE9I3Mwn6XdP8p',
  },
];

/* ================= 1. NEW GOAL / COURSE WIZARD ================= */
