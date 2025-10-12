/**
 * Tools module - AI function calling and tool execution.
 *
 * This module provides the core functionality for creating and managing AI tools
 * that can be invoked by LLMs. It includes:
 *
 * - AITool interface for defining tools
 * - BaseTool abstract class for implementing custom tools
 * - FunctionTool for wrapping functions as tools
 * - createTool helper for easy tool creation
 * - @aiFunction decorator for marking methods as AI functions
 * - Schema conversion utilities for LLM integration
 *
 * @module tools
 */

export { AITool, BaseTool, FunctionTool, createTool } from './base-tool.js';
export {
  aiFunction,
  getAIFunctionMetadata,
  isAIFunction,
  getAllAIFunctions,
  type AIFunctionConfig,
  type AIFunctionMetadata,
} from './decorators.js';
export {
  zodToJsonSchema,
  createToolSchema,
  type JsonSchema,
  type AIToolSchema,
} from './schema.js';
