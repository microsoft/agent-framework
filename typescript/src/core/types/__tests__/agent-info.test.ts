/**
 * Tests for AgentInfo and AISettings types, builder, and validation functions.
 */

import { describe, it, expect } from 'vitest';
import {
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
} from '../agent-info';

describe('AgentInfo', () => {
  it('should create AgentInfo with all fields', () => {
    const agentInfo: AgentInfo = {
      id: 'agent-123',
      name: 'Test Agent',
      description: 'A test agent for unit testing',
      instructions: 'You are a helpful assistant',
      metadata: { version: '1.0', custom: true },
    };

    expect(agentInfo.id).toBe('agent-123');
    expect(agentInfo.name).toBe('Test Agent');
    expect(agentInfo.description).toBe('A test agent for unit testing');
    expect(agentInfo.instructions).toBe('You are a helpful assistant');
    expect(agentInfo.metadata).toEqual({ version: '1.0', custom: true });
  });

  it('should create AgentInfo with only required fields', () => {
    const agentInfo: AgentInfo = {
      id: 'agent-456',
      name: 'Minimal Agent',
    };

    expect(agentInfo.id).toBe('agent-456');
    expect(agentInfo.name).toBe('Minimal Agent');
    expect(agentInfo.description).toBeUndefined();
    expect(agentInfo.instructions).toBeUndefined();
    expect(agentInfo.metadata).toBeUndefined();
  });

  it('should create AgentInfo with optional description only', () => {
    const agentInfo: AgentInfo = {
      id: 'agent-789',
      name: 'Described Agent',
      description: 'Has description but no instructions',
    };

    expect(agentInfo.description).toBe('Has description but no instructions');
    expect(agentInfo.instructions).toBeUndefined();
    expect(agentInfo.metadata).toBeUndefined();
  });

  it('should create AgentInfo with complex metadata object', () => {
    const agentInfo: AgentInfo = {
      id: 'agent-complex',
      name: 'Complex Agent',
      metadata: {
        tags: ['production', 'customer-facing'],
        settings: {
          timeout: 30000,
          retries: 3,
        },
        enabled: true,
        priority: 1,
      },
    };

    expect(agentInfo.metadata).toEqual({
      tags: ['production', 'customer-facing'],
      settings: { timeout: 30000, retries: 3 },
      enabled: true,
      priority: 1,
    });
  });
});

describe('AISettings', () => {
  it('should create AISettings with all fields', () => {
    const settings: AISettings = {
      modelId: 'gpt-4',
      temperature: 0.7,
      topP: 0.9,
      maxTokens: 2000,
      stopSequences: ['STOP', 'END'],
      presencePenalty: 0.5,
      frequencyPenalty: 0.3,
      seed: 42,
      responseFormat: { type: 'json_object' },
      streamOptions: { includeUsage: true },
    };

    expect(settings.modelId).toBe('gpt-4');
    expect(settings.temperature).toBe(0.7);
    expect(settings.topP).toBe(0.9);
    expect(settings.maxTokens).toBe(2000);
    expect(settings.stopSequences).toEqual(['STOP', 'END']);
    expect(settings.presencePenalty).toBe(0.5);
    expect(settings.frequencyPenalty).toBe(0.3);
    expect(settings.seed).toBe(42);
    expect(settings.responseFormat).toEqual({ type: 'json_object' });
    expect(settings.streamOptions).toEqual({ includeUsage: true });
  });

  it('should create AISettings with only some fields', () => {
    const settings: AISettings = {
      modelId: 'gpt-3.5-turbo',
      temperature: 1.0,
      maxTokens: 1000,
    };

    expect(settings.modelId).toBe('gpt-3.5-turbo');
    expect(settings.temperature).toBe(1.0);
    expect(settings.maxTokens).toBe(1000);
    expect(settings.topP).toBeUndefined();
    expect(settings.presencePenalty).toBeUndefined();
  });

  it('should create AISettings with empty object (all optional)', () => {
    const settings: AISettings = {};

    expect(Object.keys(settings).length).toBe(0);
  });

  it('should accept empty stopSequences array', () => {
    const settings: AISettings = {
      stopSequences: [],
    };

    expect(settings.stopSequences).toEqual([]);
  });

  it('should support text response format', () => {
    const settings: AISettings = {
      responseFormat: { type: 'text' },
    };

    expect(settings.responseFormat?.type).toBe('text');
  });

  it('should support json_object response format', () => {
    const settings: AISettings = {
      responseFormat: { type: 'json_object' },
    };

    expect(settings.responseFormat?.type).toBe('json_object');
  });
});

