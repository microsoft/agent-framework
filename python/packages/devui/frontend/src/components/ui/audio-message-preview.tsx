import { useEffect, useRef, useState } from "react";
import { Download, Pause, Play, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getAudioContextConstructor, getWaveformPeaks } from "@/hooks/use-audio-recorder";

interface AudioPreviewData {
  blobUrl: string;
  durationSeconds?: number;
  waveformPeaks?: number[];
}

function formatDuration(seconds: number) {
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${(whole % 60).toString().padStart(2, "0")}`;
}

function WaveformBars({ peaks, progress }: { peaks: number[]; progress: number }) {
  const waveform = peaks.length ? peaks : [0.12, 0.28, 0.16, 0.35, 0.2, 0.5, 0.18, 0.3];
  return (
    <div className="flex h-full items-center gap-0.5" aria-hidden="true">
      {waveform.map((peak, index) => (
        <span
          key={index}
          className={`w-0.5 shrink-0 rounded-full ${
            index / waveform.length <= progress ? "bg-violet-500" : "bg-muted-foreground/45"
          }`}
          style={{ height: Math.max(3, Math.round(peak * 32)) }}
        />
      ))}
    </div>
  );
}

export function RecordingBar({
  recordingSeconds,
  inputLevel,
  statusLabel,
  onStop,
  onCancel,
}: {
  recordingSeconds: number;
  inputLevel: number;
  statusLabel?: string;
  onStop: () => void;
  onCancel: () => void;
}) {
  const bars = [8, 12, 16, 22, 28, 32, 30, 24, 18, 14, 12, 16, 20, 24, 18, 14, 12, 16];
  return (
    <div className="mx-auto flex w-full max-w-[760px] items-center gap-2" role="status">
      <div className="flex h-[72px] min-w-0 flex-1 items-center justify-between gap-5 rounded-full border border-border bg-background px-4 py-2 shadow-sm">
        <Button
          type="button"
          size="icon"
          onClick={onStop}
          className="h-11 w-11 shrink-0 rounded-full bg-violet-600 text-white hover:bg-violet-700"
          title="Stop recording and attach voice message"
          aria-label="Stop recording"
        >
          <Square className="h-4 w-4 fill-current" />
        </Button>
        <span aria-label="Recording duration" className="min-w-[4ch] text-center text-base font-semibold tabular-nums">
          {formatDuration(recordingSeconds)}
        </span>
        <div className="flex h-full flex-1 flex-col items-center justify-center gap-1 overflow-hidden">
          <div className="flex h-10 items-center gap-1 overflow-hidden" aria-hidden="true">
            {bars.map((height, index) => (
              <span
                key={index}
                className="w-1 shrink-0 animate-pulse rounded-full bg-violet-500 dark:bg-violet-400"
                style={{
                  height: Math.min(40, Math.max(6, Math.round(height * (0.35 + inputLevel * 0.9)))),
                  animationDelay: `${index * 80}ms`,
                  animationDuration: "900ms",
                }}
              />
            ))}
          </div>
          {statusLabel && <span className="h-3 text-[10px] leading-3 text-muted-foreground">{statusLabel}</span>}
        </div>
        <span className="sr-only">Recording voice message</span>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onCancel}
        className="h-10 w-10 shrink-0"
        title="Cancel recording"
        aria-label="Cancel recording"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

export function AudioMessagePreview({
  audio,
  label = "Voice recording preview",
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
  label?: string;
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
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(audio.durationSeconds || 0);
  const [peaks, setPeaks] = useState(audio.waveformPeaks || []);
  const [error, setError] = useState<string | null>(null);
  const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0;
  const previewWidth = Math.round(Math.min(maxWidth, Math.max(minWidth, 300 + duration * 18)));

  useEffect(() => {
    setCurrentTime(0);
    setIsPlaying(false);
    setDuration(audio.durationSeconds || 0);
    setPeaks(audio.waveformPeaks || []);
    setError(null);
    const Context = getAudioContextConstructor();
    // Remote sources remain playable without downloading and decoding the whole file.
    if (audio.waveformPeaks || !audio.blobUrl.startsWith("data:") || !Context) return;
    const controller = new AbortController();
    let cancelled = false;
    const analyze = async () => {
      const context = new Context();
      try {
        const response = await fetch(audio.blobUrl, { signal: controller.signal });
        if (!response.ok) throw new Error(`Audio waveform request failed (${response.status}).`);
        const decoded = await context.decodeAudioData(await response.arrayBuffer());
        if (!cancelled) {
          setPeaks(getWaveformPeaks(decoded));
          setDuration(decoded.duration);
        }
      } finally {
        await context.close();
      }
    };
    void analyze().catch((cause) => {
      if (!cancelled) console.warn("Could not generate audio waveform; playback is still available:", cause);
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [audio.blobUrl, audio.durationSeconds, audio.waveformPeaks]);

  const togglePlayback = async () => {
    const element = audioRef.current;
    if (!element) return;
    if (!element.paused) {
      element.pause();
      return;
    }
    setError(null);
    try {
      await element.play();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Audio playback failed.");
    }
  };

  const seekTo = (time: number) => {
    const nextTime = Math.min(duration, Math.max(0, time));
    if (audioRef.current) audioRef.current.currentTime = nextTime;
    setCurrentTime(nextTime);
  };

  return (
    <div className={`max-w-full ${className}`}>
      <div
        className="mx-auto max-w-full overflow-hidden rounded-full border bg-background text-foreground px-3 py-2 shadow-sm transition-[width]"
        style={{ width: `min(100%, ${previewWidth}px)` }}
      >
        <audio
          ref={audioRef}
          src={audio.blobUrl}
          aria-label={onRemove ? "Voice recording preview" : label}
          preload="metadata"
          autoPlay={autoPlay}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
          onDurationChange={(event) => {
            const seconds = event.currentTarget.duration;
            if (Number.isFinite(seconds)) setDuration(seconds);
          }}
          onEnded={() => setIsPlaying(false)}
          onError={() => setError("Audio could not be loaded. Download it or try again.")}
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
              aria-label={isPlaying ? "Pause recording preview" : "Play recording preview"}
            >
              {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current" />}
            </Button>
          )}
          <div className="min-w-0 flex-1 max-w-[560px]">
            <div className="mb-1 truncate text-xs font-medium">{label}</div>
            <div className="group relative h-8 overflow-hidden rounded-md px-1 focus-within:ring-2 focus-within:ring-violet-500">
              <WaveformBars peaks={peaks} progress={progress} />
              {previewBeforeSend && (
                <div
                  className="pointer-events-none absolute inset-x-3 top-1/2 h-6 -translate-y-1/2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 group-active:opacity-100"
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
              )}
              {previewBeforeSend && (
                <input
                  type="range"
                  min={0}
                  max={duration}
                  step={0.01}
                  value={currentTime}
                  aria-label="Audio playback position"
                  aria-valuetext={`${formatDuration(currentTime)} of ${formatDuration(duration)}`}
                  disabled={disabled || duration <= 0}
                  onChange={(event) => seekTo(Number(event.currentTarget.value))}
                  onKeyDown={(event) => {
                    const offsets: Record<string, number> = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 };
                    const time = event.key === "Home" ? 0 : event.key === "End" ? duration
                      : event.key in offsets ? currentTime + offsets[event.key] : undefined;
                    if (time !== undefined) {
                      event.preventDefault();
                      seekTo(time);
                    }
                  }}
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-default"
                />
              )}
            </div>
          </div>
          <span className="min-w-[4ch] text-sm font-semibold tabular-nums">
            {formatDuration(currentTime || duration)}
          </span>
          {onRemove && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={onRemove}
              disabled={disabled}
              className="h-8 w-8 shrink-0"
              title="Remove recording"
              aria-label="Remove recording"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
          {downloadFilename && (
            <a
              href={audio.blobUrl}
              download={downloadFilename}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              title="Download audio"
              aria-label="Download audio"
            >
              <Download className="h-4 w-4" />
            </a>
          )}
        </div>
      </div>
      {error && <div role="alert" className="mt-1 text-xs text-destructive">{error}</div>}
    </div>
  );
}
