import { useEffect, useRef, useState } from "react";
import { Download, Pause, Play, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const AUDIO_UI_TEXT = {
  audioPlaybackPosition: "Audio playback position",
  cancelRecording: "Cancel recording",
  pausePreview: "Pause recording preview",
  playPreview: "Play recording preview",
  downloadAudio: "Download audio",
  removeRecording: "Remove recording",
  stopRecording: "Stop recording and attach voice message",
  recordingMessage: "Recording voice message",
};

export interface AudioPreviewData {
  blobUrl: string;
  durationSeconds: number;
  waveformPeaks: number[];
}

function formatAudioDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

function WaveformBars({
  peaks,
  progress,
  maxHeight = 32,
}: {
  peaks: number[];
  progress: number;
  maxHeight?: number;
}) {
  const normalizedPeaks = peaks.length > 0 ? peaks : [0.12, 0.28, 0.16, 0.35, 0.2, 0.5, 0.18, 0.3];

  return (
    <div className="flex h-full items-center gap-0.5" aria-hidden="true">
      {normalizedPeaks.map((peak, index) => {
        const isPlayed = index / normalizedPeaks.length <= progress;
        return (
          <span
            key={`${index}-${peak}`}
            className={isPlayed ? "w-0.5 rounded-full bg-violet-500" : "w-0.5 rounded-full bg-muted-foreground/45"}
            style={{ height: Math.max(3, Math.round(peak * maxHeight)) }}
          />
        );
      })}
    </div>
  );
}

function RecordingWaveform() {
  const bars = [8, 14, 22, 28, 32, 26, 20, 14, 10, 18, 12, 16];

  return (
    <div className="flex items-center gap-1" aria-hidden="true">
      {bars.map((height, index) => (
        <span
          key={`${height}-${index}`}
          className="w-1 rounded-full bg-violet-500 dark:bg-violet-400 animate-pulse"
          style={{
            height,
            animationDelay: `${index * 80}ms`,
            animationDuration: "900ms",
          }}
        />
      ))}
    </div>
  );
}

export function RecordingBar({
  recordingSeconds,
  onStop,
  onCancel,
}: {
  recordingSeconds: number;
  onStop: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="flex flex-1 items-center gap-2">
      <div className="flex min-h-[56px] flex-1 items-center justify-between gap-5 rounded-full border border-border bg-background px-4 py-2 shadow-sm">
        <Button
          type="button"
          size="icon"
          onClick={onStop}
          className="h-11 w-11 shrink-0 rounded-full bg-violet-600 text-white hover:bg-violet-700"
          title={AUDIO_UI_TEXT.stopRecording}
          aria-label={AUDIO_UI_TEXT.stopRecording}
        >
          <Square className="h-4 w-4 fill-current" />
        </Button>
        <div className="min-w-[4ch] text-center text-base font-semibold tabular-nums">
          {formatAudioDuration(recordingSeconds)}
        </div>
        <div className="flex flex-1 justify-center">
          <RecordingWaveform />
        </div>
        <span className="sr-only">{AUDIO_UI_TEXT.recordingMessage}</span>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onCancel}
        className="h-10 w-10 shrink-0"
        title={AUDIO_UI_TEXT.cancelRecording}
        aria-label={AUDIO_UI_TEXT.cancelRecording}
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

export function AudioMessagePreview({
  audio,
  label,
  disabled,
  previewBeforeSend = true,
  onRemove,
  autoPlay = false,
  downloadFilename,
  maxWidth = 760,
  minWidth = 420,
  className = "",
}: {
  audio: AudioPreviewData;
  label: string;
  disabled?: boolean;
  previewBeforeSend?: boolean;
  onRemove?: () => void;
  autoPlay?: boolean;
  downloadFilename?: string;
  maxWidth?: number;
  minWidth?: number;
  className?: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const lastAutoPlayedUrlRef = useRef<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const duration = Math.max(audio.durationSeconds, 0.01);
  const progress = Math.min(1, Math.max(0, currentTime / duration));
  const previewWidth = Math.round(Math.min(maxWidth, Math.max(minWidth, 320 + duration * 32)));

  useEffect(() => {
    if (!autoPlay || lastAutoPlayedUrlRef.current === audio.blobUrl) {
      return;
    }

    const audioElement = audioRef.current;
    if (!audioElement) {
      return;
    }

    lastAutoPlayedUrlRef.current = audio.blobUrl;
    audioElement.play().catch(() => {
      setIsPlaying(false);
    });
  }, [audio.blobUrl, autoPlay]);

  const seekTo = (time: number) => {
    const nextTime = Math.min(duration, Math.max(0, time));
    const audioElement = audioRef.current;
    if (audioElement) {
      audioElement.currentTime = nextTime;
    }
    setCurrentTime(nextTime);
  };

  const togglePlayback = async () => {
    const audioElement = audioRef.current;
    if (!audioElement) {
      return;
    }

    if (audioElement.paused) {
      try {
        await audioElement.play();
      } catch {
        setIsPlaying(false);
      }
    } else {
      audioElement.pause();
    }
  };

  const handleScrubPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const pointerId = event.pointerId;
    const seekFromClientX = (clientX: number) => {
      const rect = target.getBoundingClientRect();
      const ratio = rect.width === 0 ? 0 : (clientX - rect.left) / rect.width;
      seekTo(ratio * duration);
    };
    const updateFromPointer = (pointerEvent: PointerEvent) => seekFromClientX(pointerEvent.clientX);
    const cleanupPointerListeners = () => {
      target.removeEventListener("pointermove", updateFromPointer);
      target.removeEventListener("pointerup", cleanupPointerListeners);
      target.removeEventListener("pointercancel", cleanupPointerListeners);
      setIsScrubbing(false);
      if (target.hasPointerCapture(pointerId)) {
        target.releasePointerCapture(pointerId);
      }
    };

    if (!previewBeforeSend || disabled) {
      return;
    }

    setIsScrubbing(true);
    seekFromClientX(event.clientX);
    target.setPointerCapture(pointerId);
    target.addEventListener("pointermove", updateFromPointer);
    target.addEventListener("pointerup", cleanupPointerListeners);
    target.addEventListener("pointercancel", cleanupPointerListeners);
  };

  return (
    <div
      className={`mx-auto max-w-full rounded-full border bg-background px-3 py-2 shadow-sm transition-[width] ${className}`}
      style={{ width: `min(100%, ${previewWidth}px)` }}
    >
      <audio
        ref={audioRef}
        src={audio.blobUrl}
        preload="metadata"
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onEnded={() => setIsPlaying(false)}
        className="hidden"
      />
      <div className="flex items-center gap-3">
        {previewBeforeSend && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={togglePlayback}
            disabled={disabled}
            className="h-8 w-8 shrink-0 rounded-full text-violet-600 hover:text-violet-700"
            aria-label={isPlaying ? AUDIO_UI_TEXT.pausePreview : AUDIO_UI_TEXT.playPreview}
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current" />}
          </Button>
        )}
        <div className="min-w-0 flex-1">
          <div className="mb-1 text-xs font-medium">{label}</div>
          {previewBeforeSend ? (
            <div
              role="slider"
              aria-label={AUDIO_UI_TEXT.audioPlaybackPosition}
              aria-valuemin={0}
              aria-valuemax={Math.round(duration)}
              aria-valuenow={Math.round(currentTime)}
              aria-valuetext={`${formatAudioDuration(Math.floor(currentTime))} of ${formatAudioDuration(
                Math.floor(duration)
              )}`}
              aria-disabled={disabled || undefined}
              tabIndex={disabled ? -1 : 0}
              onPointerDown={handleScrubPointerDown}
              onKeyDown={(event) => {
                if (disabled) {
                  return;
                }

                if (event.key === "ArrowLeft") {
                  event.preventDefault();
                  seekTo(currentTime - 1);
                } else if (event.key === "ArrowRight") {
                  event.preventDefault();
                  seekTo(currentTime + 1);
                } else if (event.key === "ArrowDown") {
                  event.preventDefault();
                  seekTo(currentTime - 1);
                } else if (event.key === "ArrowUp") {
                  event.preventDefault();
                  seekTo(currentTime + 1);
                } else if (event.key === "Home") {
                  event.preventDefault();
                  seekTo(0);
                } else if (event.key === "End") {
                  event.preventDefault();
                  seekTo(duration);
                }
              }}
              data-scrubbing={isScrubbing}
              className="group relative h-8 cursor-pointer overflow-hidden rounded-md px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 aria-disabled:cursor-default"
            >
              <div className="h-full">
                <WaveformBars peaks={audio.waveformPeaks} progress={progress} />
              </div>
              <div
                className="pointer-events-none absolute inset-x-3 top-1/2 h-6 -translate-y-1/2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100 group-data-[scrubbing=true]:opacity-100"
                aria-hidden="true"
              >
                <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-muted-foreground/35" />
                <div
                  className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-violet-500/80"
                  style={{ width: `${progress * 100}%` }}
                />
                <div
                  className="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-4 border-background bg-violet-500 shadow-md"
                  style={{ left: `${progress * 100}%` }}
                />
              </div>
            </div>
          ) : (
            <div className="h-8 overflow-hidden px-1">
              <WaveformBars peaks={audio.waveformPeaks} progress={progress} />
            </div>
          )}
        </div>
        <div className="min-w-[4ch] text-sm font-semibold tabular-nums">
          {formatAudioDuration(Math.floor(currentTime || audio.durationSeconds))}
        </div>
        {onRemove && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onRemove}
            disabled={disabled}
            className="h-8 w-8 shrink-0"
            title={AUDIO_UI_TEXT.removeRecording}
            aria-label={AUDIO_UI_TEXT.removeRecording}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
        {downloadFilename && (
          <a
            href={audio.blobUrl}
            download={downloadFilename}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title={AUDIO_UI_TEXT.downloadAudio}
            aria-label={AUDIO_UI_TEXT.downloadAudio}
          >
            <Download className="h-4 w-4" />
          </a>
        )}
      </div>
    </div>
  );
}
