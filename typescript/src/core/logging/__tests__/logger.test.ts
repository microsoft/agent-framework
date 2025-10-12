/**
 * Copyright (c) Microsoft. All rights reserved.
 * Tests for the logging system
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  getLogger,
  configureLogging,
  LogLevel,
  resetLoggers,
  type Logger,
} from '../logger.js';

describe('Logger', () => {
  // Capture console output
  let consoleOutput: string[] = [];
  let originalConsoleLog: typeof console.log;
  let originalConsoleWarn: typeof console.warn;
  let originalConsoleError: typeof console.error;

  beforeEach(() => {
    // Reset loggers before each test
    resetLoggers();
    consoleOutput = [];

    // Mock console methods
    originalConsoleLog = console.log;
    originalConsoleWarn = console.warn;
    originalConsoleError = console.error;

    console.log = vi.fn((...args) => consoleOutput.push(args.join(' ')));
    console.warn = vi.fn((...args) => consoleOutput.push(args.join(' ')));
    console.error = vi.fn((...args) => consoleOutput.push(args.join(' ')));
  });

  afterEach(() => {
    // Restore console methods
    console.log = originalConsoleLog;
    console.warn = originalConsoleWarn;
    console.error = originalConsoleError;
  });

  describe('getLogger', () => {
    it('should create a logger with default name', () => {
      const logger = getLogger();
      expect(logger).toBeDefined();
    });

    it('should create a logger with custom name', () => {
      const logger = getLogger('agent_framework.agents');
      expect(logger).toBeDefined();
    });

    it('should return the same logger instance for the same name', () => {
      const logger1 = getLogger('agent_framework.test');
      const logger2 = getLogger('agent_framework.test');
      expect(logger1).toBe(logger2);
    });

    it('should throw error if name does not start with agent_framework', () => {
      expect(() => getLogger('invalid.name')).toThrow(
        "Logger name must start with 'agent_framework'"
      );
    });

    it('should create different loggers for different names', () => {
      const logger1 = getLogger('agent_framework.agents');
      const logger2 = getLogger('agent_framework.tools');
      expect(logger1).not.toBe(logger2);
    });
  });

  describe('LogLevel', () => {
    it('should have all required log levels', () => {
      expect(LogLevel.DEBUG).toBe('debug');
      expect(LogLevel.INFO).toBe('info');
      expect(LogLevel.WARN).toBe('warn');
      expect(LogLevel.ERROR).toBe('error');
    });
  });

  describe('Logger methods', () => {
    let logger: Logger;

    beforeEach(() => {
      logger = getLogger('agent_framework.test');
    });

    it('should log debug messages', () => {
      configureLogging({ level: LogLevel.DEBUG });
      logger.debug('Debug message');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('DEBUG');
      expect(consoleOutput[0]).toContain('Debug message');
    });

    it('should log info messages', () => {
      logger.info('Info message');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('INFO');
      expect(consoleOutput[0]).toContain('Info message');
    });

    it('should log warn messages', () => {
      logger.warn('Warning message');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('WARN');
      expect(consoleOutput[0]).toContain('Warning message');
    });

    it('should log error messages', () => {
      logger.error('Error message');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('ERROR');
      expect(consoleOutput[0]).toContain('Error message');
    });

    it('should include error details when provided', () => {
      const error = new Error('Test error');
      logger.error('Error occurred', error);
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('Error occurred');
      expect(consoleOutput[0]).toContain('Test error');
    });

    it('should log structured context', () => {
      logger.info('Message with context', { userId: '123', action: 'login' });
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('Message with context');
      expect(consoleOutput[0]).toContain('userId');
      expect(consoleOutput[0]).toContain('123');
    });

    it('should handle empty context gracefully', () => {
      logger.info('Message without context', {});
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('Message without context');
    });
  });

  describe('Log level filtering', () => {
    let logger: Logger;

    beforeEach(() => {
      logger = getLogger('agent_framework.filter');
    });

    it('should filter debug messages when level is INFO', () => {
      configureLogging({ level: LogLevel.INFO });
      logger.debug('Should not appear');
      logger.info('Should appear');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('Should appear');
    });

    it('should filter debug and info messages when level is WARN', () => {
      configureLogging({ level: LogLevel.WARN });
      logger.debug('Should not appear');
      logger.info('Should not appear');
      logger.warn('Should appear');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('Should appear');
    });

    it('should only show error messages when level is ERROR', () => {
      configureLogging({ level: LogLevel.ERROR });
      logger.debug('Should not appear');
      logger.info('Should not appear');
      logger.warn('Should not appear');
      logger.error('Should appear');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('Should appear');
    });

    it('should show all messages when level is DEBUG', () => {
      configureLogging({ level: LogLevel.DEBUG });
      logger.debug('Debug');
      logger.info('Info');
      logger.warn('Warn');
      logger.error('Error');
      expect(consoleOutput.length).toBe(4);
    });

    it('should allow setting log level per logger', () => {
      const logger1 = getLogger('agent_framework.verbose');
      const logger2 = getLogger('agent_framework.quiet');

      logger1.setLevel(LogLevel.DEBUG);
      logger2.setLevel(LogLevel.ERROR);

      logger1.debug('Debug from logger1');
      logger2.debug('Debug from logger2');

      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('Debug from logger1');
    });
  });

  describe('configureLogging', () => {
    it('should configure log level globally', () => {
      configureLogging({ level: LogLevel.WARN });
      const logger = getLogger('agent_framework.config');
      logger.info('Should not appear');
      logger.warn('Should appear');
      expect(consoleOutput.length).toBe(1);
    });

    it('should configure output format as JSON', () => {
      configureLogging({ format: 'json' });
      const logger = getLogger('agent_framework.json');
      logger.info('JSON message', { key: 'value' });
      expect(consoleOutput.length).toBe(1);
      const parsed = JSON.parse(consoleOutput[0]);
      expect(parsed.level).toBe('INFO');
      expect(parsed.message).toBe('JSON message');
      expect(parsed.context).toEqual({ key: 'value' });
    });

    it('should configure output format as text', () => {
      configureLogging({ format: 'text' });
      const logger = getLogger('agent_framework.text');
      logger.info('Text message');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('INFO');
      expect(consoleOutput[0]).toContain('Text message');
    });

    it('should use custom destination', () => {
      const customOutput: string[] = [];
      configureLogging({
        destination: (message) => customOutput.push(message),
      });
      const logger = getLogger('agent_framework.custom');
      logger.info('Custom destination');
      expect(consoleOutput.length).toBe(0);
      expect(customOutput.length).toBe(1);
      expect(customOutput[0]).toContain('Custom destination');
    });

    it('should configure timestamp inclusion', () => {
      configureLogging({ includeTimestamp: false });
      const logger = getLogger('agent_framework.notimestamp');
      logger.info('Message');
      expect(consoleOutput.length).toBe(1);
      // Should not contain ISO timestamp pattern
      expect(consoleOutput[0]).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    });

    it('should configure logger name inclusion', () => {
      configureLogging({ includeLoggerName: false });
      const logger = getLogger('agent_framework.noname');
      logger.info('Message');
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).not.toContain('agent_framework.noname');
    });

    it('should update existing loggers when level changes', () => {
      const logger = getLogger('agent_framework.existing');
      configureLogging({ level: LogLevel.ERROR });
      logger.info('Should not appear');
      logger.error('Should appear');
      expect(consoleOutput.length).toBe(1);
    });
  });

  describe('Structured logging', () => {
    let logger: Logger;

    beforeEach(() => {
      logger = getLogger('agent_framework.structured');
    });

    it('should log with string context', () => {
      logger.info('User action', { userId: 'user-123', action: 'login' });
      expect(consoleOutput[0]).toContain('userId');
      expect(consoleOutput[0]).toContain('user-123');
    });

    it('should log with number context', () => {
      logger.info('Metric', { count: 42, duration: 1.5 });
      expect(consoleOutput[0]).toContain('count');
      expect(consoleOutput[0]).toContain('42');
    });

    it('should log with boolean context', () => {
      logger.info('Status', { success: true, cached: false });
      expect(consoleOutput[0]).toContain('success');
      expect(consoleOutput[0]).toContain('true');
    });

    it('should log with nested object context', () => {
      logger.info('Complex data', {
        user: { id: '123', name: 'Test' },
        metadata: { timestamp: Date.now() },
      });
      expect(consoleOutput[0]).toContain('user');
      expect(consoleOutput[0]).toContain('metadata');
    });

    it('should log with array context', () => {
      logger.info('Array data', { items: [1, 2, 3], tags: ['a', 'b'] });
      expect(consoleOutput[0]).toContain('items');
      expect(consoleOutput[0]).toContain('tags');
    });

    it('should handle undefined context', () => {
      logger.info('No context', undefined);
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('No context');
    });
  });

  describe('JSON format', () => {
    beforeEach(() => {
      configureLogging({ format: 'json' });
    });

    it('should output valid JSON', () => {
      const logger = getLogger('agent_framework.json');
      logger.info('Test message');
      expect(() => JSON.parse(consoleOutput[0])).not.toThrow();
    });

    it('should include timestamp in JSON', () => {
      configureLogging({ format: 'json', includeTimestamp: true });
      const logger = getLogger('agent_framework.json');
      logger.info('Test');
      const parsed = JSON.parse(consoleOutput[0]);
      expect(parsed.timestamp).toBeDefined();
      expect(typeof parsed.timestamp).toBe('string');
    });

    it('should include logger name in JSON', () => {
      configureLogging({ format: 'json', includeLoggerName: true });
      const logger = getLogger('agent_framework.json');
      logger.info('Test');
      const parsed = JSON.parse(consoleOutput[0]);
      expect(parsed.logger).toBe('agent_framework.json');
    });

    it('should include context in JSON', () => {
      const logger = getLogger('agent_framework.json');
      logger.info('Test', { key: 'value' });
      const parsed = JSON.parse(consoleOutput[0]);
      expect(parsed.context).toEqual({ key: 'value' });
    });

    it('should include error details in JSON', () => {
      const logger = getLogger('agent_framework.json');
      const error = new Error('Test error');
      logger.error('Error occurred', error);
      const parsed = JSON.parse(consoleOutput[0]);
      expect(parsed.context.error).toBeDefined();
      expect(parsed.context.error.message).toBe('Test error');
      expect(parsed.context.error.name).toBe('Error');
    });
  });

  describe('Text format', () => {
    beforeEach(() => {
      configureLogging({ format: 'text' });
    });

    it('should include timestamp in text format', () => {
      configureLogging({ format: 'text', includeTimestamp: true });
      const logger = getLogger('agent_framework.text');
      logger.info('Test');
      // Should contain date pattern [YYYY-MM-DD HH:MM:SS
      expect(consoleOutput[0]).toMatch(/\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/);
    });

    it('should include logger name in text format', () => {
      configureLogging({ format: 'text', includeLoggerName: true });
      const logger = getLogger('agent_framework.text');
      logger.info('Test');
      expect(consoleOutput[0]).toContain('agent_framework.text');
    });

    it('should include level in text format', () => {
      const logger = getLogger('agent_framework.text');
      logger.info('Test');
      expect(consoleOutput[0]).toContain('INFO');
    });

    it('should format context as JSON in text format', () => {
      const logger = getLogger('agent_framework.text');
      logger.info('Test', { key: 'value' });
      expect(consoleOutput[0]).toContain('"key"');
      expect(consoleOutput[0]).toContain('"value"');
    });
  });

  describe('Edge cases', () => {
    it('should handle very long messages', () => {
      const logger = getLogger('agent_framework.edge');
      const longMessage = 'x'.repeat(10000);
      logger.info(longMessage);
      expect(consoleOutput.length).toBe(1);
      expect(consoleOutput[0]).toContain('x'.repeat(100));
    });

    it('should handle special characters in messages', () => {
      const logger = getLogger('agent_framework.edge');
      logger.info('Message with\nnewlines\tand\ttabs');
      expect(consoleOutput.length).toBe(1);
    });

    it('should handle circular references in context gracefully', () => {
      const logger = getLogger('agent_framework.edge');
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const circular: any = { name: 'test' };
      circular.self = circular;
      // Should throw - JSON.stringify cannot handle circular references
      expect(() => logger.info('Circular', circular)).toThrow();
    });

    it('should handle null and undefined in context', () => {
      const logger = getLogger('agent_framework.edge');
      logger.info('Null context', { value: null, undef: undefined });
      expect(consoleOutput.length).toBe(1);
    });

    it('should handle multiple logger instances', () => {
      const logger1 = getLogger('agent_framework.one');
      getLogger('agent_framework.two'); // Create but don't use
      const logger3 = getLogger('agent_framework.three');

      logger1.info('From one');
      logger3.info('From three');

      expect(consoleOutput.length).toBe(2);
    });

    it('should handle rapid consecutive logs', () => {
      const logger = getLogger('agent_framework.rapid');
      for (let i = 0; i < 100; i++) {
        logger.info(`Message ${i}`);
      }
      expect(consoleOutput.length).toBe(100);
    });
  });

  describe('resetLoggers', () => {
    it('should clear all loggers', () => {
      const logger1 = getLogger('agent_framework.one');
      getLogger('agent_framework.two'); // Create another logger
      resetLoggers();
      const logger3 = getLogger('agent_framework.one');
      // Should be a new instance
      expect(logger3).not.toBe(logger1);
    });

    it('should reset to default configuration', () => {
      configureLogging({ level: LogLevel.ERROR, format: 'json' });
      resetLoggers();
      const logger = getLogger('agent_framework.reset');
      logger.info('Should appear with default config');
      expect(consoleOutput.length).toBe(1);
      // Should be text format (default)
      expect(consoleOutput[0]).not.toMatch(/^\{/);
    });
  });
});
