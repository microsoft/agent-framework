/**
 * AttachmentGallery - Shows uploaded files with thumbnails and remove options
 */

import { useState } from "react";
import { X, FileText, Image } from "lucide-react";
import { Button } from "./button";

export interface AttachmentItem {
  id: string;
  file: File;
  preview?: string; // Data URL for preview
  type: "image" | "pdf" | "other";
}

interface AttachmentGalleryProps {
  attachments: AttachmentItem[];
  onRemoveAttachment: (id: string) => void;
  className?: string;
}

export function AttachmentGallery({
  attachments,
  onRemoveAttachment,
  className = "",
}: AttachmentGalleryProps) {
  if (attachments.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-2 p-2 bg-muted rounded-lg ${className}`}>
      {attachments.map((attachment) => (
        <AttachmentPreview
          key={attachment.id}
          attachment={attachment}
          onRemove={() => onRemoveAttachment(attachment.id)}
        />
      ))}
    </div>
  );
}

interface AttachmentPreviewProps {
  attachment: AttachmentItem;
  onRemove: () => void;
}

function AttachmentPreview({ attachment, onRemove }: AttachmentPreviewProps) {
  const [isHovered, setIsHovered] = useState(false);

  const renderPreview = () => {
    switch (attachment.type) {
      case "image":
        return attachment.preview ? (
          <img
            src={attachment.preview}
            alt={attachment.file.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="flex items-center justify-center w-full h-full bg-gray-200">
            <Image className="h-6 w-6 text-gray-400" />
          </div>
        );

      case "pdf":
        return (
          <div className="flex flex-col items-center justify-center w-full h-full bg-red-50">
            <FileText className="h-6 w-6 text-red-500 mb-1" />
            <span className="text-xs text-red-600">PDF</span>
          </div>
        );

      default:
        return (
          <div className="flex flex-col items-center justify-center w-full h-full bg-gray-100">
            <FileText className="h-6 w-6 text-gray-500 mb-1" />
            <span className="text-xs text-gray-600">FILE</span>
          </div>
        );
    }
  };

  return (
    <div
      className="relative w-16 h-16 rounded border overflow-hidden group cursor-pointer"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={attachment.file.name}
    >
      {renderPreview()}

      {/* Remove button on hover */}
      {isHovered && (
        <Button
          variant="destructive"
          size="icon"
          className="absolute -top-1 -right-1 h-5 w-5 rounded-full"
          onClick={onRemove}
        >
          <X className="h-3 w-3" />
        </Button>
      )}

      {/* File name tooltip */}
      <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-75 text-white text-xs p-1 truncate opacity-0 group-hover:opacity-100 transition-opacity">
        {attachment.file.name}
      </div>
    </div>
  );
}