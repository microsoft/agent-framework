/**
 * OpenAI Content Renderer - Renders OpenAI Conversations API content types
 * This is the CORRECT implementation that works with OpenAI types only
 */

import { useState, useEffect } from "react";
import {
  Download,
  FileText,
  Code,
  ChevronDown,
  ChevronRight,
  Music,
  Check,
  X,
  Clock,
} from "lucide-react";
import type { MessageContent, MessageOutputFile } from "@/types/openai";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import { AudioMessagePreview } from "@/components/ui/audio-message-preview";
import {
  analyzeAudioBlob,
  createAudioBlobFromBase64,
  createRecordedAudioFromBase64,
  createRecordedAudioFromBlob,
  type AudioAnalysis,
  type RecordedAudio,
  type SupportedAudioFormat,
} from "@/hooks";
import { useDevUIStore } from "@/stores/devuiStore";

interface ContentRendererProps {
  content: MessageContent;
  className?: string;
  isStreaming?: boolean;
  autoPlayAudio?: boolean;
}

const AUDIO_PREVIEW_CACHE_LIMIT = 25;
const audioPreviewCache = new Map<string, Promise<AudioAnalysis & { blob: Blob }>>();

function getAudioPreviewCacheKey(data: string, format: "wav" | "mp3"): string {
  let hash = 0;
  for (let index = 0; index < data.length; index++) {
    hash = (hash * 31 + data.charCodeAt(index)) | 0;
  }
  return `${format}:${data.length}:${hash}`;
}

function getCachedAudioPreview(data: string, format: "wav" | "mp3"): Promise<AudioAnalysis & { blob: Blob }> {
  const cacheKey = getAudioPreviewCacheKey(data, format);
  const cachedPreview = audioPreviewCache.get(cacheKey);
  if (cachedPreview) {
    return cachedPreview;
  }

  const preview = (async () => {
    const { blob } = createAudioBlobFromBase64(data, format);
    return {
      blob,
      ...(await analyzeAudioBlob(blob)),
    };
  })().catch((error) => {
    audioPreviewCache.delete(cacheKey);
    throw error;
  });

  audioPreviewCache.set(cacheKey, preview);
  if (audioPreviewCache.size > AUDIO_PREVIEW_CACHE_LIMIT) {
    const oldestKey = audioPreviewCache.keys().next().value;
    if (oldestKey) {
      audioPreviewCache.delete(oldestKey);
    }
  }

  return preview;
}

// Text content renderer
function TextContentRenderer({ content, className, isStreaming }: ContentRendererProps) {
  if (
    content.type !== "text" &&
    content.type !== "input_text" &&
    content.type !== "output_text" &&
    content.type !== "refusal"
  ) return null;

  const text = content.type === "refusal" ? content.refusal : content.text;

  return (
    <div className={`break-words ${className || ""}`}>
      <MarkdownRenderer content={text} />
      {isStreaming && text.length > 0 && (
        <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-current" />
      )}
    </div>
  );
}

// Image content renderer (handles both input and output images)
function ImageContentRenderer({ content, className }: ContentRendererProps) {
  const [imageError, setImageError] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  if (content.type !== "input_image" && content.type !== "output_image") return null;

  const imageUrl = content.image_url;

  if (imageError) {
    return (
      <div className={`my-2 p-3 border rounded-lg bg-muted ${className || ""}`}>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileText className="h-4 w-4" />
          <span>Image could not be loaded</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`my-2 ${className || ""}`}>
      <img
        src={imageUrl}
        alt="Uploaded image"
        className={`rounded-lg border max-w-full transition-all cursor-pointer ${
          isExpanded ? "max-h-none" : "max-h-64"
        }`}
        onClick={() => setIsExpanded(!isExpanded)}
        onError={() => setImageError(true)}
      />
      {isExpanded && (
        <div className="text-xs text-muted-foreground mt-1">
          Click to collapse
        </div>
      )}
    </div>
  );
}

