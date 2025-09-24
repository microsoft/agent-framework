/**
 * FileUpload - Upload button with drag & drop support
 */

import { useRef } from "react";
import { Upload } from "lucide-react";
import { Button } from "./button";

interface FileUploadProps {
  onFilesSelected: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  maxSize?: number; // in bytes
  disabled?: boolean;
  className?: string;
}

export function FileUpload({
  onFilesSelected,
  accept = "image/*,.pdf",
  multiple = true,
  maxSize = 50 * 1024 * 1024, // 50MB default for local dev tool
  disabled = false,
  className = "",
}: FileUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const validFiles: File[] = [];
    const errors: string[] = [];

    Array.from(files).forEach((file) => {
      // Size validation
      if (file.size > maxSize) {
        errors.push(`${file.name} is too large (max ${formatFileSize(maxSize)})`);
        return;
      }

      // Type validation (basic)
      if (accept && !isFileAccepted(file, accept)) {
        errors.push(`${file.name} is not an accepted file type`);
        return;
      }

      validFiles.push(file);
    });

    if (errors.length > 0) {
      console.warn("File upload errors:", errors);
      // In a production app, you might want to show these errors to the user
    }

    if (validFiles.length > 0) {
      onFilesSelected(validFiles);
    }
  };

  const handleButtonClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFileSelect(e.target.files);
    // Reset input to allow selecting the same file again
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (disabled) return;

    const files = e.dataTransfer.files;
    handleFileSelect(files);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  return (
    <div className={className}>
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={handleFileInputChange}
        className="hidden"
        disabled={disabled}
      />

      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={handleButtonClick}
        disabled={disabled}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        className="shrink-0 transition-colors hover:bg-muted"
        title="Upload files (images, PDFs)"
      >
        <Upload className="h-4 w-4" />
      </Button>
    </div>
  );
}

// Helper functions
function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function isFileAccepted(file: File, accept: string): boolean {
  const acceptPatterns = accept.split(",").map((pattern) => pattern.trim());

  return acceptPatterns.some((pattern) => {
    if (pattern.startsWith(".")) {
      // File extension check
      return file.name.toLowerCase().endsWith(pattern.toLowerCase());
    } else if (pattern.includes("/*")) {
      // MIME type wildcard check (e.g., "image/*")
      const [mainType] = pattern.split("/");
      return file.type.startsWith(mainType + "/");
    } else {
      // Exact MIME type check
      return file.type === pattern;
    }
  });
}