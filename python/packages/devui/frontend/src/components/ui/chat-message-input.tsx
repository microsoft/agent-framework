/**
 * ChatMessageInput - Reusable chat input component with file upload and rich text support
 * Features: Text input, file upload, drag & drop, paste handling, attachments
 */

import { useState, useRef, useCallback, useEffect } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { FileUpload } from "@/components/ui/file-upload";
import {
  AttachmentGallery,
  type AttachmentItem,
} from "@/components/ui/attachment-gallery";
import {
  SendHorizontal,
  Square,
  FileText,
  Paperclip,
} from "lucide-react";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import type { ResponseInputContent, ResponseInputTextParam, ResponseInputImageParam, ResponseInputFileParam } from "@/types/agent-framework";

export interface ChatMessageInputProps {
  onSubmit: (content: ResponseInputContent[]) => Promise<void>;
  isSubmitting?: boolean;
  isStreaming?: boolean;
  onCancel?: () => void;
  isCancelling?: boolean;
  placeholder?: string;
  showFileUpload?: boolean;
  maxAttachments?: number;
  className?: string;
  disabled?: boolean;
  entityName?: string; // For placeholder text
  /** Files dropped from parent (via useDragDrop hook) */
  externalFiles?: File[];
  /** Called after external files have been processed */
  onExternalFilesProcessed?: () => void;
}

