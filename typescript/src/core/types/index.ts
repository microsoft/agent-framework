/**
 * Core type definitions for the Microsoft Agent Framework.
 *
 * This module exports all core types, interfaces, and utilities for working
 * with agents and AI model settings.
 */

export {
  AgentInfo,
  AISettings,
  ResponseFormat,
  StreamOptions,
  DEFAULT_AI_SETTINGS,
  validateTemperature,
  validateTopP,
  validateMaxTokens,
  validatePenalty,
  validateAISettings,
  AISettingsBuilder,
} from './agent-info';

export {
  MessageRole,
  type TextContent,
  type FunctionCallContent,
  type FunctionResultContent,
  type FunctionApprovalRequestContent,
  type FunctionApprovalResponseContent,
  type ImageContent,
  type AudioContent,
  type FileContent,
  type VectorStoreContent,
  type Content,
  type ChatMessage,
  createUserMessage,
  createAssistantMessage,
  createSystemMessage,
  createToolMessage,
  isTextContent,
  isFunctionCallContent,
  isFunctionResultContent,
  isFunctionApprovalRequest,
  isFunctionApprovalResponse,
  isImageContent,
  isAudioContent,
  isFileContent,
  isVectorStoreContent,
  getTextContent,
  getFunctionCalls,
  getFunctionResults,
  hasContent,
} from './chat-message';
