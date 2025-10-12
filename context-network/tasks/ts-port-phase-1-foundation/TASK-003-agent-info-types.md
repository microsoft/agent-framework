# Task: TASK-003 Core Type Definitions - AgentInfo & AISettings

**Phase**: 1
**Priority**: High
**Estimated Effort**: 3 hours
**Dependencies**: TASK-001

## Objective
Implement AgentInfo and AISettings interfaces with comprehensive model configuration options and validation.

## Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-1 (Agent Metadata), § FR-2 (AI Settings)
- **Python Reference**: `/python/packages/core/agent_framework/_types.py:200-400`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Abstractions/AgentInfo.cs`, `/dotnet/src/Microsoft.Agents.AI.Abstractions/AISettings.cs`
- **Standards**: CLAUDE.md § Code Quality Standards

## Files to Create/Modify
- `src/core/types/agent-info.ts` - AgentInfo and AISettings types
- `src/core/types/__tests__/agent-info.test.ts` - Tests
- `src/core/types/index.ts` - Re-exports

## Implementation Requirements

### Core Functionality

1. **Define AgentInfo interface**:
   ```typescript
   export interface AgentInfo {
     id: string;                           // Unique identifier
     name: string;                         // Display name
     description?: string;                 // Purpose/capabilities
     instructions?: string;                // System instructions
     metadata?: Record<string, unknown>;   // Custom properties
   }
   ```

2. **Define AISettings interface**:
   ```typescript
   export interface AISettings {
     modelId?: string;                     // Model identifier
     temperature?: number;                 // 0.0 to 2.0
     topP?: number;                        // 0.0 to 1.0
     maxTokens?: number;                   // Max completion tokens (positive integer)
     stopSequences?: string[];             // Custom stop sequences
     presencePenalty?: number;             // -2.0 to 2.0
     frequencyPenalty?: number;            // -2.0 to 2.0
     seed?: number;                        // Reproducibility seed
     responseFormat?: ResponseFormat;      // Output format
     streamOptions?: StreamOptions;        // Streaming config
   }
   ```

3. **Define supporting types**:
   ```typescript
   export interface ResponseFormat {
     type: 'text' | 'json_object';
   }

   export interface StreamOptions {
     includeUsage?: boolean;
   }
   ```

4. **Create AISettingsBuilder class** (fluent interface):
   ```typescript
   export class AISettingsBuilder {
     private settings: AISettings = {};

     modelId(id: string): this;
     temperature(value: number): this;     // Validates 0-2 range
     topP(value: number): this;            // Validates 0-1 range
     maxTokens(value: number): this;       // Validates positive integer
     stopSequences(sequences: string[]): this;
     presencePenalty(value: number): this; // Validates -2 to 2 range
     frequencyPenalty(value: number): this;// Validates -2 to 2 range
     seed(value: number): this;
     responseFormat(format: ResponseFormat): this;
     streamOptions(options: StreamOptions): this;
     build(): AISettings;
   }
   ```

5. **Create validation functions**:
   ```typescript
   export function validateTemperature(value: number): void;
   export function validateTopP(value: number): void;
   export function validateMaxTokens(value: number): void;
   export function validatePenalty(value: number): void;
   export function validateAISettings(settings: AISettings): void;
   ```

6. **Create default settings constant**:
   ```typescript
   export const DEFAULT_AI_SETTINGS: Readonly<AISettings> = {
     temperature: 1.0,
     topP: 1.0,
     maxTokens: 4096,
   };
   ```

### TypeScript Patterns
- Use interfaces for object shapes
- Use optional properties with `?`
- Use `Readonly<T>` for constants
- Use fluent interface pattern for builder
- Throw TypeError for validation failures
- Export validation functions for reuse

### Code Standards
- Document valid ranges in JSDoc with `@throws` for validation errors
- Include validation in builder methods
- Export default settings constant
- Use descriptive error messages

## Test Requirements

### AgentInfo Tests
- [ ] Test AgentInfo creation with all fields
- [ ] Test AgentInfo with only required fields (id, name)
- [ ] Test AgentInfo with optional fields individually
- [ ] Test AgentInfo with complex metadata object

### AISettings Tests
- [ ] Test AISettings with all fields
- [ ] Test AISettings with only some fields
- [ ] Test AISettings with empty object (all optional)
- [ ] Test default settings are immutable (readonly)

### Builder Tests
- [ ] Test builder creates settings with all fields
- [ ] Test builder fluent interface (method chaining)
- [ ] Test builder validates temperature (0-2 range)
  - Valid: 0, 1, 2
  - Invalid: -0.1, 2.1
- [ ] Test builder validates topP (0-1 range)
  - Valid: 0, 0.5, 1
  - Invalid: -0.1, 1.1
- [ ] Test builder validates maxTokens (positive integer)
  - Valid: 1, 100, 4096
  - Invalid: 0, -1, 1.5
- [ ] Test builder validates presencePenalty (-2 to 2 range)
- [ ] Test builder validates frequencyPenalty (-2 to 2 range)
- [ ] Test builder build() returns new object (not reference)

### Validation Function Tests
- [ ] Test `validateTemperature` throws for out of range
- [ ] Test `validateTopP` throws for out of range
- [ ] Test `validateMaxTokens` throws for non-positive or non-integer
- [ ] Test `validatePenalty` throws for out of range
- [ ] Test `validateAISettings` validates all fields
- [ ] Test validation error messages are descriptive

### Edge Case Tests
- [ ] Test settings with boundary values (0, 1, 2, -2)
- [ ] Test settings with undefined vs missing fields
- [ ] Test empty stopSequences array
- [ ] Test builder with no method calls returns empty settings

**Minimum Coverage**: 85%

## Acceptance Criteria
- [ ] AgentInfo interface with all required and optional fields
- [ ] AISettings interface with all model parameters
- [ ] ResponseFormat and StreamOptions supporting types
- [ ] AISettingsBuilder class with fluent interface
- [ ] All builder methods validate input ranges
- [ ] Validation functions for each numeric parameter
- [ ] Default settings exported as readonly constant
- [ ] JSDoc includes valid ranges and @throws annotations
- [ ] Tests cover all validation edge cases
- [ ] Tests achieve >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings

## Example Code Pattern

```typescript
/**
 * AI model settings for chat completion.
 */