export function ChatMessageInput({
  onSubmit,
  isSubmitting = false,
  isStreaming = false,
  onCancel,
  isCancelling = false,
  placeholder,
  showFileUpload = true,
  maxAttachments = 10,
  className = "",
  disabled = false,
  entityName = "assistant",
  externalFiles,
  onExternalFilesProcessed,
}: ChatMessageInputProps) {
  const [inputValue, setInputValue] = useState("");
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [pasteNotification, setPasteNotification] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Process external files from parent (via useDragDrop hook)
  useEffect(() => {
    if (externalFiles && externalFiles.length > 0) {
      handleFilesSelected(externalFiles);
      onExternalFilesProcessed?.();
    }
  }, [externalFiles, onExternalFilesProcessed]);

  // Constants for text-to-file conversion
  const TEXT_THRESHOLD = 10000; // 10KB threshold for converting to file

  // Helper functions
  const getFileType = (file: File): AttachmentItem["type"] => {
    if (file.type.startsWith("image/")) return "image";
    if (file.type === "application/pdf") return "pdf";
    if (file.type.startsWith("audio/")) return "audio";
    return "other";
  };

  const readFileAsDataURL = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  // Detect file extension from content
  const detectFileExtension = (text: string): string => {
    const trimmed = text.trim();
    const lines = trimmed.split("\n");

    // JSON detection
    if (/^{[\s\S]*}$|^\[[\s\S]*\]$/.test(trimmed)) return ".json";

    // XML/HTML detection
    if (/^<\?xml|^<html|^<!DOCTYPE/i.test(trimmed)) return ".html";

    // Markdown detection (code blocks)
    if (/^```/.test(trimmed)) return ".md";

    // TSV detection (tabs with multiple lines)
    if (/\t/.test(text) && lines.length > 1) return ".tsv";

    // CSV detection (more strict) - need multiple lines with consistent comma patterns
    if (lines.length > 2) {
      const commaLines = lines.filter((line) => line.includes(","));
      const semicolonLines = lines.filter((line) => line.includes(";"));

      // If >50% of lines have commas and it looks tabular
      if (commaLines.length > lines.length * 0.5) {
        const avgCommas =
          commaLines.reduce(
            (sum, line) => sum + (line.match(/,/g) || []).length,
            0
          ) / commaLines.length;
        if (avgCommas >= 2) return ".csv";
      }

      // If >50% of lines have semicolons and it looks tabular
      if (semicolonLines.length > lines.length * 0.5) {
        const avgSemicolons =
          semicolonLines.reduce(
            (sum, line) => sum + (line.match(/;/g) || []).length,
            0
          ) / semicolonLines.length;
        if (avgSemicolons >= 2) return ".csv";
      }
    }

    return ".txt";
  };

  // Handle file selection
  const handleFilesSelected = useCallback(
    async (files: File[]) => {
      if (attachments.length + files.length > maxAttachments) {
        console.warn(`Cannot add more than ${maxAttachments} attachments`);
        return;
      }

      const newAttachments: AttachmentItem[] = [];

      for (const file of files) {
        const attachment: AttachmentItem = {
          id: `${Date.now()}-${Math.random()}`,
          file,
          type: getFileType(file),
        };

        // Generate preview for images
        if (file.type.startsWith("image/")) {
          try {
            attachment.preview = await readFileAsDataURL(file);
          } catch (error) {
            console.error("Failed to generate preview:", error);
          }
        }

        newAttachments.push(attachment);
      }

      setAttachments((prev) => [...prev, ...newAttachments]);
    },
    [attachments.length, maxAttachments]
  );

  // Handle attachment removal
  const handleRemoveAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  // Handle drag and drop
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      await handleFilesSelected(files);
    }
  };

  // Handle paste events
  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    const files: File[] = [];
    let hasProcessedText = false;

    for (const item of items) {
      // Handle images (including screenshots)
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (blob) {
          const timestamp = Date.now();
          files.push(
            new File([blob], `screenshot-${timestamp}.png`, { type: blob.type })
          );
        }
      }
      // Handle text - only process first text item (browsers often duplicate)
      else if (item.type === "text/plain" && !hasProcessedText) {
        hasProcessedText = true;

        // We need to check the text synchronously to decide whether to prevent default
        // Unfortunately, getAsString is async, so we'll prevent default for all text
        // and then decide whether to actually create a file or manually insert the text
        e.preventDefault();

        await new Promise<void>((resolve) => {
          item.getAsString((text) => {
            // Check if text should be converted to file
            const lineCount = (text.match(/\n/g) || []).length;
            const shouldConvert =
              text.length > TEXT_THRESHOLD ||
              lineCount > 50 || // Many lines suggests logs/data
              /^\s*[{[][\s\S]*[}\]]\s*$/.test(text) || // JSON-like
              /^<\?xml|^<html|^<!DOCTYPE/i.test(text); // XML/HTML

            if (shouldConvert) {
              // Create file for large/complex text
              const extension = detectFileExtension(text);
              const timestamp = Date.now();
              const blob = new Blob([text], { type: "text/plain" });
              files.push(
                new File([blob], `pasted-text-${timestamp}${extension}`, {
                  type: "text/plain",
                })
              );
            } else {
              // For small text, manually insert into textarea since we prevented default
              const textarea = textareaRef.current;
              if (textarea) {
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                const currentValue = textarea.value;
                const newValue =
                  currentValue.slice(0, start) + text + currentValue.slice(end);
                setInputValue(newValue);

                // Restore cursor position after the inserted text
                setTimeout(() => {
                  textarea.selectionStart = textarea.selectionEnd =
                    start + text.length;
                  textarea.focus();
                }, 0);
              }
            }
            resolve();
          });
        });
      }
    }

    // Process collected files
    if (files.length > 0) {
      await handleFilesSelected(files);

      // Show notification with appropriate icon
      const message =
        files.length === 1
          ? files[0].name.includes("screenshot")
            ? "Screenshot added as attachment"
            : "Large text converted to file"
          : `${files.length} files added`;

      setPasteNotification(message);
      setTimeout(() => setPasteNotification(null), 3000);
    }
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (
      (!inputValue.trim() && attachments.length === 0) ||
      isSubmitting ||
      disabled
    )
      return;

    const messageText = inputValue.trim();
    const content: ResponseInputContent[] = [];

    // Add text content if present
    if (messageText) {
      content.push({
        text: messageText,
        type: "input_text",
      } as ResponseInputTextParam);
    }

    // Add attachments
    for (const attachment of attachments) {
      const dataUri = await readFileAsDataURL(attachment.file);

      if (attachment.file.type.startsWith("image/")) {
        // Image attachment
        content.push({
          detail: "auto",
          type: "input_image",
          image_url: dataUri,
        } as ResponseInputImageParam);
      } else if (
        attachment.file.type === "text/plain" &&
        (attachment.file.name.includes("pasted-text-") ||
          attachment.file.name.endsWith(".txt") ||
          attachment.file.name.endsWith(".csv") ||
          attachment.file.name.endsWith(".json") ||
          attachment.file.name.endsWith(".html") ||
          attachment.file.name.endsWith(".md") ||
          attachment.file.name.endsWith(".tsv"))
      ) {
        // Convert text files back to input_text
        const text = await attachment.file.text();
        content.push({
          text: text,
          type: "input_text",
        } as ResponseInputTextParam);
      } else {
        // Other file types
        const base64Data = dataUri.split(",")[1]; // Extract base64 part
        content.push({
          type: "input_file",
          file_data: base64Data,
          file_url: dataUri,
          filename: attachment.file.name,
        } as ResponseInputFileParam);
      }
    }

    // Call the onSubmit callback
    await onSubmit(content);

    // Clear input and attachments after successful submission
    setInputValue("");
    setAttachments([]);
  };

  const canSendMessage =
    !disabled &&
    !isSubmitting &&
    !isStreaming &&
    (inputValue.trim() || attachments.length > 0);

  return (
    <div
      className={`relative ${className}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragOver && (
        <div className="absolute inset-2 border-2 border-dashed border-blue-400 dark:border-blue-500 rounded-lg bg-blue-50/80 dark:bg-blue-950/40 backdrop-blur-sm flex items-center justify-center transition-all duration-200 ease-in-out z-10">
          <div className="text-center">
            <div className="text-blue-600 dark:text-blue-400 text-sm font-medium mb-1">
              Drop files here
            </div>
            <div className="text-blue-500 dark:text-blue-500 text-xs">
              Images, PDFs, and other files
            </div>
          </div>
        </div>
      )}

      {/* Attachment gallery */}
      {attachments.length > 0 && (
        <div className="mb-3">
          <AttachmentGallery
            attachments={attachments}
            onRemoveAttachment={handleRemoveAttachment}
          />
        </div>
      )}

      {/* Paste notification */}
      {pasteNotification && (
        <div
          className="absolute bottom-24 left-1/2 -translate-x-1/2 z-20
                      bg-blue-500 text-white px-4 py-2 rounded-full text-sm
                      animate-in slide-in-from-bottom-2 fade-in duration-200
                      flex items-center gap-2 shadow-lg"
        >
          {pasteNotification.includes("screenshot") ? (
            <Paperclip className="h-3 w-3" />
          ) : (
            <FileText className="h-3 w-3" />
          )}
          {pasteNotification}
        </div>
      )}

      {/* Input form */}
      <form onSubmit={handleSubmit} className="flex gap-2 items-end">
        <Textarea
          ref={textareaRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onPaste={handlePaste}
          onKeyDown={(e) => {
            // Submit on Enter (without shift)
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder={placeholder || `Message ${entityName}... (Shift+Enter for new line)`}
          disabled={disabled || isSubmitting || isStreaming}
          className="flex-1 min-h-[40px] max-h-[200px] resize-none"
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
        {showFileUpload && (
          <FileUpload
            onFilesSelected={handleFilesSelected}
            disabled={disabled || isSubmitting || isStreaming}
          />
        )}
        {isStreaming && onCancel ? (
          <Button
            type="button"
            size="icon"
            onClick={onCancel}
            disabled={isCancelling}
            className="shrink-0 h-10 transition-all"
            title="Stop generating"
            aria-label="Stop generating response"
          >
            {isCancelling ? (
              <LoadingSpinner size="sm" />
            ) : (
              <Square className="h-4 w-4 fill-current" />
            )}
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            disabled={!canSendMessage}
            className="shrink-0 h-10 transition-all"
            title="Send message"
            aria-label="Send message"
          >
            {isSubmitting ? (
              <LoadingSpinner size="sm" />
            ) : (
              <SendHorizontal className="h-4 w-4" />
            )}
          </Button>
        )}
      </form>
    </div>
  );
}