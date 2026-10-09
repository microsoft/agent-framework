import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export interface AudioRecorderOptions {
  maxDurationSeconds: number;
  maxPayloadBytes: number;
  sampleRate: number;
  echoCancellation: boolean;
  noiseSuppression: boolean;
  autoGainControl: boolean;
}

export interface RecordedAudio {
  data: string;
  format: SupportedAudioFormat;
  blobUrl: string;
  durationSeconds: number;
  sizeBytes: number;
  waveformPeaks: number[];
}

export type SupportedAudioFormat = "wav" | "mp3";

export interface AudioAnalysis {
  durationSeconds: number;
  waveformPeaks: number[];
}

export const SUPPORTED_INPUT_AUDIO_ACCEPT = "audio/wav,audio/x-wav,audio/mpeg,audio/mp3,.wav,.mp3";

const MP3_MEDIA_TYPES = new Set(["audio/mp3", "audio/mpeg", "audio/x-mpeg", "audio/mpeg3", "audio/x-mpeg-3"]);
const AUDIO_FILE_EXTENSION_PATTERN = /\.(aac|flac|m4a|mp3|ogg|wav)$/i;
const MICROPHONE_WARMUP_MS = 600;

function getAudioContextConstructor(): typeof AudioContext | undefined {
  return window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
}

function pickMimeType(): string | undefined {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];

  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate));
}

function writeString(view: DataView, offset: number, value: string): void {
  for (let i = 0; i < value.length; i++) {
    view.setUint8(offset + i, value.charCodeAt(i));
  }
}

function encodeWav(audioBuffer: AudioBuffer): Blob {
  const channelData = audioBuffer.getChannelData(0);
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample;
  const byteRate = audioBuffer.sampleRate * blockAlign;
  const dataSize = channelData.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, audioBuffer.sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (const sample of channelData) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += bytesPerSample;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function createWaveformPeaks(audioBuffer: AudioBuffer, peakCount = 64): number[] {
  const channelData = audioBuffer.getChannelData(0);
  const samplesPerPeak = Math.max(1, Math.floor(channelData.length / peakCount));
  const peaks: number[] = [];
  let loudestPeak = 0;

  for (let peakIndex = 0; peakIndex < peakCount; peakIndex++) {
    const start = peakIndex * samplesPerPeak;
    const end = Math.min(start + samplesPerPeak, channelData.length);
    let peak = 0;

    for (let sampleIndex = start; sampleIndex < end; sampleIndex++) {
      peak = Math.max(peak, Math.abs(channelData[sampleIndex]));
    }

    peaks.push(peak);
    loudestPeak = Math.max(loudestPeak, peak);
  }

  if (loudestPeak === 0) {
    return peaks.map(() => 0.08);
  }

  return peaks.map((peak) => Math.max(0.08, peak / loudestPeak));
}

async function normalizeToWav(blob: Blob, sampleRate: number): Promise<{ blob: Blob; waveformPeaks: number[] }> {
  const AudioContextConstructor = getAudioContextConstructor();
  if (!AudioContextConstructor) {
    throw new Error("Audio recording requires AudioContext support in this browser.");
  }

  const audioContext = new AudioContextConstructor();
  try {
    const decoded = await audioContext.decodeAudioData(await blob.arrayBuffer());
    const targetSampleRate = sampleRate || decoded.sampleRate;
    const duration = decoded.duration;
    const frameCount = Math.max(1, Math.ceil(duration * targetSampleRate));
    const offlineContext = new OfflineAudioContext(1, frameCount, targetSampleRate);
    const source = offlineContext.createBufferSource();
    source.buffer = decoded;
    source.connect(offlineContext.destination);
    source.start(0);
    const rendered = await offlineContext.startRendering();
    return {
      blob: encodeWav(rendered),
      waveformPeaks: createWaveformPeaks(rendered),
    };
  } finally {
    await audioContext.close();
  }
}

async function blobToBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const chunkSize = 0x8000;
  let binary = "";

  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }

  return btoa(binary);
}

export async function analyzeAudioBlob(blob: Blob): Promise<AudioAnalysis> {
  const AudioContextConstructor = getAudioContextConstructor();
  if (!AudioContextConstructor) {
    throw new Error("Audio preview requires AudioContext support in this browser.");
  }

  const audioContext = new AudioContextConstructor();
  try {
    const decoded = await audioContext.decodeAudioData(await blob.arrayBuffer());
    return {
      durationSeconds: decoded.duration,
      waveformPeaks: createWaveformPeaks(decoded),
    };
  } finally {
    await audioContext.close();
  }
}

export function looksLikeAudioFile(file: File): boolean {
  return file.type.startsWith("audio/") || AUDIO_FILE_EXTENSION_PATTERN.test(file.name);
}

export function getSupportedInputAudioFormat(file: File): SupportedAudioFormat | null {
  const mediaType = file.type.split(";")[0].trim().toLowerCase();
  const fileName = file.name.toLowerCase();

  if (mediaType === "audio/wav" || mediaType === "audio/x-wav" || fileName.endsWith(".wav")) {
    return "wav";
  }

  if (MP3_MEDIA_TYPES.has(mediaType) || fileName.endsWith(".mp3")) {
    return "mp3";
  }

  return null;
}

export function createAudioBlobFromBase64(data: string, format: SupportedAudioFormat): { blob: Blob; data: string } {
  const mediaType = format === "mp3" ? "audio/mpeg" : "audio/wav";
  const normalizedData = data.startsWith("data:") ? data.split(",", 2)[1] ?? "" : data;
  const binary = atob(normalizedData);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index++) {
    bytes[index] = binary.charCodeAt(index);
  }

  return {
    blob: new Blob([bytes], { type: mediaType }),
    data: normalizedData,
  };
}

