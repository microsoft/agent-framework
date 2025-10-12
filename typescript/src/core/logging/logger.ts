/**
 * Copyright (c) Microsoft. All rights reserved.
 * Logging system for the Microsoft Agent Framework
 */

/**
 * Log levels for filtering log output
 */
export enum LogLevel {
  DEBUG = 'debug',
  INFO = 'info',
  WARN = 'warn',
  ERROR = 'error',
}

/**
 * Logger interface for structured logging with metadata support
 */
export interface Logger {
  /**
   * Log a debug message
   * @param message The message to log
   * @param context Optional structured context/metadata
   */
  debug(message: string, context?: Record<string, unknown>): void;

  /**
   * Log an info message
   * @param message The message to log
   * @param context Optional structured context/metadata
   */
  info(message: string, context?: Record<string, unknown>): void;

  /**
   * Log a warning message
   * @param message The message to log
   * @param context Optional structured context/metadata
   */
  warn(message: string, context?: Record<string, unknown>): void;

  /**
   * Log an error message
   * @param message The message to log
   * @param error Optional error object
   * @param context Optional structured context/metadata
   */
  error(message: string, error?: Error, context?: Record<string, unknown>): void;

  /**
   * Set the minimum log level for this logger
   * @param level The minimum log level
   */
  setLevel(level: LogLevel): void;
}

/**
 * Logging configuration options
 */
export interface LoggingConfig {
  /**
   * Minimum log level (default: INFO)
   */
  level?: LogLevel;

  /**
   * Output format: 'json' or 'text' (default: 'text')
   */
  format?: 'json' | 'text';

  /**
   * Custom destination function for log output
   * If not provided, uses console methods
   */
  destination?: (message: string) => void;

  /**
   * Include timestamp in log messages (default: true)
   */
  includeTimestamp?: boolean;

  /**
   * Include logger name in log messages (default: true)
   */
  includeLoggerName?: boolean;
}

/**
 * Log level hierarchy for filtering
 */
const LOG_LEVEL_HIERARCHY: Record<LogLevel, number> = {
  [LogLevel.DEBUG]: 0,
  [LogLevel.INFO]: 1,
  [LogLevel.WARN]: 2,
  [LogLevel.ERROR]: 3,
};

/**
 * Global logging configuration
 */
let globalConfig: Required<LoggingConfig> = {
  level: LogLevel.INFO,
  format: 'text',
  destination: (message: string): void => console.log(message),
  includeTimestamp: true,
  includeLoggerName: true,
};

/**
 * Registry of all loggers
 */
const loggers = new Map<string, ConsoleLogger>();

/**
 * Default console-based logger implementation
 */
class ConsoleLogger implements Logger {
  private minLevel: LogLevel;

  constructor(
    private readonly name: string,
    level?: LogLevel
  ) {
    this.minLevel = level ?? globalConfig.level;
  }

  setLevel(level: LogLevel): void {
    this.minLevel = level;
  }

  debug(message: string, context?: Record<string, unknown>): void {
    this.log(LogLevel.DEBUG, message, context);
  }

  info(message: string, context?: Record<string, unknown>): void {
    this.log(LogLevel.INFO, message, context);
  }

  warn(message: string, context?: Record<string, unknown>): void {
    this.log(LogLevel.WARN, message, context);
  }

  error(message: string, error?: Error, context?: Record<string, unknown>): void {
    const enhancedContext = { ...context };
    if (error) {
      enhancedContext.error = {
        name: error.name,
        message: error.message,
        stack: error.stack,
      };
    }
    this.log(LogLevel.ERROR, message, enhancedContext);
  }

  private log(level: LogLevel, message: string, context?: Record<string, unknown>): void {
    // Check if this log level should be output
    if (LOG_LEVEL_HIERARCHY[level] < LOG_LEVEL_HIERARCHY[this.minLevel]) {
      return;
    }

    const logEntry = this.formatLogEntry(level, message, context);

    // Use appropriate console method based on level
    if (globalConfig.destination) {
      globalConfig.destination(logEntry);
    } else {
      switch (level) {
        case LogLevel.DEBUG:
        case LogLevel.INFO:
          console.log(logEntry);
          break;
        case LogLevel.WARN:
          console.warn(logEntry);
          break;
        case LogLevel.ERROR:
          console.error(logEntry);
          break;
      }
    }
  }

