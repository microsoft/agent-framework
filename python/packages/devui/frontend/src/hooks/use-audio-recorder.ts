import { useCallback, useEffect, useRef, useState } from "react";

interface AudioRecorderOptions {
  maxDurationSeconds: number;
  maxPayloadBytes: number;
  sampleRate: number;
  echoCancellation: boolean;
  noiseSuppression: boolean;
  autoGainControl: boolean;
  autoStopOnSilence: boolean;
  silenceThreshold: number;
  silenceDurationMs: number;
  minimumRecordingMs: number;
}

const MICROPHONE_WARMUP_MS = 600;

export interface RecordedAudio {
  data: string;
  format: "wav";
  blobUrl: string;
  sizeBytes: number;
  durationSeconds: number;
  waveformPeaks: number[];
}

interface RecordingSession {
  stream?: MediaStream;
  recorder?: MediaRecorder;
  timer?: number;
  deadline?: number;
  warmup?: number;
  meterFrame?: number;
  meterContext?: AudioContext;
}

function releaseSession(session: RecordingSession) {
  window.clearInterval(session.timer);
  window.clearTimeout(session.deadline);
  window.clearTimeout(session.warmup);
  if (session.meterFrame !== undefined) window.cancelAnimationFrame(session.meterFrame);
  session.stream?.getTracks().forEach((track) => track.stop());
  session.stream = undefined;
  if (session.meterContext) {
    void session.meterContext.close().catch((cause) => console.warn("Could not close microphone meter:", cause));
    session.meterContext = undefined;
  }
  if (session.recorder?.state === "recording") session.recorder.stop();
}

export function getAudioContextConstructor() {
  return window.AudioContext ||
    (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
}

export function getWaveformPeaks(buffer: AudioBuffer): number[] {
  const samples = buffer.getChannelData(0);
  const count = Math.min(64, samples.length);
  const peaks = Array.from({ length: count }, (_, index) => {
    const start = Math.floor(index * samples.length / count);
    const end = Math.floor((index + 1) * samples.length / count);
    let peak = 0;
    for (let sample = start; sample < end; sample++) peak = Math.max(peak, Math.abs(samples[sample]));
    return peak;
  });
  const maximum = Math.max(...peaks, 0.01);
  return peaks.map((peak) => peak / maximum);
}

function encodeWav(audioBuffer: AudioBuffer): Blob {
  const samples = audioBuffer.getChannelData(0);
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, audioBuffer.sampleRate, true);
  view.setUint32(28, audioBuffer.sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(44 + index * 2, clamped * (clamped < 0 ? 0x8000 : 0x7fff), true);
  });
  return new Blob([view], { type: "audio/wav" });
}

async function normalizeToWav(blob: Blob, sampleRate: number) {
  const AudioContextConstructor = getAudioContextConstructor();
  if (!AudioContextConstructor) throw new Error("This browser cannot convert microphone audio.");
  const context = new AudioContextConstructor();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * sampleRate)), sampleRate);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    return {
      wav: encodeWav(rendered),
      durationSeconds: rendered.duration,
      waveformPeaks: getWaveformPeaks(rendered),
    };
  } finally {
    await context.close();
  }
}

async function blobToBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

