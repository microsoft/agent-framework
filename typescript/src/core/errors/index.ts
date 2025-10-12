/**
 * Error classes for the Agent Framework.
 *
 * This module exports all error types used throughout the framework.
 * All errors extend from AgentFrameworkError which provides:
 * - Cause chaining for wrapping underlying errors
 * - Optional error codes for programmatic handling
 * - Proper stack trace capture
 *
 * @module errors
 */

export { AgentFrameworkError } from './base-error';
export { AgentExecutionError, AgentInitializationError, AgentThreadError } from './agent-errors';
export { ToolExecutionError } from './tool-errors';
export { ChatClientError } from './chat-client-error';
export { WorkflowValidationError, GraphConnectivityError, TypeCompatibilityError } from './workflow-errors';
