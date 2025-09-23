/**
 * ContentRenderer - Renders individual content items based on type
 */

import { useState } from "react";
import { Download, FileText, AlertCircle, Code } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { RenderProps } from "./types";
import {
  isTextContent,
  isFunctionCallContent,
  isFunctionResultContent,
} from "@/types/agent-framework";

function TextContentRenderer({ content, isStreaming, className }: RenderProps) {
  if (!isTextContent(content)) return null;

  return (
    <div className={`whitespace-pre-wrap break-words ${className || ""}`}>
      {content.text}
      {isStreaming && (
        <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-current" />
      )}
    </div>
  );
}

function DataContentRenderer({ content, className }: RenderProps) {
  const [imageError, setImageError] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  if (content.type !== "data") return null;

  // Extract data URI and media type (updated for new field names)
  const dataUri = typeof content.uri === "string" ? content.uri : "";
  const mediaTypeMatch = dataUri.match(/^data:([^;]+)/);
  const mediaType = content.media_type || mediaTypeMatch?.[1] || "unknown";

  const isImage = mediaType.startsWith("image/");
  const isPdf = mediaType === "application/pdf";

  if (isImage && !imageError) {
    return (
      <div className={`my-2 ${className || ""}`}>
        <img
          src={dataUri}
          alt="Uploaded image"
          className={`rounded-lg border max-w-full transition-all cursor-pointer ${
            isExpanded ? "max-h-none" : "max-h-64"
          }`}
          onClick={() => setIsExpanded(!isExpanded)}
          onError={() => setImageError(true)}
        />
        <div className="text-xs text-muted-foreground mt-1">
          {mediaType} • Click to {isExpanded ? "collapse" : "expand"}
        </div>
      </div>
    );
  }

  // Fallback for non-images or failed images
  return (
    <div className={`my-2 p-3 border rounded-lg bg-muted ${className || ""}`}>
      <div className="flex items-center gap-2">
        {isPdf ? (
          <FileText className="h-4 w-4 text-red-500" />
        ) : (
          <Download className="h-4 w-4" />
        )}
        <span className="text-sm font-medium">
          {isPdf ? "PDF Document" : "File Attachment"}
        </span>
        <span className="text-xs text-muted-foreground">({mediaType})</span>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="mt-2"
        onClick={() => {
          const link = document.createElement("a");
          link.href = dataUri;
          link.download = `attachment.${mediaType.split("/")[1] || "bin"}`;
          link.click();
        }}
      >
        <Download className="h-3 w-3 mr-1" />
        Download
      </Button>
    </div>
  );
}

function FunctionCallRenderer({ content, className }: RenderProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!isFunctionCallContent(content)) return null;

  let parsedArgs;
  try {
    parsedArgs =
      typeof content.arguments === "string"
        ? JSON.parse(content.arguments)
        : content.arguments;
  } catch {
    parsedArgs = content.arguments;
  }

  return (
    <div className={`my-2 p-3 border rounded-lg bg-blue-50 ${className || ""}`}>
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <Code className="h-4 w-4 text-blue-600" />
        <span className="text-sm font-medium text-blue-800">
          Function Call: {content.name}
        </span>
        <span className="text-xs text-blue-600">
          {isExpanded ? "▼" : "▶"}
        </span>
      </div>
      {isExpanded && (
        <div className="mt-2 text-xs font-mono bg-white p-2 rounded border">
          <div className="text-blue-600 mb-1">Arguments:</div>
          <pre className="whitespace-pre-wrap">
            {JSON.stringify(parsedArgs, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function FunctionResultRenderer({ content, className }: RenderProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!isFunctionResultContent(content)) return null;

  return (
    <div className={`my-2 p-3 border rounded-lg bg-green-50 ${className || ""}`}>
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <Code className="h-4 w-4 text-green-600" />
        <span className="text-sm font-medium text-green-800">
          Function Result
        </span>
        <span className="text-xs text-green-600">
          {isExpanded ? "▼" : "▶"}
        </span>
      </div>
      {isExpanded && (
        <div className="mt-2 text-xs font-mono bg-white p-2 rounded border">
          <pre className="whitespace-pre-wrap">
            {typeof content.result === "string"
              ? content.result
              : JSON.stringify(content.result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function ErrorContentRenderer({ content, className }: RenderProps) {
  if (content.type !== "error") return null;

  return (
    <div className={`my-2 p-3 border rounded-lg bg-red-50 ${className || ""}`}>
      <div className="flex items-center gap-2">
        <AlertCircle className="h-4 w-4 text-red-500" />
        <span className="text-sm font-medium text-red-800">Error</span>
        {content.error_code && (
          <span className="text-xs text-red-600">({content.error_code})</span>
        )}
      </div>
      <div className="mt-1 text-sm text-red-700">{content.error}</div>
    </div>
  );
}

function UriContentRenderer({ content, className }: RenderProps) {
  const [imageError, setImageError] = useState(false);

  if (content.type !== "uri") return null;

  const isImage = content.media_type?.startsWith("image/");

  if (isImage && !imageError) {
    return (
      <div className={`my-2 ${className || ""}`}>
        <img
          src={content.uri}
          alt="Referenced image"
          className="rounded-lg border max-w-full max-h-64"
          onError={() => setImageError(true)}
        />
        <div className="text-xs text-muted-foreground mt-1">
          <a
            href={content.uri}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            {content.uri}
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className={`my-2 p-3 border rounded-lg bg-muted ${className || ""}`}>
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4" />
        <a
          href={content.uri}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-medium hover:underline"
        >
          {content.media_type || "External Link"}
        </a>
      </div>
      <div className="text-xs text-muted-foreground mt-1 break-all">
        {content.uri}
      </div>
    </div>
  );
}

export function ContentRenderer({ content, isStreaming, className }: RenderProps) {
  switch (content.type) {
    case "text":
      return (
        <TextContentRenderer
          content={content}
          isStreaming={isStreaming}
          className={className}
        />
      );
    case "data":
      return <DataContentRenderer content={content} className={className} />;
    case "uri":
      return <UriContentRenderer content={content} className={className} />;
    case "function_call":
      return (
        <FunctionCallRenderer content={content} className={className} />
      );
    case "function_result":
      return (
        <FunctionResultRenderer content={content} className={className} />
      );
    case "error":
      return <ErrorContentRenderer content={content} className={className} />;
    default:
      // Fallback for unsupported content types
      return (
        <div className={`my-2 p-2 bg-gray-100 rounded text-xs ${className || ""}`}>
          <div>Unsupported content type: {content.type}</div>
          <pre className="mt-1 text-xs whitespace-pre-wrap">
            {JSON.stringify(content, null, 2)}
          </pre>
        </div>
      );
  }
}