export function useAudioRecorder(options: AudioRecorderOptions) {
  const [stage, setStage] = useState<"idle" | "starting" | "recording" | "processing">("idle");
  const [recording, setRecording] = useState<RecordedAudio | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [inputLevel, setInputLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const sessionRef = useRef<RecordingSession | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  const clearRecording = useCallback(() => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = null;
    setRecording(null);
  }, []);

  const cancelRecording = useCallback(() => {
    const session = sessionRef.current;
    sessionRef.current = null;
    if (session) releaseSession(session);
    setInputLevel(0);
    setStage("idle");
    setError(null);
  }, []);

  useEffect(() => () => {
    const session = sessionRef.current;
    sessionRef.current = null;
    if (session) releaseSession(session);
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  const stopRecording = useCallback(() => {
    const session = sessionRef.current;
    if (session && !session.recorder) {
      cancelRecording();
      return;
    }
    if (session?.recorder?.state !== "recording") return;
    setStage("processing");
    setInputLevel(0);
    releaseSession(session);
  }, [cancelRecording]);

  const startRecording = useCallback(async (autoStopOnSilence = options.autoStopOnSilence) => {
    if (sessionRef.current) return;
    const session: RecordingSession = {};
    sessionRef.current = session;
    clearRecording();
    setError(null);
    setRecordingSeconds(0);
    setInputLevel(0);
    setStage("starting");

    const fail = (cause: unknown) => {
      if (sessionRef.current !== session) return;
      cancelRecording();
      setError(cause instanceof Error ? cause.message : "Microphone recording failed.");
    };

    try {
      session.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: options.sampleRate,
          echoCancellation: options.echoCancellation,
          noiseSuppression: options.noiseSuppression,
          autoGainControl: options.autoGainControl,
        },
      });
      if (sessionRef.current !== session) {
        releaseSession(session);
        return;
      }
      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]
        .find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(session.stream, mimeType ? { mimeType } : undefined);
      session.recorder = recorder;
      const chunks: Blob[] = [];
      let size = 0;
      recorder.ondataavailable = (event) => {
        if (sessionRef.current !== session) return;
        size += event.data.size;
        if (size > options.maxPayloadBytes) {
          fail(new Error(`Recording exceeds the ${Math.round(options.maxPayloadBytes / 1024 / 1024)} MB limit.`));
        } else {
          chunks.push(event.data);
        }
      };
      recorder.onerror = () => fail(new Error("Microphone recording failed. Please try again."));
      recorder.onstop = async () => {
        releaseSession(session);
        if (sessionRef.current !== session) return;
        setStage("processing");
        try {
          const { wav, durationSeconds, waveformPeaks } = await normalizeToWav(
            new Blob(chunks, { type: recorder.mimeType }), options.sampleRate
          );
          if (wav.size > options.maxPayloadBytes) {
            throw new Error(`Recording exceeds the ${Math.round(options.maxPayloadBytes / 1024 / 1024)} MB limit.`);
          }
          const data = await blobToBase64(wav);
          // Permission, decoding, and encoding can finish after cancellation or unmount.
          if (sessionRef.current !== session) return;
          const blobUrl = URL.createObjectURL(wav);
          previewUrlRef.current = blobUrl;
          setRecording({ data, format: "wav", blobUrl, sizeBytes: wav.size, durationSeconds, waveformPeaks });
          sessionRef.current = null;
          setStage("idle");
        } catch (cause) {
          fail(cause);
        }
      };
      const AudioContextConstructor = getAudioContextConstructor();
      if (!AudioContextConstructor) throw new Error("This browser cannot meter microphone audio.");
      const meterContext = new AudioContextConstructor();
      session.meterContext = meterContext;
      const analyser = meterContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.75;
      meterContext.createMediaStreamSource(session.stream).connect(analyser);
      if (meterContext.state === "suspended") {
        void meterContext.resume().catch((cause) => console.warn("Could not resume microphone meter:", cause));
      }
      const levels = new Uint8Array(analyser.fftSize);
      recorder.start(250);
      const started = Date.now();
      let silenceStartedAt: number | null = null;
      const updateInputLevel = () => {
        if (sessionRef.current !== session) return;
        analyser.getByteTimeDomainData(levels);
        let sumSquares = 0;
        for (const sample of levels) sumSquares += ((sample - 128) / 128) ** 2;
        const level = Math.min(1, Math.sqrt(sumSquares / levels.length) * 4);
        setInputLevel(level);
        const now = Date.now();
        if (autoStopOnSilence && now - started >= Math.max(MICROPHONE_WARMUP_MS, options.minimumRecordingMs)) {
          silenceStartedAt = level <= options.silenceThreshold ? silenceStartedAt ?? now : null;
          if (silenceStartedAt !== null && now - silenceStartedAt >= options.silenceDurationMs) {
            stopRecording();
            return;
          }
        }
        session.meterFrame = window.requestAnimationFrame(updateInputLevel);
      };
      session.meterFrame = window.requestAnimationFrame(updateInputLevel);
      session.warmup = window.setTimeout(() => {
        if (sessionRef.current === session) setStage("recording");
      }, MICROPHONE_WARMUP_MS);
      session.timer = window.setInterval(() => {
        setRecordingSeconds(Math.floor((Date.now() - started) / 1000));
      }, 250);
      session.deadline = window.setTimeout(stopRecording, options.maxDurationSeconds * 1000);
    } catch (cause) {
      fail(cause);
    }
  }, [cancelRecording, clearRecording, options, stopRecording]);

  return {
    isSupported: typeof window !== "undefined" && window.isSecureContext &&
      Boolean(typeof navigator.mediaDevices?.getUserMedia === "function" && window.MediaRecorder &&
        getAudioContextConstructor() && window.OfflineAudioContext),
    isStarting: stage === "starting",
    isRecording: stage === "recording",
    isProcessing: stage === "processing",
    recording,
    recordingSeconds,
    inputLevel,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
    clearRecording,
  };
}
