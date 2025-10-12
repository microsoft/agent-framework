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
