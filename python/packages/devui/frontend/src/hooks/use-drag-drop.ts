/**
 * useDragDrop - Hook for handling drag and drop file uploads at parent level
 * Provides drag state and handlers that can be spread on a container element
 */

import { useState, useCallback, useRef } from "react";

export interface UseDragDropOptions {
  /** Called when files are dropped */
  onDrop?: (files: File[]) => void;
  /** Whether drag/drop is disabled */
  disabled?: boolean;
}

export interface UseDragDropReturn {
  /** Whether a drag is currently over the drop zone */
  isDragOver: boolean;
  /** Files that were dropped (cleared after processing) */
  droppedFiles: File[];
  /** Clear the dropped files after they've been processed */
  clearDroppedFiles: () => void;
  /** Event handlers to spread on the container element */
  dragHandlers: {
    onDragEnter: (e: React.DragEvent) => void;
    onDragLeave: (e: React.DragEvent) => void;
    onDragOver: (e: React.DragEvent) => void;
    onDrop: (e: React.DragEvent) => void;
  };
}

export function useDragDrop(options: UseDragDropOptions = {}): UseDragDropReturn {
  const { onDrop, disabled = false } = options;

  const [isDragOver, setIsDragOver] = useState(false);
  const [droppedFiles, setDroppedFiles] = useState<File[]>([]);
  const dragCounterRef = useRef(0);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (disabled) return;

    dragCounterRef.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragOver(true);
    }
  }, [disabled]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (disabled) return;

    dragCounterRef.current--;
    if (dragCounterRef.current === 0) {
      setIsDragOver(false);
    }
  }, [disabled]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    setIsDragOver(false);
    dragCounterRef.current = 0;

    if (disabled) return;

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      setDroppedFiles(files);
      onDrop?.(files);
    }
  }, [disabled, onDrop]);

  const clearDroppedFiles = useCallback(() => {
    setDroppedFiles([]);
  }, []);

  return {
    isDragOver,
    droppedFiles,
    clearDroppedFiles,
    dragHandlers: {
      onDragEnter: handleDragEnter,
      onDragLeave: handleDragLeave,
      onDragOver: handleDragOver,
      onDrop: handleDrop,
    },
  };
}