describe('DEFAULT_AI_SETTINGS', () => {
  it('should have expected default values', () => {
    expect(DEFAULT_AI_SETTINGS.temperature).toBe(1.0);
    expect(DEFAULT_AI_SETTINGS.topP).toBe(1.0);
    expect(DEFAULT_AI_SETTINGS.maxTokens).toBe(4096);
  });

  it('should be immutable (readonly)', () => {
    expect(() => {
      // @ts-expect-error - Testing runtime immutability
      DEFAULT_AI_SETTINGS.temperature = 2.0;
    }).toThrow();
  });

  it('should not allow adding new properties', () => {
    expect(() => {
      // @ts-expect-error - Testing runtime immutability
      DEFAULT_AI_SETTINGS.modelId = 'gpt-4';
    }).toThrow();
  });
});

describe('validateTemperature', () => {
  it('should accept valid temperatures', () => {
    expect(() => validateTemperature(0)).not.toThrow();
    expect(() => validateTemperature(1)).not.toThrow();
    expect(() => validateTemperature(2)).not.toThrow();
    expect(() => validateTemperature(0.5)).not.toThrow();
    expect(() => validateTemperature(1.5)).not.toThrow();
  });

  it('should reject temperatures below 0', () => {
    expect(() => validateTemperature(-0.1)).toThrow(TypeError);
    expect(() => validateTemperature(-1)).toThrow(TypeError);
    expect(() => validateTemperature(-0.1)).toThrow('Temperature must be between 0 and 2');
  });

  it('should reject temperatures above 2', () => {
    expect(() => validateTemperature(2.1)).toThrow(TypeError);
    expect(() => validateTemperature(3)).toThrow(TypeError);
    expect(() => validateTemperature(2.1)).toThrow('Temperature must be between 0 and 2');
  });

  it('should reject non-number values', () => {
    // @ts-expect-error - Testing runtime validation
    expect(() => validateTemperature('1.0')).toThrow(TypeError);
    // @ts-expect-error - Testing runtime validation
    expect(() => validateTemperature(null)).toThrow(TypeError);
    // @ts-expect-error - Testing runtime validation
    expect(() => validateTemperature(undefined)).toThrow(TypeError);
  });

  it('should reject NaN', () => {
    expect(() => validateTemperature(NaN)).toThrow(TypeError);
  });
});

describe('validateTopP', () => {
  it('should accept valid topP values', () => {
    expect(() => validateTopP(0)).not.toThrow();
    expect(() => validateTopP(0.5)).not.toThrow();
    expect(() => validateTopP(1)).not.toThrow();
    expect(() => validateTopP(0.1)).not.toThrow();
    expect(() => validateTopP(0.9)).not.toThrow();
  });

  it('should reject topP below 0', () => {
    expect(() => validateTopP(-0.1)).toThrow(TypeError);
    expect(() => validateTopP(-1)).toThrow(TypeError);
    expect(() => validateTopP(-0.1)).toThrow('TopP must be between 0 and 1');
  });

  it('should reject topP above 1', () => {
    expect(() => validateTopP(1.1)).toThrow(TypeError);
    expect(() => validateTopP(2)).toThrow(TypeError);
    expect(() => validateTopP(1.1)).toThrow('TopP must be between 0 and 1');
  });

  it('should reject non-number values', () => {
    // @ts-expect-error - Testing runtime validation
    expect(() => validateTopP('0.5')).toThrow(TypeError);
    // @ts-expect-error - Testing runtime validation
    expect(() => validateTopP(null)).toThrow(TypeError);
  });

  it('should reject NaN', () => {
    expect(() => validateTopP(NaN)).toThrow(TypeError);
  });
});