// Helper to convert base64 (or data URI) to blob URL for better browser compatibility
function useBase64ToBlobUrl(data: string | undefined, mimeType: string): string | null {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!data) {
      setBlobUrl(null);
      return;
    }

    try {
      // Handle both data URI format and raw base64
      let base64Data: string;
      if (data.startsWith('data:')) {
        // Extract base64 from data URI (e.g., "data:application/pdf;base64,...")
        const parts = data.split(',');
        if (parts.length !== 2) {
          setBlobUrl(null);
          return;
        }
        base64Data = parts[1];
      } else {
        // Raw base64 data
        base64Data = data;
      }

      const binaryString = atob(base64Data);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const blob = new Blob([bytes], { type: mimeType });
      const url = URL.createObjectURL(blob);
      setBlobUrl(url);

      // Cleanup on unmount or when data changes
      return () => {
        URL.revokeObjectURL(url);
      };
    } catch (error) {
      console.error('Failed to convert base64 to blob URL:', error);
      setBlobUrl(null);
    }
  }, [data, mimeType]);

  return blobUrl;
}

// File content renderer (handles both input and output files)
function FileContentRenderer({ content, className, autoPlayAudio }: ContentRendererProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  // Determine file properties (must be before hooks for conditional logic)
  const isFileContent = content.type === "input_file" || content.type === "output_file";
  const fileUrl = isFileContent ? (content.file_url || content.file_data) : undefined;
  const filename = isFileContent ? (content.filename || "file") : undefined;
  const mimeType = content.type === "output_file" ? content.mime_type : undefined;

  // Determine file type from filename or data URI
  const isPdf = filename?.toLowerCase().endsWith(".pdf") || fileUrl?.includes("application/pdf");
  const isAudioOutput = content.type === "output_file" && Boolean(
    filename?.toLowerCase().match(/\.(mp3|wav|m4a|ogg|flac|aac)$/) ||
      mimeType?.startsWith("audio/")
  );

  // Convert base64 to blob URL for PDFs (better browser compatibility)
  // Use file_data (raw base64) if available, otherwise try file_url
  // Hook must be called unconditionally - pass undefined if not a PDF
  const pdfData = (isFileContent && isPdf) ? (content.file_data || content.file_url) : undefined;
  const pdfBlobUrl = useBase64ToBlobUrl(pdfData, 'application/pdf');

  // Early return after all hooks
  if (!isFileContent) return null;

  // Use blob URL if available, otherwise fall back to original URL
  const effectivePdfUrl = pdfBlobUrl || fileUrl;

  // Helper to open PDF in new tab
  const openPdfInNewTab = () => {
    if (effectivePdfUrl) {
      window.open(effectivePdfUrl, '_blank');
    }
  };

  // For PDFs - show a clean card with actions (inline preview is unreliable across browsers)
  if (isPdf && fileUrl) {
    return (
      <div className={`my-2 ${className || ""}`}>
        {/* Header with filename and controls */}
        <div className="flex items-center gap-2 mb-2 px-1">
          <FileText className="h-4 w-4 text-red-500" />
          <span className="text-sm font-medium truncate flex-1">{filename}</span>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          >
            {isExpanded ? (
              <>
                <ChevronDown className="h-3 w-3" />
                Collapse
              </>
            ) : (
              <>
                <ChevronRight className="h-3 w-3" />
                Expand
              </>
            )}
          </button>
        </div>

        {/* PDF Card with actions */}
        {isExpanded && (
          <div className="border rounded-lg p-6 bg-muted/50 flex flex-col items-center justify-center gap-4">
            <FileText className="h-16 w-16 text-red-400" />
            <div className="text-center">
              <p className="text-sm font-medium mb-1">{filename}</p>
              <p className="text-xs text-muted-foreground">PDF Document</p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={openPdfInNewTab}
                className="text-sm bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 px-4 py-2 rounded-md transition-colors"
              >
                Open in new tab
              </button>
              <a
                href={effectivePdfUrl || fileUrl}
                download={filename}
                className="text-sm text-foreground hover:bg-accent flex items-center gap-2 px-4 py-2 border rounded-md transition-colors"
              >
                <Download className="h-4 w-4" />
                Download
              </a>
            </div>
          </div>
        )}
      </div>
    );
  }

  // For audio files
  if (isAudioOutput && fileUrl) {
    return (
      <OutputAudioFileRenderer
        content={content as MessageOutputFile}
        className={className}
        autoPlay={autoPlayAudio}
      />
    );
  }

  // Generic file display
  return (
    <div className={`my-2 p-3 border rounded-lg bg-muted ${className || ""}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm">{filename}</span>
        </div>
        {fileUrl && (
          <a
            href={fileUrl}
            download={filename}
            className="text-xs text-primary hover:underline flex items-center gap-1"
          >
            <Download className="h-3 w-3" />
            Download
          </a>
        )}
      </div>
    </div>
  );
}

function getOutputAudioFormat(content: MessageOutputFile): SupportedAudioFormat | null {
  const mimeType = content.mime_type?.split(";")[0].trim().toLowerCase();
  const filename = content.filename.toLowerCase();

  if (mimeType === "audio/wav" || mimeType === "audio/x-wav" || filename.endsWith(".wav")) {
    return "wav";
  }
  if (
    mimeType === "audio/mpeg" ||
    mimeType === "audio/mp3" ||
    mimeType === "audio/x-mpeg" ||
    filename.endsWith(".mp3")
  ) {
    return "mp3";
  }

  return null;
}

function audioSourceUrl(content: MessageOutputFile): string | undefined {
  if (content.file_url) {
    return content.file_url;
  }
  if (content.file_data) {
    const mimeType = content.mime_type || "audio/mpeg";
    return content.file_data.startsWith("data:")
      ? content.file_data
      : `data:${mimeType};base64,${content.file_data}`;
  }
  return undefined;
}

function OutputAudioFileRenderer({
  content,
  className,
  autoPlay,
}: {
  content: MessageOutputFile;
  className?: string;
  autoPlay?: boolean;
}) {
  const [audioPreview, setAudioPreview] = useState<RecordedAudio | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const autoPlayAgentAudio = useDevUIStore((state) => state.audioInput.autoPlayAgentAudio);
  const format = getOutputAudioFormat(content);
  const sourceUrl = audioSourceUrl(content);
  const label = `${content.filename || "Voice message"}${format ? ` (${format.toUpperCase()})` : ""}`;

  useEffect(() => {
    if (!format || !sourceUrl) {
      setAudioPreview(null);
      setPreviewError(true);
      return;
    }

    let isCancelled = false;
    let activePreview: RecordedAudio | null = null;

    setAudioPreview(null);
    setPreviewError(false);

    const preparePreview = async () => {
      if (content.file_data || sourceUrl.startsWith("data:")) {
        return createRecordedAudioFromBase64(sourceUrl, format);
      }

      const response = await fetch(sourceUrl);
      if (!response.ok) {
        throw new Error(`Failed to load audio output: ${response.status}`);
      }
      return createRecordedAudioFromBlob(await response.blob(), format);
    };

    preparePreview()
      .then((preview) => {
        if (isCancelled) {
          URL.revokeObjectURL(preview.blobUrl);
          return;
        }
        activePreview = preview;
        setAudioPreview(preview);
      })
      .catch((error) => {
        console.error("Failed to prepare output audio preview:", error);
        if (!isCancelled) {
          setPreviewError(true);
        }
      });

    return () => {
      isCancelled = true;
      if (activePreview) {
        URL.revokeObjectURL(activePreview.blobUrl);
      }
    };
  }, [content.file_data, format, sourceUrl]);

  if (audioPreview && !previewError) {
    return (
      <AudioMessagePreview
        audio={audioPreview}
        label={label}
        previewBeforeSend
        autoPlay={Boolean(autoPlay && autoPlayAgentAudio)}
        downloadFilename={content.filename}
        maxWidth={460}
        minWidth={320}
        className={`my-2 bg-card text-card-foreground ${className || ""}`}
      />
    );
  }

  return (
    <div className={`my-2 p-3 border rounded-lg ${className || ""}`}>
      <div className="flex items-center gap-2 mb-2">
        <Music className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">{label}</span>
      </div>
      {sourceUrl && (
        <audio controls className="w-full">
          <source src={sourceUrl} type={content.mime_type} />
          Your browser does not support audio playback.
        </audio>
      )}
    </div>
  );
}

function AudioContentRenderer({ content, className }: ContentRendererProps) {
  const [audioPreview, setAudioPreview] = useState<RecordedAudio | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const isAudioContent = content.type === "input_audio";
  const data = isAudioContent ? content.input_audio.data : "";
  const format = isAudioContent ? content.input_audio.format : "wav";
  const mimeType = format === "mp3" ? "audio/mpeg" : "audio/wav";
  const audioUrl = data.startsWith("data:") ? data : `data:${mimeType};base64,${data}`;
  const label = `Voice message (${format.toUpperCase()})`;

  useEffect(() => {
    if (!isAudioContent) {
      return;
    }

    let isCancelled = false;
    let blobUrl: string | null = null;

    setAudioPreview(null);
    setPreviewError(false);
    getCachedAudioPreview(data, format)
      .then((preview) => {
        if (isCancelled) {
          return;
        }
        blobUrl = URL.createObjectURL(preview.blob);
        setAudioPreview({
          data: data.startsWith("data:") ? data.split(",", 2)[1] ?? "" : data,
          format,
          blobUrl,
          durationSeconds: preview.durationSeconds,
          sizeBytes: preview.blob.size,
          waveformPeaks: preview.waveformPeaks,
        });
      })
      .catch((error) => {
        console.error("Failed to prepare audio preview:", error);
        if (!isCancelled) {
          setPreviewError(true);
        }
      });

    return () => {
      isCancelled = true;
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [data, format, isAudioContent]);

  if (!isAudioContent) return null;

  if (audioPreview && !previewError) {
    return (
      <AudioMessagePreview
        audio={audioPreview}
        label={label}
        previewBeforeSend
        className={`my-2 bg-card text-card-foreground ${className || ""}`}
      />
    );
  }

  return (
    <div className={`my-2 p-3 border rounded-lg ${className || ""}`}>
      <div className="flex items-center gap-2 mb-2">
        <Music className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <audio controls className="w-full">
        <source src={audioUrl} type={mimeType} />
        Your browser does not support audio playback.
      </audio>
    </div>
  );
}

// Data content renderer (for generic structured data outputs)
function DataContentRenderer({ content, className }: ContentRendererProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (content.type !== "output_data") return null;

  const data = content.data;
  const mimeType = content.mime_type;
  const description = content.description;

  // Try to parse as JSON for pretty printing
  let displayData = data;
  try {
    const parsed = JSON.parse(data);
    displayData = JSON.stringify(parsed, null, 2);
  } catch {
    // Not JSON, display as-is
  }

  return (
    <div className={`my-2 p-3 border rounded-lg bg-muted ${className || ""}`}>
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <FileText className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">
          {description || "Data Output"}
        </span>
        <span className="text-xs text-muted-foreground ml-auto">{mimeType}</span>
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </div>
      {isExpanded && (
        <pre className="mt-2 text-xs overflow-auto max-h-64 bg-background p-2 rounded border font-mono">
          {displayData}
        </pre>
      )}
    </div>
  );
}

// Function approval request renderer - compact version
function FunctionApprovalRequestRenderer({ content, className }: ContentRendererProps) {
  // Hooks must be called unconditionally
  const [isExpanded, setIsExpanded] = useState(false);

  // Early return after hooks
  if (content.type !== "function_approval_request") return null;

  const { status, function_call } = content;

  // Status styling - compact
  const statusConfig = {
    pending: {
      icon: Clock,
      label: "Awaiting approval",
      iconClass: "text-amber-600 dark:text-amber-400",
    },
    approved: {
      icon: Check,
      label: "Approved",
      iconClass: "text-green-600 dark:text-green-400",
    },
    rejected: {
      icon: X,
      label: "Rejected",
      iconClass: "text-red-600 dark:text-red-400",
    },
  };

  const config = statusConfig[status];
  const StatusIcon = config.icon;

  let parsedArgs;
  try {
    parsedArgs = typeof function_call.arguments === "string"
      ? JSON.parse(function_call.arguments)
      : function_call.arguments;
  } catch {
    parsedArgs = function_call.arguments;
  }

  return (
    <div className={className}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 px-2 py-1 text-xs rounded hover:bg-muted/50 transition-colors w-fit"
      >
        <StatusIcon className={`h-3 w-3 ${config.iconClass}`} />
        <span className="text-muted-foreground font-mono">{function_call.name}</span>
        <span className={`text-xs ${config.iconClass}`}>{config.label}</span>
        {isExpanded ? (
          <span className="text-xs text-muted-foreground">▼</span>
        ) : (
          <span className="text-xs text-muted-foreground">▶</span>
        )}
      </button>

      {isExpanded && (
        <div className="ml-5 mt-1 text-xs font-mono text-muted-foreground border-l-2 border-muted pl-3">
          <pre className="whitespace-pre-wrap break-all">{JSON.stringify(parsedArgs, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

// Main content renderer that delegates to specific renderers
export function OpenAIContentRenderer({ content, className, isStreaming, autoPlayAudio }: ContentRendererProps) {
  switch (content.type) {
    case "text":
    case "input_text":
    case "output_text":
    case "refusal":
      return <TextContentRenderer content={content} className={className} isStreaming={isStreaming} />;
    case "input_image":
    case "output_image":
      return <ImageContentRenderer content={content} className={className} />;
    case "input_file":
    case "output_file":
      return <FileContentRenderer content={content} className={className} autoPlayAudio={autoPlayAudio} />;
    case "input_audio":
      return <AudioContentRenderer content={content} className={className} />;
    case "output_data":
      return <DataContentRenderer content={content} className={className} />;
    case "function_approval_request":
      return <FunctionApprovalRequestRenderer content={content} className={className} />;
    default:
      return null;
  }
}

// Function call renderer (for displaying function calls in chat)
interface FunctionCallRendererProps {
  name: string;
  arguments: string;
  className?: string;
}

export function FunctionCallRenderer({ name, arguments: args, className }: FunctionCallRendererProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  let parsedArgs;
  try {
    parsedArgs = typeof args === "string" ? JSON.parse(args) : args;
  } catch {
    parsedArgs = args;
  }

  return (
    <div className={`my-2 p-3 border rounded bg-blue-50 dark:bg-blue-950/20 ${className || ""}`}>
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <Code className="h-4 w-4 text-blue-600 dark:text-blue-400" />
        <span className="text-sm font-medium text-blue-800 dark:text-blue-300">
          Function Call: {name}
        </span>
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-blue-600 dark:text-blue-400 ml-auto" />
        ) : (
          <ChevronRight className="h-4 w-4 text-blue-600 dark:text-blue-400 ml-auto" />
        )}
      </div>
      {isExpanded && (
        <div className="mt-2 text-xs font-mono bg-white dark:bg-gray-900 p-2 rounded border">
          <div className="text-blue-600 dark:text-blue-400 mb-1">Arguments:</div>
          <pre className="whitespace-pre-wrap">
            {JSON.stringify(parsedArgs, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// Function result renderer
interface FunctionResultRendererProps {
  output: string;
  call_id: string;
  className?: string;
}

export function FunctionResultRenderer({ output, call_id, className }: FunctionResultRendererProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  let parsedOutput;
  try {
    parsedOutput = typeof output === "string" ? JSON.parse(output) : output;
  } catch {
    parsedOutput = output;
  }

  return (
    <div className={`my-2 p-3 border rounded bg-green-50 dark:bg-green-950/20 ${className || ""}`}>
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <Code className="h-4 w-4 text-green-600 dark:text-green-400" />
        <span className="text-sm font-medium text-green-800 dark:text-green-300">
          Function Result
        </span>
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-green-600 dark:text-green-400 ml-auto" />
        ) : (
          <ChevronRight className="h-4 w-4 text-green-600 dark:text-green-400 ml-auto" />
        )}
      </div>
      {isExpanded && (
        <div className="mt-2 text-xs font-mono bg-white dark:bg-gray-900 p-2 rounded border">
          <div className="text-green-600 dark:text-green-400 mb-1">Output:</div>
          <pre className="whitespace-pre-wrap">
            {JSON.stringify(parsedOutput, null, 2)}
          </pre>
          <div className="text-gray-500 text-[10px] mt-2">Call ID: {call_id}</div>
        </div>
      )}
    </div>
  );
}
