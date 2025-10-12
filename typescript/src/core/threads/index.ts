/**
 * Thread Management
 *
 * This module provides types and utilities for managing conversation threads
 * in the Agent Framework, supporting both service-managed and local-managed threads.
 *
 * @module threads
 */

export {
  ThreadType,
  ServiceThreadOptions,
  ThreadConfigurationOptions,
  ThreadTypeOptions,
  validateThreadOptions,
  determineThreadType,
  isServiceManaged,
  isLocalManaged,
  isUndetermined,
} from './service-thread-types';
