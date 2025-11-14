/**
 * OpenAI Content Renderer - Renders OpenAI Conversations API content types
 * This is the CORRECT implementation that works with OpenAI types only
 */

import { useState } from "react";
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
import type { MessageContent } from "@/types/openai";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";

interface ContentRendererProps {
  content: MessageContent;
  className?: string;
  isStreaming?: boolean;
}

// Text content renderer
function TextContentRenderer({ content, className, isStreaming }: ContentRendererProps) {
  if (content.type !== "text" && content.type !== "input_text" && content.type !== "output_text") return null;

  const text = content.text;

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

// File content renderer (handles both input and output files)
function FileContentRenderer({ content, className }: ContentRendererProps) {
  if (content.type !== "input_file" && content.type !== "output_file") return null;

  const fileUrl = content.file_url || content.file_data;
  const filename = content.filename || "file";

  // Determine file type from filename or data URI
  const isPdf = filename?.toLowerCase().endsWith(".pdf") || fileUrl?.includes("application/pdf");
  const isAudio = filename?.toLowerCase().match(/\.(mp3|wav|m4a|ogg|flac|aac)$/);

  // For PDFs, try to embed
  if (isPdf && fileUrl) {
    return (
      <div className={`my-2 ${className || ""}`}>
        <div className="border rounded-lg overflow-hidden">
          <iframe
            src={fileUrl}
            className="w-full h-96"
            title={filename}
          />
        </div>
        <div className="flex items-center gap-2 mt-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">{filename}</span>
          {fileUrl && (
            <a
              href={fileUrl}
              download={filename}
              className="ml-auto text-xs text-primary hover:underline flex items-center gap-1"
            >
              <Download className="h-3 w-3" />
              Download
            </a>
          )}
        </div>
      </div>
    );
  }

  // For audio files
  if (isAudio && fileUrl) {
    return (
      <div className={`my-2 p-3 border rounded-lg ${className || ""}`}>
        <div className="flex items-center gap-2 mb-2">
          <Music className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">{filename}</span>
        </div>
        <audio controls className="w-full">
          <source src={fileUrl} />
          Your browser does not support audio playback.
        </audio>
      </div>
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

// Function approval request renderer
function FunctionApprovalRequestRenderer({ content, className }: ContentRendererProps) {
  if (content.type !== "function_approval_request") return null;

  const [isExpanded, setIsExpanded] = useState(false);
  const { status, function_call } = content;

  // Status styling
  const statusConfig = {
    pending: {
      icon: Clock,
      color: "amber",
      label: "Awaiting Approval",
      bgClass: "bg-amber-50 dark:bg-amber-950/20",
      borderClass: "border-amber-200 dark:border-amber-800",
      iconClass: "text-amber-600 dark:text-amber-400",
      textClass: "text-amber-800 dark:text-amber-300",
    },
    approved: {
      icon: Check,
      color: "green",
      label: "Approved",
      bgClass: "bg-green-50 dark:bg-green-950/20",
      borderClass: "border-green-200 dark:border-green-800",
      iconClass: "text-green-600 dark:text-green-400",
      textClass: "text-green-800 dark:text-green-300",
    },
    rejected: {
      icon: X,
      color: "red",
      label: "Rejected",
      bgClass: "bg-red-50 dark:bg-red-950/20",
      borderClass: "border-red-200 dark:border-red-800",
      iconClass: "text-red-600 dark:text-red-400",
      textClass: "text-red-800 dark:text-red-300",
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
    <div className={`my-2 p-3 border rounded ${config.bgClass} ${config.borderClass} ${className || ""}`}>
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <StatusIcon className={`h-4 w-4 ${config.iconClass}`} />
        <span className={`text-sm font-medium ${config.textClass}`}>
          {config.label}: {function_call.name}
        </span>
        {isExpanded ? (
          <ChevronDown className={`h-4 w-4 ${config.iconClass} ml-auto`} />
        ) : (
          <ChevronRight className={`h-4 w-4 ${config.iconClass} ml-auto`} />
        )}
      </div>
      {isExpanded && (
        <div className="mt-2 text-xs font-mono bg-white dark:bg-gray-900 p-2 rounded border">
          <div className={`${config.textClass} mb-1`}>Arguments:</div>
          <pre className="whitespace-pre-wrap">
            {JSON.stringify(parsedArgs, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// Main content renderer that delegates to specific renderers
export function OpenAIContentRenderer({ content, className, isStreaming }: ContentRendererProps) {
  switch (content.type) {
    case "text":
    case "input_text":
    case "output_text":
      return <TextContentRenderer content={content} className={className} isStreaming={isStreaming} />;
    case "input_image":
    case "output_image":
      return <ImageContentRenderer content={content} className={className} />;
    case "input_file":
    case "output_file":
      return <FileContentRenderer content={content} className={className} />;
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