  private formatLogEntry(
    level: LogLevel,
    message: string,
    context?: Record<string, unknown>
  ): string {
    if (globalConfig.format === 'json') {
      return this.formatJson(level, message, context);
    }
    return this.formatText(level, message, context);
  }

  private formatJson(
    level: LogLevel,
    message: string,
    context?: Record<string, unknown>
  ): string {
    const entry: Record<string, unknown> = {
      level: level.toUpperCase(),
      message,
    };

    if (globalConfig.includeTimestamp) {
      entry.timestamp = new Date().toISOString();
    }

    if (globalConfig.includeLoggerName) {
      entry.logger = this.name;
    }

    if (context && Object.keys(context).length > 0) {
      entry.context = context;
    }

    return JSON.stringify(entry);
  }

  private formatText(
    level: LogLevel,
    message: string,
    context?: Record<string, unknown>
  ): string {
    const parts: string[] = [];

    if (globalConfig.includeTimestamp) {
      const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
      parts.push(`[${timestamp}`);
    }

    if (globalConfig.includeLoggerName) {
      if (parts.length > 0) {
        parts.push(`- ${this.name} - ${level.toUpperCase()}]`);
      } else {
        parts.push(`[${this.name} - ${level.toUpperCase()}]`);
      }
    } else if (parts.length > 0) {
      parts.push(`- ${level.toUpperCase()}]`);
    }

    parts.push(message);

    if (context && Object.keys(context).length > 0) {
      const contextStr = JSON.stringify(context, null, 2);
      parts.push(`\n${contextStr}`);
    }

    return parts.join(' ');
  }
}

/**
 * Configure global logging settings
 *
 * @param config Logging configuration options
 *
 * @example
 * ```typescript
 * configureLogging({
 *   level: LogLevel.DEBUG,
 *   format: 'json',
 *   includeTimestamp: true
 * });
 * ```
 */
export function configureLogging(config: LoggingConfig): void {
  if (config.level !== undefined) {
    globalConfig.level = config.level;
    // Update all existing loggers to use new level
    for (const logger of loggers.values()) {
      logger.setLevel(config.level);
    }
  }

  if (config.format !== undefined) {
    globalConfig.format = config.format;
  }

  if (config.destination !== undefined) {
    globalConfig.destination = config.destination;
  }

  if (config.includeTimestamp !== undefined) {
    globalConfig.includeTimestamp = config.includeTimestamp;
  }

  if (config.includeLoggerName !== undefined) {
    globalConfig.includeLoggerName = config.includeLoggerName;
  }
}

/**
 * Get or create a logger with the specified name.
 *
 * Logger names must start with 'agent_framework' to ensure consistency
 * across the framework.
 *
 * @param name Logger name (must start with 'agent_framework')
 * @returns Logger instance
 * @throws {Error} If name doesn't start with 'agent_framework'
 *
 * @example
 * ```typescript
 * const logger = getLogger('agent_framework.agents');
 * logger.info('Agent initialized', { agentId: 'agent-123' });
 * ```
 */
export function getLogger(name: string = 'agent_framework'): Logger {
  if (!name.startsWith('agent_framework')) {
    throw new Error("Logger name must start with 'agent_framework'");
  }

  if (!loggers.has(name)) {
    loggers.set(name, new ConsoleLogger(name));
  }

  return loggers.get(name)!;
}

/**
 * Reset all loggers (primarily for testing)
 * @internal
 */
export function resetLoggers(): void {
  loggers.clear();
  globalConfig = {
    level: LogLevel.INFO,
    format: 'text',
    destination: (message: string): void => console.log(message),
    includeTimestamp: true,
    includeLoggerName: true,
  };
}
