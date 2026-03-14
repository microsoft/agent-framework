/**
 * Custom hook for managing cancellable requests with AbortController
 * Reduces duplication across agent and workflow views
 */

import { useState, useRef, useCallback } from "react";

/**
 * Hook for managing cancellable requests with AbortController
 * @returns Object with cancellation state and methods
 */
export function useCancellableRequest() {
  const [isCancelling, setIsCancelling] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * Creates a new AbortController and returns its signal
   * Resets the cancelling state
   */
  const createAbortSignal = useCallback((): AbortSignal => {
    abortControllerRef.current = new AbortController();
    setIsCancelling(false);
    return abortControllerRef.current.signal;
  }, []);

  /**
   * Cancels the current request if one exists
   */
  const handleCancel = useCallback(() => {
    if (abortControllerRef.current) {
      setIsCancelling(true);
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  /**
   * Resets the cancelling state - useful in error handlers
   */
  const resetCancelling = useCallback(() => {
    setIsCancelling(false);
  }, []);

  /**
   * Cleanup function to be called when component unmounts
   */
  const cleanup = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  return {
    isCancelling,
    createAbortSignal,
    handleCancel,
    resetCancelling,
    cleanup,
  };
}

/**
 * Utility function to check if an error is an AbortError
 * @param error - The error to check
 * @returns true if the error is an AbortError
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}