describe('validateMaxTokens', () => {
  it('should accept valid maxTokens values', () => {
    expect(() => validateMaxTokens(1)).not.toThrow();
    expect(() => validateMaxTokens(100)).not.toThrow();
    expect(() => validateMaxTokens(4096)).not.toThrow();
    expect(() => validateMaxTokens(8192)).not.toThrow();
  });

  it('should reject zero', () => {
    expect(() => validateMaxTokens(0)).toThrow(TypeError);
    expect(() => validateMaxTokens(0)).toThrow('MaxTokens must be positive');
  });

  it('should reject negative values', () => {
    expect(() => validateMaxTokens(-1)).toThrow(TypeError);
    expect(() => validateMaxTokens(-100)).toThrow(TypeError);
    expect(() => validateMaxTokens(-1)).toThrow('MaxTokens must be positive');
  });

  it('should reject non-integer values', () => {
    expect(() => validateMaxTokens(1.5)).toThrow(TypeError);
    expect(() => validateMaxTokens(100.1)).toThrow(TypeError);
    expect(() => validateMaxTokens(1.5)).toThrow('MaxTokens must be an integer');
  });

  it('should reject non-number values', () => {
    // @ts-expect-error - Testing runtime validation
    expect(() => validateMaxTokens('100')).toThrow(TypeError);
    // @ts-expect-error - Testing runtime validation
    expect(() => validateMaxTokens(null)).toThrow(TypeError);
  });

  it('should reject NaN', () => {
    expect(() => validateMaxTokens(NaN)).toThrow(TypeError);
  });
});

describe('validatePenalty', () => {
  it('should accept valid penalty values', () => {
    expect(() => validatePenalty(-2)).not.toThrow();
    expect(() => validatePenalty(-1)).not.toThrow();
    expect(() => validatePenalty(0)).not.toThrow();
    expect(() => validatePenalty(1)).not.toThrow();
    expect(() => validatePenalty(2)).not.toThrow();
    expect(() => validatePenalty(0.5)).not.toThrow();
    expect(() => validatePenalty(-1.5)).not.toThrow();
  });

  it('should reject penalties below -2', () => {
    expect(() => validatePenalty(-2.1)).toThrow(TypeError);
    expect(() => validatePenalty(-3)).toThrow(TypeError);
    expect(() => validatePenalty(-2.1)).toThrow('Penalty must be between -2 and 2');
  });

  it('should reject penalties above 2', () => {
    expect(() => validatePenalty(2.1)).toThrow(TypeError);
    expect(() => validatePenalty(3)).toThrow(TypeError);
    expect(() => validatePenalty(2.1)).toThrow('Penalty must be between -2 and 2');
  });

  it('should use custom parameter name in error messages', () => {
    expect(() => validatePenalty(3, 'PresencePenalty')).toThrow('PresencePenalty must be between -2 and 2');
    expect(() => validatePenalty(3, 'FrequencyPenalty')).toThrow('FrequencyPenalty must be between -2 and 2');
  });

  it('should reject non-number values', () => {
    // @ts-expect-error - Testing runtime validation
    expect(() => validatePenalty('0.5')).toThrow(TypeError);
    // @ts-expect-error - Testing runtime validation
    expect(() => validatePenalty(null)).toThrow(TypeError);
  });

  it('should reject NaN', () => {
    expect(() => validatePenalty(NaN)).toThrow(TypeError);
  });
});

