/**
 * Message storage interfaces and implementations.
 *
 * This module provides interfaces and implementations for storing and
 * retrieving chat messages in conversations.
 *
 * Multi-thread storage: Use for managing messages across multiple threads
 * - MultiThreadMessageStore (from './message-store')
 * - InMemoryMultiThreadStore (from './in-memory-store')
 *
 * Per-thread storage: Use for local-managed threads (one store per thread)
 * - ChatMessageStore (from './thread-message-store')
 * - InMemoryMessageStore (from './thread-message-store')
 *
 * @module storage
 */

// Multi-thread message storage (Phase 1 - TASK-010)
export {
  ChatMessageStore as MultiThreadMessageStore,
  ListOptions,
} from './message-store';
export { InMemoryMessageStore as InMemoryMultiThreadStore } from './in-memory-store';

// Per-thread message storage (Phase 2 - TASK-105a)
export {
  ChatMessageStore,
  InMemoryMessageStore,
  LocalThreadOptions,
  createDefaultMessageStore,
} from './thread-message-store';
