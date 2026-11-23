import React, { useEffect, useRef, useState } from 'react';
import { ExternalLink, VideoOff } from 'lucide-react';

interface YouTubePlayerProps {
  videoId?: string;
  startSec?: number;
  playbackSpeed?: number;
  seekRequest?: { sec: number; nonce: number } | null;
}

declare global {
  interface Window {
    YT?: any;
    onYouTubeIframeAPIReady?: () => void;
  }
}

export const YouTubePlayer: React.FC<YouTubePlayerProps> = ({
  videoId,
  startSec = 0,
  playbackSpeed = 1.0,
  seekRequest,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<any>(null);
  const readyRef = useRef(false);
  const pendingRef = useRef<{ videoId: string; startSec: number } | null>(null);
  const [embedError, setEmbedError] = useState(false);

  useEffect(() => {
    setEmbedError(false);
    if (!videoId) return;

    const loadSlice = (vid: string, sec: number) => {
      if (!readyRef.current || !playerRef.current?.loadVideoById) {
        pendingRef.current = { videoId: vid, startSec: sec };
        return;
      }
      try {
        playerRef.current.loadVideoById({ videoId: vid, startSeconds: Math.max(0, Math.floor(sec)) });
        if (playbackSpeed && typeof playerRef.current.setPlaybackRate === 'function') {
          playerRef.current.setPlaybackRate(playbackSpeed);
        }
      } catch {
        setEmbedError(true);
      }
    };

    const initPlayer = () => {
      if (!mountRef.current || playerRef.current || !window.YT?.Player) return;
      playerRef.current = new window.YT.Player(mountRef.current, {
        width: '100%',
        height: '100%',
        videoId,
        playerVars: { start: Math.max(0, Math.floor(startSec)), rel: 0, modestbranding: 1 },
        events: {
          onReady: () => {
            readyRef.current = true;
            if (playbackSpeed && typeof playerRef.current?.setPlaybackRate === 'function') {
              try {
                playerRef.current.setPlaybackRate(playbackSpeed);
              } catch {
                /* ignore */
              }
            }
            if (pendingRef.current) {
              const p = pendingRef.current;
              pendingRef.current = null;
              loadSlice(p.videoId, p.startSec);
            }
          },
          onError: () => setEmbedError(true),
        },
      });
    };

    if (window.YT?.Player) {
      if (playerRef.current) {
        loadSlice(videoId, startSec);
      } else {
        initPlayer();
      }
    } else {
      pendingRef.current = { videoId, startSec };
      if (!document.querySelector('script[src*="youtube.com/iframe_api"]')) {
        const tag = document.createElement('script');
        tag.src = 'https://www.youtube.com/iframe_api';
        tag.async = true;
        document.head.appendChild(tag);
      }
      const prevReady = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        prevReady?.();
        initPlayer();
      };
    }
  }, [videoId, startSec, playbackSpeed]);

  useEffect(() => {
    if (!seekRequest || !readyRef.current || !playerRef.current?.seekTo) return;
    try {
      playerRef.current.seekTo(Math.max(0, seekRequest.sec), true);
      playerRef.current.playVideo?.();
    } catch {
      /* ignore */
    }
  }, [seekRequest]);

  if (!videoId) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-subtle text-fg-secondary text-sm rounded-lg border border-border-def p-6">
        <VideoOff className="w-6 h-6 mb-2 opacity-60" />
        <span>Select a video lesson to start watching</span>
      </div>
    );
  }

  if (embedError) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-subtle text-fg-secondary text-sm rounded-lg border border-border-def p-6 gap-2">
        <VideoOff className="w-6 h-6 opacity-70" />
        <span>This video could not be embedded (offline or embed disabled).</span>
        <a
          href={`https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}&t=${Math.floor(startSec)}s`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-accent-text hover:underline font-medium"
        >
          Open on YouTube <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>
    );
  }

  return (
    <div className="w-full h-full rounded-lg overflow-hidden bg-black border border-border-def">
      <div ref={mountRef} className="w-full h-full" />
    </div>
  );
};