export interface AISettings {
  modelId?: string;
  /** Temperature for sampling (0.0 to 2.0) */
  temperature?: number;
  /** Top-p for nucleus sampling (0.0 to 1.0) */
  topP?: number;
  /** Maximum number of tokens to generate (positive integer) */
  maxTokens?: number;
  // ... other fields
}

/**
 * Builder for AISettings with validation.
 *
 * @example
 * ```typescript
 * const settings = new AISettingsBuilder()
 *   .modelId('gpt-4')
 *   .temperature(0.7)
 *   .maxTokens(2000)
 *   .build();
 * ```
 */
export class AISettingsBuilder {
  private settings: AISettings = {};

  /**
   * Set the model ID.
   * @param id - Model identifier
   * @returns Builder instance for chaining
   */
  modelId(id: string): this {
    this.settings.modelId = id;
    return this;
  }

  /**
   * Set the temperature.
   * @param value - Temperature value (0.0 to 2.0)
   * @returns Builder instance for chaining
   * @throws {TypeError} If value is not in range [0, 2]
   */
  temperature(value: number): this {
    validateTemperature(value);
    this.settings.temperature = value;
    return this;
  }

  /**
   * Build the AISettings object.
   * @returns New AISettings instance
   */
  build(): AISettings {
    return { ...this.settings };
  }
}

/**
 * Validate temperature value.
 * @param value - Temperature to validate
 * @throws {TypeError} If value is not in range [0, 2]
 */
export function validateTemperature(value: number): void {
  if (value < 0 || value > 2) {
    throw new TypeError(`Temperature must be between 0 and 2, got ${value}`);
  }
}

/**
 * Default AI settings.
 */
export const DEFAULT_AI_SETTINGS: Readonly<AISettings> = {
  temperature: 1.0,
  topP: 1.0,
  maxTokens: 4096,
};
```

## Related Tasks
- **Blocks**: TASK-004 (ChatClientProtocol uses AISettings), TASK-007 (BaseAgent uses AgentInfo)
- **Blocked by**: TASK-001 (Project scaffolding)
- **Related**: TASK-002 (Similar type definition patterns)
