/**
 * Utility functions for generating executor avatars
 */

export interface ExecutorAvatar {
  initials: string;
  color: string;
}

/**
 * Simple hash function that converts a string to a number
 * Used for deterministic color generation
 */
export function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash);
}

/**
 * Generate avatar properties (initials and color) from an executor ID
 * @param executorId - The executor ID to generate avatar from
 * @returns Object containing initials (first 2 uppercase letters) and color (HSL string)
 */
export function generateExecutorAvatar(executorId: string): ExecutorAvatar {
  // Extract first 2 characters as uppercase initials
  const initials = executorId.substring(0, 2).toUpperCase();

  // Generate deterministic color from ID hash
  const hash = simpleHash(executorId);
  const hue = hash % 360;
  const color = `hsl(${hue}, 70%, 60%)`;

  return { initials, color };
}
