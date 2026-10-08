import { useRef, useState } from "react";
import { Pause, Play, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const AUDIO_UI_TEXT = {
  audioPlaybackPosition: "Audio playback position",
  cancelRecording: "Cancel recording",
  pausePreview: "Pause recording preview",
  playPreview: "Play recording preview",
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
  className = "",
}: {
  audio: AudioPreviewData;
  label: string;
  disabled?: boolean;
  previewBeforeSend?: boolean;
  onRemove?: () => void;
  className?: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const duration = Math.max(audio.durationSeconds, 0.01);
  const progress = Math.min(1, Math.max(0, currentTime / duration));
  const previewWidth = Math.round(Math.min(760, Math.max(420, 320 + duration * 32)));

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
      if (target.hasPointerCapture(pointerId)) {
        target.releasePointerCapture(pointerId);
      }
    };

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
        <button
          type="button"
          onClick={() => previewBeforeSend && setIsExpanded((expanded) => !expanded)}
          disabled={!previewBeforeSend}
          className="flex min-w-0 flex-1 items-center gap-4 text-left disabled:cursor-default"
          aria-label={previewBeforeSend ? `${label}. Show audio scrubber` : label}
        >
          <div className="min-w-0 flex-1">
            <div className="mb-1 text-xs font-medium">{label}</div>
            <div className="h-8 overflow-hidden">
              <WaveformBars peaks={audio.waveformPeaks} progress={progress} />
            </div>
          </div>
          <div className="min-w-[4ch] text-sm font-semibold tabular-nums">
            {formatAudioDuration(Math.floor(currentTime || audio.durationSeconds))}
          </div>
        </button>
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
      </div>
      {previewBeforeSend && isExpanded && (
        <div
          role="slider"
          aria-label={AUDIO_UI_TEXT.audioPlaybackPosition}
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={Math.round(currentTime)}
          aria-valuetext={`${formatAudioDuration(Math.floor(currentTime))} of ${formatAudioDuration(
            Math.floor(duration)
          )}`}
          tabIndex={0}
          onPointerDown={handleScrubPointerDown}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") {
              event.preventDefault();
              seekTo(currentTime - 1);
            } else if (event.key === "ArrowRight") {
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
          className="relative mt-2 h-9 cursor-pointer rounded-full px-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
        >
          <div className="absolute inset-x-2 top-1/2 h-1 -translate-y-1/2 rounded-full bg-muted-foreground/40" />
          <div
            className="absolute left-2 top-1/2 h-1 -translate-y-1/2 rounded-full bg-violet-500"
            style={{ width: `calc(${progress * 100}% - ${progress * 16}px)` }}
          />
          <div className="absolute inset-x-10 top-1/2 h-7 -translate-y-1/2 overflow-hidden opacity-55">
            <WaveformBars peaks={audio.waveformPeaks} progress={progress} maxHeight={28} />
          </div>
          <div
            className="absolute top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full border-4 border-background bg-violet-500 shadow"
            style={{ left: `calc(8px + ${progress * 100}% - ${progress * 16}px)` }}
          />
        </div>
      )}
    </div>
  );
}