export async function createRecordedAudioFromBlob(
  blob: Blob,
  format: SupportedAudioFormat,
  durationSeconds?: number,
  waveformPeaks?: number[]
): Promise<RecordedAudio> {
  const analysis =
    durationSeconds !== undefined && waveformPeaks !== undefined
      ? { durationSeconds, waveformPeaks }
      : await analyzeAudioBlob(blob);

  return {
    data: await blobToBase64(blob),
    format,
    blobUrl: URL.createObjectURL(blob),
    durationSeconds: analysis.durationSeconds,
    sizeBytes: blob.size,
    waveformPeaks: analysis.waveformPeaks,
  };
}

export async function createRecordedAudioFromBase64(
  data: string,
  format: SupportedAudioFormat
): Promise<RecordedAudio> {
  const { blob, data: normalizedData } = createAudioBlobFromBase64(data, format);
  const recording = await createRecordedAudioFromBlob(blob, format);
  return {
    ...recording,
    data: normalizedData,
  };
}

export function useAudioRecorder(options: AudioRecorderOptions) {
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef<number>(0);
  const intervalRef = useRef<number | null>(null);
  const warmupTimeoutRef = useRef<number | null>(null);
  const cancelledRef = useRef(false);

  const isSupported = useMemo(() => {
    return Boolean(
      window.isSecureContext &&
        typeof navigator.mediaDevices?.getUserMedia === "function" &&
        "MediaRecorder" in window &&
        getAudioContextConstructor()
    );
  }, []);

  const clearTimer = useCallback(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const clearWarmupTimer = useCallback(() => {
    if (warmupTimeoutRef.current !== null) {
      window.clearTimeout(warmupTimeoutRef.current);
      warmupTimeoutRef.current = null;
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (!isSupported) {
      setError("Microphone input requires a supported browser and a secure context (localhost or HTTPS).");
      return;
    }

    setError(null);
    setIsStarting(true);
    chunksRef.current = [];
    cancelledRef.current = false;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: options.echoCancellation,
          noiseSuppression: options.noiseSuppression,
          autoGainControl: options.autoGainControl,
          sampleRate: options.sampleRate,
        },
      });
      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstart = () => {
        warmupTimeoutRef.current = window.setTimeout(() => {
          if (cancelledRef.current) {
            return;
          }

          startedAtRef.current = Date.now();
          setRecordingSeconds(0);
          setIsRecording(true);
          setIsStarting(false);

          intervalRef.current = window.setInterval(() => {
            setRecordingSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
          }, 250);
        }, MICROPHONE_WARMUP_MS);
      };

      streamRef.current = stream;
      mediaRecorderRef.current = recorder;

      recorder.start();
    } catch (recordingError) {
      releaseStream();
      setIsRecording(false);
      setIsStarting(false);
      setError(recordingError instanceof Error ? recordingError.message : "Microphone permission was denied.");
    }
  }, [isSupported, options, releaseStream]);

  const stopRecording = useCallback(async (): Promise<RecordedAudio | null> => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive" || isStarting) {
      return null;
    }

    return new Promise((resolve, reject) => {
      recorder.onstop = async () => {
        clearTimer();
        clearWarmupTimer();
        setIsRecording(false);
        setIsProcessing(true);
        releaseStream();

        try {
          if (cancelledRef.current) {
            resolve(null);
            return;
          }

          const durationSeconds = (Date.now() - startedAtRef.current) / 1000;
          if (durationSeconds > options.maxDurationSeconds) {
            throw new Error(`Recording is longer than the ${options.maxDurationSeconds}s limit.`);
          }

          const sourceBlob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
          if (sourceBlob.size === 0) {
            throw new Error("No audio was captured.");
          }

          const { blob: wavBlob, waveformPeaks } = await normalizeToWav(sourceBlob, options.sampleRate);
          if (wavBlob.size > options.maxPayloadBytes) {
            throw new Error(
              `Recording is too large (${Math.ceil(wavBlob.size / 1024 / 1024)} MB). ` +
                `Limit is ${Math.ceil(options.maxPayloadBytes / 1024 / 1024)} MB.`
            );
          }

          resolve(await createRecordedAudioFromBlob(wavBlob, "wav", durationSeconds, waveformPeaks));
        } catch (processingError) {
          const message = processingError instanceof Error ? processingError.message : "Failed to process audio.";
          setError(message);
          reject(processingError);
        } finally {
          setIsProcessing(false);
          chunksRef.current = [];
          mediaRecorderRef.current = null;
        }
      };

      recorder.stop();
    });
  }, [
    clearTimer,
    clearWarmupTimer,
    isStarting,
    options.maxDurationSeconds,
    options.maxPayloadBytes,
    options.sampleRate,
    releaseStream,
  ]);

  const cancelRecording = useCallback(() => {
    cancelledRef.current = true;
    clearTimer();
    clearWarmupTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
    releaseStream();
    setIsRecording(false);
    setIsStarting(false);
    setRecordingSeconds(0);
    chunksRef.current = [];
  }, [clearTimer, clearWarmupTimer, releaseStream]);

  useEffect(() => {
    return () => {
      cancelRecording();
    };
  }, [cancelRecording]);

  return {
    isSupported,
    isRecording,
    isStarting,
    isProcessing,
    recordingSeconds,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
