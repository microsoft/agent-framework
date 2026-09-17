// Copyright (c) Microsoft. All rights reserved.

/**
 * Check whether a comment contains only the DevFlow review command.
 *
 * @param {unknown} body - Issue comment body from the GitHub event payload.
 * @returns {boolean} Whether the normalized comment is exactly `/review`.
 */
function isReviewCommand(body) {
  return typeof body === 'string' && body.trim() === '/review';
}

module.exports = isReviewCommand;