describe('validateAISettings', () => {
  it('should validate all fields in AISettings', () => {
    const validSettings: AISettings = {
      temperature: 0.7,
      topP: 0.9,
      maxTokens: 2000,
      presencePenalty: 0.5,
      frequencyPenalty: 0.3,
    };

    expect(() => validateAISettings(validSettings)).not.toThrow();
  });

  it('should validate empty settings', () => {
    expect(() => validateAISettings({})).not.toThrow();
  });

  it('should throw on invalid temperature', () => {
    const settings: AISettings = { temperature: 3 };
    expect(() => validateAISettings(settings)).toThrow(TypeError);
    expect(() => validateAISettings(settings)).toThrow('Temperature must be between 0 and 2');
  });

  it('should throw on invalid topP', () => {
    const settings: AISettings = { topP: 1.5 };
    expect(() => validateAISettings(settings)).toThrow(TypeError);
    expect(() => validateAISettings(settings)).toThrow('TopP must be between 0 and 1');
  });

  it('should throw on invalid maxTokens', () => {
    const settings: AISettings = { maxTokens: -1 };
    expect(() => validateAISettings(settings)).toThrow(TypeError);
    expect(() => validateAISettings(settings)).toThrow('MaxTokens must be positive');
  });

  it('should throw on invalid presencePenalty', () => {
    const settings: AISettings = { presencePenalty: 3 };
    expect(() => validateAISettings(settings)).toThrow(TypeError);
    expect(() => validateAISettings(settings)).toThrow('PresencePenalty must be between -2 and 2');
  });

  it('should throw on invalid frequencyPenalty', () => {
    const settings: AISettings = { frequencyPenalty: -3 };
    expect(() => validateAISettings(settings)).toThrow(TypeError);
    expect(() => validateAISettings(settings)).toThrow('FrequencyPenalty must be between -2 and 2');
  });

  it('should validate settings with boundary values', () => {
    const settings: AISettings = {
      temperature: 0,
      topP: 1,
      maxTokens: 1,
      presencePenalty: -2,
      frequencyPenalty: 2,
    };

    expect(() => validateAISettings(settings)).not.toThrow();
  });

  it('should skip validation for undefined fields', () => {
    const settings: AISettings = {
      modelId: 'gpt-4',
      seed: 42,
    };

    expect(() => validateAISettings(settings)).not.toThrow();
  });
});

