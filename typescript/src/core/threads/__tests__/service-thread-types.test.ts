/**
 * Tests for service thread types and validation logic.
 */

import { describe, it, expect } from 'vitest';
import {
  ThreadType,
  validateThreadOptions,
  determineThreadType,
  isServiceManaged,
  isLocalManaged,
  isUndetermined,
} from '../service-thread-types';
import { AgentInitializationError } from '../../errors/agent-errors';
import { InMemoryMessageStore } from '../../storage/in-memory-store';

describe('ThreadType', () => {
  it('should have SERVICE_MANAGED value', () => {
    expect(ThreadType.SERVICE_MANAGED).toBe('service_managed');
  });

  it('should have LOCAL_MANAGED value', () => {
    expect(ThreadType.LOCAL_MANAGED).toBe('local_managed');
  });

  it('should have UNDETERMINED value', () => {
    expect(ThreadType.UNDETERMINED).toBe('undetermined');
  });

  it('should be an enum with exactly 3 values', () => {
    const values = Object.values(ThreadType);
    expect(values).toHaveLength(3);
    expect(values).toContain('service_managed');
    expect(values).toContain('local_managed');
    expect(values).toContain('undetermined');
  });
});

describe('validateThreadOptions', () => {
  describe('valid configurations', () => {
    it('should accept conversationId alone', () => {
      expect(() => {
        validateThreadOptions({ conversationId: 'thread-123' });
      }).not.toThrow();
    });

    it('should accept messageStoreFactory alone', () => {
      expect(() => {
        validateThreadOptions({
          messageStoreFactory: () => new InMemoryMessageStore(),
        });
      }).not.toThrow();
    });

    it('should accept neither option (undetermined)', () => {
      expect(() => {
        validateThreadOptions({});
      }).not.toThrow();
    });

    it('should accept undefined conversationId', () => {
      expect(() => {
        validateThreadOptions({ conversationId: undefined });
      }).not.toThrow();
    });

    it('should accept undefined messageStoreFactory', () => {
      expect(() => {
        validateThreadOptions({ messageStoreFactory: undefined });
      }).not.toThrow();
    });
  });

  describe('invalid configurations', () => {
    it('should reject both conversationId and messageStoreFactory', () => {
      expect(() => {
        validateThreadOptions({
          conversationId: 'thread-123',
          messageStoreFactory: () => new InMemoryMessageStore(),
        });
      }).toThrow(AgentInitializationError);
    });

    it('should throw error with descriptive message', () => {
      expect(() => {
        validateThreadOptions({
          conversationId: 'thread-123',
          messageStoreFactory: () => new InMemoryMessageStore(),
        });
      }).toThrow('Cannot specify both conversationId and messageStoreFactory');
    });

    it('should provide guidance in error message', () => {
      try {
        validateThreadOptions({
          conversationId: 'thread-123',
          messageStoreFactory: () => new InMemoryMessageStore(),
        });
        // Should not reach here
        expect(true).toBe(false);
      } catch (error) {
        expect(error).toBeInstanceOf(AgentInitializationError);
        const message = (error as AgentInitializationError).message;
        expect(message).toContain('service-managed');
        expect(message).toContain('local threads');
      }
    });
  });
});

describe('determineThreadType', () => {
  describe('SERVICE_MANAGED detection', () => {
    it('should return SERVICE_MANAGED with conversationId', () => {
      const type = determineThreadType({
        conversationId: 'thread-123',
      });
      expect(type).toBe(ThreadType.SERVICE_MANAGED);
    });

    it('should return SERVICE_MANAGED with hasConversationIdFromResponse', () => {
      const type = determineThreadType({
        hasConversationIdFromResponse: true,
      });
      expect(type).toBe(ThreadType.SERVICE_MANAGED);
    });

    it('should prioritize conversationId over messageStoreFactory', () => {
      const type = determineThreadType({
        conversationId: 'thread-123',
        messageStoreFactory: () => new InMemoryMessageStore(),
      });
      expect(type).toBe(ThreadType.SERVICE_MANAGED);
    });

    it('should prioritize hasConversationIdFromResponse over messageStoreFactory', () => {
      const type = determineThreadType({
        hasConversationIdFromResponse: true,
        messageStoreFactory: () => new InMemoryMessageStore(),
      });
      expect(type).toBe(ThreadType.SERVICE_MANAGED);
    });

    it('should handle both conversationId and hasConversationIdFromResponse', () => {
      const type = determineThreadType({
        conversationId: 'thread-123',
        hasConversationIdFromResponse: true,
      });
      expect(type).toBe(ThreadType.SERVICE_MANAGED);
    });
  });

  describe('LOCAL_MANAGED detection', () => {
    it('should return LOCAL_MANAGED with messageStoreFactory', () => {
      const type = determineThreadType({
        messageStoreFactory: () => new InMemoryMessageStore(),
      });
      expect(type).toBe(ThreadType.LOCAL_MANAGED);
    });

    it('should return LOCAL_MANAGED with custom message store factory', () => {
      const customFactory = () => new InMemoryMessageStore();
      const type = determineThreadType({
        messageStoreFactory: customFactory,
      });
      expect(type).toBe(ThreadType.LOCAL_MANAGED);
    });
  });

  describe('UNDETERMINED detection', () => {
    it('should return UNDETERMINED with empty options', () => {
      const type = determineThreadType({});
      expect(type).toBe(ThreadType.UNDETERMINED);
    });

    it('should return UNDETERMINED with hasConversationIdFromResponse false', () => {
      const type = determineThreadType({
        hasConversationIdFromResponse: false,
      });
      expect(type).toBe(ThreadType.UNDETERMINED);
    });

    it('should return UNDETERMINED with all undefined', () => {
      const type = determineThreadType({
        conversationId: undefined,
        messageStoreFactory: undefined,
        hasConversationIdFromResponse: undefined,
      });
      expect(type).toBe(ThreadType.UNDETERMINED);
    });
  });

  describe('edge cases', () => {
    it('should handle empty string conversationId as falsy', () => {
      const type = determineThreadType({
        conversationId: '',
      });
      // Empty string is falsy in JavaScript, so should be UNDETERMINED
      expect(type).toBe(ThreadType.UNDETERMINED);
    });

    it('should handle whitespace-only conversationId', () => {
      const type = determineThreadType({
        conversationId: '   ',
      });
      // Whitespace string is truthy, should be SERVICE_MANAGED
      expect(type).toBe(ThreadType.SERVICE_MANAGED);
    });
  });
});

