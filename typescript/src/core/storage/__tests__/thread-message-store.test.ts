/**
 * Tests for thread-local message store implementations.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  ChatMessageStore,
  InMemoryMessageStore,
  createDefaultMessageStore,
  LocalThreadOptions,
} from '../thread-message-store';
import { ChatMessage, MessageRole } from '../../types/chat-message';

describe('InMemoryMessageStore', () => {
  let store: InMemoryMessageStore;

  beforeEach(() => {
    store = new InMemoryMessageStore();
  });

  describe('addMessage', () => {
    it('should add a message to the store', () => {
      const message: ChatMessage = {
        role: MessageRole.User,
        content: 'Hello, world!',
      };

      store.addMessage(message);
      const messages = store.getMessages();

      expect(messages).toHaveLength(1);
      expect(messages[0]).toEqual(message);
    });

    it('should add multiple messages in order', () => {
      const message1: ChatMessage = {
        role: MessageRole.User,
        content: 'First message',
      };
      const message2: ChatMessage = {
        role: MessageRole.Assistant,
        content: 'Second message',
      };
      const message3: ChatMessage = {
        role: MessageRole.User,
        content: 'Third message',
      };

      store.addMessage(message1);
      store.addMessage(message2);
      store.addMessage(message3);

      const messages = store.getMessages();
      expect(messages).toHaveLength(3);
      expect(messages[0]).toEqual(message1);
      expect(messages[1]).toEqual(message2);
      expect(messages[2]).toEqual(message3);
    });

    it('should handle messages with metadata', () => {
      const message: ChatMessage = {
        role: MessageRole.User,
        content: 'Message with metadata',
        metadata: {
          customField: 'custom value',
          timestamp: new Date(),
        },
      };

      store.addMessage(message);
      const messages = store.getMessages();

      expect(messages).toHaveLength(1);
      expect(messages[0].metadata).toEqual(message.metadata);
    });

    it('should handle tool messages', () => {
      const message: ChatMessage = {
        role: MessageRole.Tool,
        content: 'Tool result',
        toolCallId: 'call_123',
      };

      store.addMessage(message);
      const messages = store.getMessages();

      expect(messages).toHaveLength(1);
      expect(messages[0].toolCallId).toBe('call_123');
    });
  });

  describe('getMessages', () => {
    it('should return empty array when store is empty', () => {
      const messages = store.getMessages();
      expect(messages).toEqual([]);
    });

    it('should return all messages', () => {
      store.addMessage({ role: MessageRole.User, content: 'Message 1' });
      store.addMessage({ role: MessageRole.Assistant, content: 'Message 2' });
      store.addMessage({ role: MessageRole.User, content: 'Message 3' });

      const messages = store.getMessages();
      expect(messages).toHaveLength(3);
    });

    it('should return a copy of messages array (not reference)', () => {
      store.addMessage({ role: MessageRole.User, content: 'Original' });

      const messages1 = store.getMessages();
      const messages2 = store.getMessages();

      expect(messages1).not.toBe(messages2); // Different array instances
      expect(messages1).toEqual(messages2); // But same content

      // Mutating returned array should not affect store
      messages1.push({ role: MessageRole.User, content: 'Mutated' });
      expect(store.size()).toBe(1); // Store still has only 1 message
    });

    it('should maintain chronological order', () => {
      const message1: ChatMessage = {
        role: MessageRole.User,
        content: 'First',
        timestamp: new Date('2024-01-01T10:00:00Z'),
      };
      const message2: ChatMessage = {
        role: MessageRole.Assistant,
        content: 'Second',
        timestamp: new Date('2024-01-01T10:01:00Z'),
      };
      const message3: ChatMessage = {
        role: MessageRole.User,
        content: 'Third',
        timestamp: new Date('2024-01-01T10:02:00Z'),
      };

      store.addMessage(message1);
      store.addMessage(message2);
      store.addMessage(message3);

      const messages = store.getMessages();
      expect(messages[0].content).toBe('First');
      expect(messages[1].content).toBe('Second');
      expect(messages[2].content).toBe('Third');
    });
  });

  describe('clear', () => {
    it('should remove all messages from the store', () => {
      store.addMessage({ role: MessageRole.User, content: 'Message 1' });
      store.addMessage({ role: MessageRole.Assistant, content: 'Message 2' });
      store.addMessage({ role: MessageRole.User, content: 'Message 3' });

      expect(store.size()).toBe(3);

      store.clear();

      expect(store.size()).toBe(0);
      expect(store.getMessages()).toEqual([]);
    });

    it('should allow adding messages after clearing', () => {
      store.addMessage({ role: MessageRole.User, content: 'Before clear' });
      store.clear();
      store.addMessage({ role: MessageRole.User, content: 'After clear' });

      const messages = store.getMessages();
      expect(messages).toHaveLength(1);
      expect(messages[0].content).toBe('After clear');
    });

    it('should be idempotent (safe to call multiple times)', () => {
      store.addMessage({ role: MessageRole.User, content: 'Message' });
      store.clear();
      store.clear();
      store.clear();

      expect(store.size()).toBe(0);
      expect(store.getMessages()).toEqual([]);
    });
  });

  describe('size', () => {
    it('should return 0 for empty store', () => {
      expect(store.size()).toBe(0);
    });

    it('should return correct count after adding messages', () => {
      expect(store.size()).toBe(0);

      store.addMessage({ role: MessageRole.User, content: 'Message 1' });
      expect(store.size()).toBe(1);

      store.addMessage({ role: MessageRole.Assistant, content: 'Message 2' });
      expect(store.size()).toBe(2);

      store.addMessage({ role: MessageRole.User, content: 'Message 3' });
      expect(store.size()).toBe(3);
    });

    it('should return 0 after clearing', () => {
      store.addMessage({ role: MessageRole.User, content: 'Message 1' });
      store.addMessage({ role: MessageRole.Assistant, content: 'Message 2' });
      expect(store.size()).toBe(2);

      store.clear();
      expect(store.size()).toBe(0);
    });
  });

  describe('ChatMessageStore interface compatibility', () => {
    it('should implement ChatMessageStore interface', () => {
      const chatStore: ChatMessageStore = new InMemoryMessageStore();

      // Test that all methods are available
      expect(typeof chatStore.addMessage).toBe('function');
      expect(typeof chatStore.getMessages).toBe('function');
      expect(typeof chatStore.clear).toBe('function');
      expect(typeof chatStore.size).toBe('function');
    });

    it('should work with interface type', () => {
      const createStore = (): ChatMessageStore => new InMemoryMessageStore();

      const chatStore = createStore();
      chatStore.addMessage({ role: MessageRole.User, content: 'Test' });

      expect(chatStore.size()).toBe(1);
    });
  });
});

describe('createDefaultMessageStore', () => {
  it('should create a new InMemoryMessageStore instance', () => {
    const store = createDefaultMessageStore();
    expect(store).toBeInstanceOf(InMemoryMessageStore);
  });

  it('should create independent store instances', () => {
    const store1 = createDefaultMessageStore();
    const store2 = createDefaultMessageStore();

    store1.addMessage({ role: MessageRole.User, content: 'Store 1' });
    store2.addMessage({ role: MessageRole.User, content: 'Store 2' });

    expect(store1.size()).toBe(1);
    expect(store2.size()).toBe(1);
    expect(store1.getMessages()[0].content).toBe('Store 1');
    expect(store2.getMessages()[0].content).toBe('Store 2');
  });

  it('should work as a factory function', () => {
    const factory = createDefaultMessageStore;
    const store = factory();

    store.addMessage({ role: MessageRole.User, content: 'From factory' });
    expect(store.size()).toBe(1);
  });
});

describe('Thread isolation', () => {
  it('should maintain separate message stores for different threads', () => {
    const thread1Store = new InMemoryMessageStore();
    const thread2Store = new InMemoryMessageStore();

    // Add messages to thread 1
    thread1Store.addMessage({ role: MessageRole.User, content: 'Thread 1 - Message 1' });
    thread1Store.addMessage({ role: MessageRole.Assistant, content: 'Thread 1 - Message 2' });

    // Add messages to thread 2
    thread2Store.addMessage({ role: MessageRole.User, content: 'Thread 2 - Message 1' });

    // Verify isolation
    expect(thread1Store.size()).toBe(2);
    expect(thread2Store.size()).toBe(1);

    const thread1Messages = thread1Store.getMessages();
    const thread2Messages = thread2Store.getMessages();

    expect(thread1Messages[0].content).toBe('Thread 1 - Message 1');
    expect(thread2Messages[0].content).toBe('Thread 2 - Message 1');
  });

  it('should not interfere when using factory function', () => {
    const factory = createDefaultMessageStore;

    const store1 = factory();
    const store2 = factory();
    const store3 = factory();

    store1.addMessage({ role: MessageRole.User, content: 'Store 1' });
    store2.addMessage({ role: MessageRole.User, content: 'Store 2' });
    store3.addMessage({ role: MessageRole.User, content: 'Store 3' });

    expect(store1.getMessages()[0].content).toBe('Store 1');
    expect(store2.getMessages()[0].content).toBe('Store 2');
    expect(store3.getMessages()[0].content).toBe('Store 3');

    expect(store1.size()).toBe(1);
    expect(store2.size()).toBe(1);
    expect(store3.size()).toBe(1);
  });
});

describe('LocalThreadOptions', () => {
  it('should accept messageStoreFactory property', () => {
    const options: LocalThreadOptions = {
      messageStoreFactory: () => new InMemoryMessageStore(),
    };

    expect(typeof options.messageStoreFactory).toBe('function');
  });

  it('should work with createDefaultMessageStore', () => {
    const options: LocalThreadOptions = {
      messageStoreFactory: createDefaultMessageStore,
    };

    const store = options.messageStoreFactory!();
    expect(store).toBeInstanceOf(InMemoryMessageStore);
  });

  it('should be optional (all fields optional)', () => {
    const options1: LocalThreadOptions = {};
    const options2: LocalThreadOptions = {
      messageStoreFactory: undefined,
    };

    expect(options1.messageStoreFactory).toBeUndefined();
    expect(options2.messageStoreFactory).toBeUndefined();
  });

  it('should work with custom factory implementations', () => {
    class CustomMessageStore implements ChatMessageStore {
      private messages: ChatMessage[] = [];

      addMessage(message: ChatMessage): void {
        this.messages.push({ ...message, metadata: { ...message.metadata, custom: true } });
      }

      getMessages(): ChatMessage[] {
        return [...this.messages];
      }

      clear(): void {
        this.messages = [];
      }

      size(): number {
        return this.messages.length;
      }
    }

    const options: LocalThreadOptions = {
      messageStoreFactory: () => new CustomMessageStore(),
    };

    const store = options.messageStoreFactory!();
    store.addMessage({ role: MessageRole.User, content: 'Test' });

    const messages = store.getMessages();
    expect(messages[0].metadata?.custom).toBe(true);
  });
});

describe('Async compatibility', () => {
  it('should work with async/await even though implementation is sync', async () => {
    const store = new InMemoryMessageStore();

    await store.addMessage({ role: MessageRole.User, content: 'Async test' });
    const messages = await store.getMessages();
    await store.clear();
    const size = await store.size();

    expect(messages).toHaveLength(1);
    expect(size).toBe(0);
  });

  it('should support Promise.all for batch operations', async () => {
    const store = new InMemoryMessageStore();

    await Promise.all([
      store.addMessage({ role: MessageRole.User, content: 'Message 1' }),
      store.addMessage({ role: MessageRole.Assistant, content: 'Message 2' }),
      store.addMessage({ role: MessageRole.User, content: 'Message 3' }),
    ]);

    const size = await store.size();
    expect(size).toBe(3);
  });
});

describe('Edge cases', () => {
  let store: InMemoryMessageStore;

  beforeEach(() => {
    store = new InMemoryMessageStore();
  });

  it('should handle messages with empty content', () => {
    store.addMessage({ role: MessageRole.User, content: '' });
    expect(store.size()).toBe(1);
    expect(store.getMessages()[0].content).toBe('');
  });

  it('should handle messages with complex content', () => {
    const complexContent = [
      { type: 'text' as const, text: 'Hello' },
      { type: 'text' as const, text: 'World' },
    ];

    store.addMessage({
      role: MessageRole.User,
      content: complexContent,
    });

    const messages = store.getMessages();
    expect(messages[0].content).toEqual(complexContent);
  });

  it('should handle large number of messages', () => {
    const messageCount = 10000;

    for (let i = 0; i < messageCount; i++) {
      store.addMessage({
        role: i % 2 === 0 ? MessageRole.User : MessageRole.Assistant,
        content: `Message ${i}`,
      });
    }

    expect(store.size()).toBe(messageCount);
    const messages = store.getMessages();
    expect(messages).toHaveLength(messageCount);
    expect(messages[0].content).toBe('Message 0');
    expect(messages[messageCount - 1].content).toBe(`Message ${messageCount - 1}`);
  });

  it('should preserve message references correctly', () => {
    const metadata = { customId: 'test-123' };
    const message: ChatMessage = {
      role: MessageRole.User,
      content: 'Test',
      metadata,
    };

    store.addMessage(message);
    const retrieved = store.getMessages()[0];

    // The message should be stored, but getMessages returns a copy of the array
    expect(retrieved.metadata).toEqual(metadata);
    expect(retrieved.metadata).toBe(metadata); // Same reference for nested objects
  });
});