describe('AISettingsBuilder', () => {
  it('should create settings with all fields', () => {
    const settings = new AISettingsBuilder()
      .modelId('gpt-4')
      .temperature(0.7)
      .topP(0.9)
      .maxTokens(2000)
      .stopSequences(['STOP'])
      .presencePenalty(0.5)
      .frequencyPenalty(0.3)
      .seed(42)
      .responseFormat({ type: 'json_object' })
      .streamOptions({ includeUsage: true })
      .build();

    expect(settings.modelId).toBe('gpt-4');
    expect(settings.temperature).toBe(0.7);
    expect(settings.topP).toBe(0.9);
    expect(settings.maxTokens).toBe(2000);
    expect(settings.stopSequences).toEqual(['STOP']);
    expect(settings.presencePenalty).toBe(0.5);
    expect(settings.frequencyPenalty).toBe(0.3);
    expect(settings.seed).toBe(42);
    expect(settings.responseFormat).toEqual({ type: 'json_object' });
    expect(settings.streamOptions).toEqual({ includeUsage: true });
  });

  it('should support method chaining (fluent interface)', () => {
    const builder = new AISettingsBuilder();
    const result1 = builder.modelId('gpt-4');
    const result2 = result1.temperature(0.7);
    const result3 = result2.maxTokens(2000);

    expect(result1).toBe(builder);
    expect(result2).toBe(builder);
    expect(result3).toBe(builder);
  });

  it('should validate temperature', () => {
    const builder = new AISettingsBuilder();

    expect(() => builder.temperature(0)).not.toThrow();
    expect(() => builder.temperature(1)).not.toThrow();
    expect(() => builder.temperature(2)).not.toThrow();
    expect(() => builder.temperature(-0.1)).toThrow(TypeError);
    expect(() => builder.temperature(2.1)).toThrow(TypeError);
  });

  it('should validate topP', () => {
    const builder = new AISettingsBuilder();

    expect(() => builder.topP(0)).not.toThrow();
    expect(() => builder.topP(0.5)).not.toThrow();
    expect(() => builder.topP(1)).not.toThrow();
    expect(() => builder.topP(-0.1)).toThrow(TypeError);
    expect(() => builder.topP(1.1)).toThrow(TypeError);
  });

  it('should validate maxTokens', () => {
    const builder = new AISettingsBuilder();

    expect(() => builder.maxTokens(1)).not.toThrow();
    expect(() => builder.maxTokens(100)).not.toThrow();
    expect(() => builder.maxTokens(4096)).not.toThrow();
    expect(() => builder.maxTokens(0)).toThrow(TypeError);
    expect(() => builder.maxTokens(-1)).toThrow(TypeError);
    expect(() => builder.maxTokens(1.5)).toThrow(TypeError);
  });

  it('should validate presencePenalty', () => {
    const builder = new AISettingsBuilder();

    expect(() => builder.presencePenalty(-2)).not.toThrow();
    expect(() => builder.presencePenalty(0)).not.toThrow();
    expect(() => builder.presencePenalty(2)).not.toThrow();
    expect(() => builder.presencePenalty(-2.1)).toThrow(TypeError);
    expect(() => builder.presencePenalty(2.1)).toThrow(TypeError);
  });

  it('should validate frequencyPenalty', () => {
    const builder = new AISettingsBuilder();

    expect(() => builder.frequencyPenalty(-2)).not.toThrow();
    expect(() => builder.frequencyPenalty(0)).not.toThrow();
    expect(() => builder.frequencyPenalty(2)).not.toThrow();
    expect(() => builder.frequencyPenalty(-2.1)).toThrow(TypeError);
    expect(() => builder.frequencyPenalty(2.1)).toThrow(TypeError);
  });

  it('should build empty settings with no method calls', () => {
    const settings = new AISettingsBuilder().build();

    expect(Object.keys(settings).length).toBe(0);
  });

  it('should return new object (not reference)', () => {
    const builder = new AISettingsBuilder().temperature(0.7).maxTokens(2000);

    const settings1 = builder.build();
    const settings2 = builder.build();

    expect(settings1).not.toBe(settings2);
    expect(settings1).toEqual(settings2);

    // Modifying one should not affect the other
    settings1.temperature = 1.0;
    expect(settings2.temperature).toBe(0.7);
  });

  it('should not affect builder state after build', () => {
    const builder = new AISettingsBuilder().temperature(0.7);

    const settings1 = builder.build();
    builder.temperature(1.5);
    const settings2 = builder.build();

    expect(settings1.temperature).toBe(0.7);
    expect(settings2.temperature).toBe(1.5);
  });

  it('should handle multiple builds with modifications', () => {
    const builder = new AISettingsBuilder();

    builder.modelId('gpt-3.5-turbo');
    const settings1 = builder.build();

    builder.temperature(0.8);
    const settings2 = builder.build();

    expect(settings1.modelId).toBe('gpt-3.5-turbo');
    expect(settings1.temperature).toBeUndefined();
    expect(settings2.modelId).toBe('gpt-3.5-turbo');
    expect(settings2.temperature).toBe(0.8);
  });

  it('should allow overwriting previous values', () => {
    const settings = new AISettingsBuilder()
      .temperature(0.5)
      .temperature(0.7)
      .build();

    expect(settings.temperature).toBe(0.7);
  });
});