describe('Type guards', () => {
  describe('isServiceManaged', () => {
    it('should return true for SERVICE_MANAGED', () => {
      expect(isServiceManaged(ThreadType.SERVICE_MANAGED)).toBe(true);
    });

    it('should return false for LOCAL_MANAGED', () => {
      expect(isServiceManaged(ThreadType.LOCAL_MANAGED)).toBe(false);
    });

    it('should return false for UNDETERMINED', () => {
      expect(isServiceManaged(ThreadType.UNDETERMINED)).toBe(false);
    });
  });

  describe('isLocalManaged', () => {
    it('should return true for LOCAL_MANAGED', () => {
      expect(isLocalManaged(ThreadType.LOCAL_MANAGED)).toBe(true);
    });

    it('should return false for SERVICE_MANAGED', () => {
      expect(isLocalManaged(ThreadType.SERVICE_MANAGED)).toBe(false);
    });

    it('should return false for UNDETERMINED', () => {
      expect(isLocalManaged(ThreadType.UNDETERMINED)).toBe(false);
    });
  });

  describe('isUndetermined', () => {
    it('should return true for UNDETERMINED', () => {
      expect(isUndetermined(ThreadType.UNDETERMINED)).toBe(true);
    });

    it('should return false for SERVICE_MANAGED', () => {
      expect(isUndetermined(ThreadType.SERVICE_MANAGED)).toBe(false);
    });

    it('should return false for LOCAL_MANAGED', () => {
      expect(isUndetermined(ThreadType.LOCAL_MANAGED)).toBe(false);
    });
  });

  describe('type guard integration with determineThreadType', () => {
    it('should correctly identify service-managed thread', () => {
      const type = determineThreadType({ conversationId: 'thread-123' });
      expect(isServiceManaged(type)).toBe(true);
      expect(isLocalManaged(type)).toBe(false);
      expect(isUndetermined(type)).toBe(false);
    });

    it('should correctly identify local-managed thread', () => {
      const type = determineThreadType({
        messageStoreFactory: () => new InMemoryMessageStore(),
      });
      expect(isServiceManaged(type)).toBe(false);
      expect(isLocalManaged(type)).toBe(true);
      expect(isUndetermined(type)).toBe(false);
    });

    it('should correctly identify undetermined thread', () => {
      const type = determineThreadType({});
      expect(isServiceManaged(type)).toBe(false);
      expect(isLocalManaged(type)).toBe(false);
      expect(isUndetermined(type)).toBe(true);
    });
  });
});

describe('Integration scenarios', () => {
  it('should support typical service-managed workflow', () => {
    // Agent configured with conversation ID
    const options = { conversationId: 'thread-abc123' };

    // Validation passes
    expect(() => validateThreadOptions(options)).not.toThrow();

    // Type is determined as service-managed
    const type = determineThreadType(options);
    expect(type).toBe(ThreadType.SERVICE_MANAGED);
    expect(isServiceManaged(type)).toBe(true);
  });

  it('should support typical local-managed workflow', () => {
    // Agent configured with message store factory
    const options = {
      messageStoreFactory: () => new InMemoryMessageStore(),
    };

    // Validation passes
    expect(() => validateThreadOptions(options)).not.toThrow();

    // Type is determined as local-managed
    const type = determineThreadType(options);
    expect(type).toBe(ThreadType.LOCAL_MANAGED);
    expect(isLocalManaged(type)).toBe(true);
  });

  it('should support undetermined to service-managed transition', () => {
    // Initial undetermined state
    const initialOptions = {};
    expect(() => validateThreadOptions(initialOptions)).not.toThrow();

    let type = determineThreadType(initialOptions);
    expect(type).toBe(ThreadType.UNDETERMINED);
    expect(isUndetermined(type)).toBe(true);

    // After receiving conversation ID from service
    const updatedOptions = {
      hasConversationIdFromResponse: true,
    };
    type = determineThreadType(updatedOptions);
    expect(type).toBe(ThreadType.SERVICE_MANAGED);
    expect(isServiceManaged(type)).toBe(true);
  });

  it('should prevent mixing thread management strategies', () => {
    const options = {
      conversationId: 'thread-123',
      messageStoreFactory: () => new InMemoryMessageStore(),
    };

    // Validation fails
    expect(() => validateThreadOptions(options)).toThrow(AgentInitializationError);

    // But determination still works (prioritizes service-managed)
    const type = determineThreadType(options);
    expect(type).toBe(ThreadType.SERVICE_MANAGED);
  });
});
