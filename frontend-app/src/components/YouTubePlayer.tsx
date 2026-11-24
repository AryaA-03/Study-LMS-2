import React, { useEffect, useRef, useState } from 'react';
import { ExternalLink, PlayCircle } from 'lucide-react';

declare global {
  interface Window {
    YT?: any;
    onYouTubeIframeAPIReady?: () => void;
  }
}

interface YouTubePlayerProps {
  videoId?: string | null;
  videoUrl?: string | null;
  startSec?: number;
  endSec?: number;
  playbackSpeed?: number;
  seekRequest?: { sec: number; ts: number } | null;
  lessonTitle?: string;
  onTimeUpdate?: (sec: number) => void;
}

let ytApiPromise: Promise<void> | null = null;
function loadYTApi(): Promise<void> {
  if (window.YT && window.YT.Player) return Promise.resolve();
  if (ytApiPromise) return ytApiPromise;
  ytApiPromise = new Promise((resolve) => {
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      if (prev) prev();
      resolve();
    };
    if (!document.querySelector('script[src*="youtube.com/iframe_api"]')) {
      const tag = document.createElement('script');
      tag.src = 'https://www.youtube.com/iframe_api';
      document.head.appendChild(tag);
    }
  });
  return ytApiPromise;
}

export function extractVideoId(videoId?: string | null, videoUrl?: string | null): string | null {
  if (videoId && /^[a-zA-Z0-9_-]{11}$/.test(videoId)) return videoId;
  if (!videoUrl) return null;
  const m = videoUrl.match(/(?:v=|youtu\.be\/|embed\/)([a-zA-Z0-9_-]{11})/);
  return m ? m[1] : null;
}

export const YouTubePlayer: React.FC<YouTubePlayerProps> = ({
  videoId,
  videoUrl,
  startSec = 0,
  endSec,
  playbackSpeed = 1.0,
  seekRequest,
  lessonTitle,
  onTimeUpdate,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<any>(null);
  const readyRef = useRef(false);
  const pendingSeekRef = useRef<number | null>(null);
  const [embedError, setEmbedError] = useState(false);

  const resolvedId = extractVideoId(videoId, videoUrl);

  useEffect(() => {
    setEmbedError(false);
    if (!resolvedId) {
      if (playerRef.current) {
        try {
          playerRef.current.destroy();
        } catch {
          // ignore
        }
        playerRef.current = null;
        readyRef.current = false;
      }
      return;
    }

    let cancelled = false;
    loadYTApi().then(() => {
      if (cancelled || !containerRef.current) return;
      if (playerRef.current && readyRef.current) {
        try {
          playerRef.current.cueVideoById({
            videoId: resolvedId,
            startSeconds: startSec || 0,
            ...(endSec && endSec > (startSec || 0) ? { endSeconds: endSec } : {}),
          });
          if (playbackSpeed) playerRef.current.setPlaybackRate(playbackSpeed);
          return;
        } catch {
          // rebuild below
        }
      }

      containerRef.current.innerHTML = '';
      const mountEl = document.createElement('div');
      containerRef.current.appendChild(mountEl);

      playerRef.current = new window.YT.Player(mountEl, {
        width: '100%',
        height: '100%',
        videoId: resolvedId,
        playerVars: {
          rel: 0,
          modestbranding: 1,
          start: Math.floor(startSec || 0),
          ...(endSec && endSec > (startSec || 0) ? { end: Math.floor(endSec) } : {}),
        },
        events: {
          onReady: (ev: any) => {
            readyRef.current = true;
            try {
              if (playbackSpeed) ev.target.setPlaybackRate(playbackSpeed);
              if (pendingSeekRef.current !== null) {
                ev.target.seekTo(pendingSeekRef.current, true);
                ev.target.playVideo();
                pendingSeekRef.current = null;
              }
            } catch {
              // ignore
            }
          },
          onError: () => setEmbedError(true),
        },
      });
    });

    return () => {
      cancelled = true;
    };
  }, [resolvedId, startSec, endSec]);

  useEffect(() => {
    return () => {
      if (playerRef.current) {
        try {
          playerRef.current.destroy();
        } catch {
          // ignore
        }
        playerRef.current = null;
        readyRef.current = false;
      }
    };
  }, []);


  useEffect(() => {
    if (!onTimeUpdate) return;
    const timer = window.setInterval(() => {
      try {
        if (playerRef.current && readyRef.current && typeof playerRef.current.getPlayerState === 'function') {
          if (playerRef.current.getPlayerState() === 1) {
            const cur = Math.floor(playerRef.current.getCurrentTime() || 0);
            onTimeUpdate(cur);
          }
        }
      } catch {
        // ignore
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [onTimeUpdate]);

  useEffect(() => {
    if (playerRef.current && readyRef.current && playbackSpeed) {
      try {
        playerRef.current.setPlaybackRate(playbackSpeed);
      } catch {
        // ignore
      }
    }
  }, [playbackSpeed]);

  useEffect(() => {
    if (!seekRequest) return;
    if (playerRef.current && readyRef.current) {
      try {
        playerRef.current.seekTo(seekRequest.sec, true);
        playerRef.current.playVideo();
      } catch {
        pendingSeekRef.current = seekRequest.sec;
      }
    } else {
      pendingSeekRef.current = seekRequest.sec;
    }
  }, [seekRequest]);

  if (!resolvedId) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-center">
        <PlayCircle className="mb-2 h-8 w-8 text-[var(--fg-muted)]" />
        <p className="text-sm font-medium text-[var(--fg-primary)]">{lessonTitle || 'Select a lesson to begin'}</p>
        <p className="mt-1 text-xs text-[var(--fg-secondary)]">
          This lesson is a reading / PDF / manual transcript unit — study directly in the structured notes below.
        </p>
      </div>
    );
  }

  if (embedError) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-center">
        <p className="text-sm font-medium text-[var(--fg-primary)]">YouTube embed unavailable for this video</p>
        <a
          href={`https://www.youtube.com/watch?v=${resolvedId}&t=${Math.floor(startSec || 0)}s`}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-semibold text-white"
        >
          Open on YouTube <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl bg-black shadow-sm">
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
};
