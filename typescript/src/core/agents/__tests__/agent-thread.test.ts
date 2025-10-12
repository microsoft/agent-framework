/**
 * Tests for AgentThread class.
 *
 * These tests verify the AgentThread implementation including:
 * - Service-managed thread creation and usage
 * - Local-managed thread creation and usage
 * - Serialization and deserialization for both modes
 * - Mixed mode prevention (validation)
 * - Edge cases and error handling
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { AgentThread } from '../agent-thread';
import { InMemoryMessageStore } from '../../storage/in-memory-store';
import { createUserMessage, createAssistantMessage, MessageRole } from '../../types/chat-message';
import { AgentThreadError } from '../../errors/agent-errors';

describe('AgentThread', () => {
  describe('Constructor', () => {
    it('should create an uninitialized thread with no options', () => {
      const thread = new AgentThread({});

      expect(thread.serviceThreadId).toBeUndefined();
      expect(thread.messageStore).toBeUndefined();
      expect(thread.isInitialized).toBe(false);
      expect(thread.isServiceManaged).toBe(false);
      expect(thread.isLocalManaged).toBe(false);
      expect(thread.threadId).toBeTruthy();
    });

    it('should create a service-managed thread with serviceThreadId', () => {
      const thread = new AgentThread({ serviceThreadId: 'thread_123' });

      expect(thread.serviceThreadId).toBe('thread_123');
      expect(thread.messageStore).toBeUndefined();
      expect(thread.isInitialized).toBe(true);
      expect(thread.isServiceManaged).toBe(true);
      expect(thread.isLocalManaged).toBe(false);
    });

    it('should create a local-managed thread with messageStore', () => {
      const store = new InMemoryMessageStore();
      const thread = new AgentThread({ messageStore: store });

      expect(thread.serviceThreadId).toBeUndefined();
      expect(thread.messageStore).toBe(store);
      expect(thread.isInitialized).toBe(true);
      expect(thread.isServiceManaged).toBe(false);
      expect(thread.isLocalManaged).toBe(true);
    });

    it('should throw error when both serviceThreadId and messageStore are provided', () => {
      const store = new InMemoryMessageStore();

      expect(() => {
        new AgentThread({ serviceThreadId: 'thread_123', messageStore: store });
      }).toThrow(AgentThreadError);

      expect(() => {
        new AgentThread({ serviceThreadId: 'thread_123', messageStore: store });
      }).toThrow(/Cannot specify both serviceThreadId and messageStore/);
    });
  });

  describe('Property Setters', () => {
    it('should allow setting serviceThreadId on uninitialized thread', () => {
      const thread = new AgentThread({});
      thread.serviceThreadId = 'thread_456';

      expect(thread.serviceThreadId).toBe('thread_456');
      expect(thread.isServiceManaged).toBe(true);
    });

    it('should allow setting messageStore on uninitialized thread', () => {
      const thread = new AgentThread({});
      const store = new InMemoryMessageStore();
      thread.messageStore = store;

      expect(thread.messageStore).toBe(store);
      expect(thread.isLocalManaged).toBe(true);
    });

    it('should throw error when setting messageStore after serviceThreadId is set', () => {
      const thread = new AgentThread({ serviceThreadId: 'thread_123' });
      const store = new InMemoryMessageStore();

      expect(() => {
        thread.messageStore = store;
      }).toThrow(AgentThreadError);

      expect(() => {
        thread.messageStore = store;
      }).toThrow(/Cannot set messageStore when serviceThreadId is already set/);
    });

    it('should throw error when setting serviceThreadId after messageStore is set', () => {
      const store = new InMemoryMessageStore();
      const thread = new AgentThread({ messageStore: store });

      expect(() => {
        thread.serviceThreadId = 'thread_123';
      }).toThrow(AgentThreadError);

      expect(() => {
        thread.serviceThreadId = 'thread_123';
      }).toThrow(/Cannot set serviceThreadId when messageStore is already set/);
    });

    it('should allow setting serviceThreadId to undefined', () => {
      const thread = new AgentThread({ serviceThreadId: 'thread_123' });
      thread.serviceThreadId = undefined;

      expect(thread.serviceThreadId).toBe('thread_123'); // Should remain unchanged
    });

    it('should allow setting messageStore to undefined', () => {
      const store = new InMemoryMessageStore();
      const thread = new AgentThread({ messageStore: store });
      thread.messageStore = undefined;

      expect(thread.messageStore).toBe(store); // Should remain unchanged
    });
  });

  describe('Service-Managed Thread Operations', () => {
    let thread: AgentThread;

    beforeEach(() => {
      thread = new AgentThread({ serviceThreadId: 'thread_service_123' });
    });

    it('should not store messages locally for service-managed threads', async () => {
      const message = createUserMessage('Hello');
      await thread.onNewMessages([message]);

      // Service-managed threads don't store messages locally
      expect(thread.messageStore).toBeUndefined();
      const messages = await thread.getMessages();
      expect(messages).toEqual([]);
    });

    it('should handle single message', async () => {
      const message = createUserMessage('Hello');
      await thread.onNewMessages(message);

      // Should not throw, but also shouldn't store
      expect(thread.messageStore).toBeUndefined();
    });

    it('should handle multiple messages', async () => {
      const messages = [createUserMessage('Hello'), createAssistantMessage('Hi there')];
      await thread.onNewMessages(messages);

      // Should not throw, but also shouldn't store
      expect(thread.messageStore).toBeUndefined();
    });
  });

  describe('Local-Managed Thread Operations', () => {
    let thread: AgentThread;
    let store: InMemoryMessageStore;

    beforeEach(() => {
      store = new InMemoryMessageStore();
      thread = new AgentThread({ messageStore: store });
    });

    it('should store messages in local store', async () => {
      const message = createUserMessage('Hello');
      await thread.onNewMessages([message]);

      const messages = await thread.getMessages();
      expect(messages).toHaveLength(1);
      expect(messages[0].role).toBe(MessageRole.User);
    });

    it('should store multiple messages', async () => {
      const messages = [createUserMessage('Hello'), createAssistantMessage('Hi there'), createUserMessage('How are you?')];

      await thread.onNewMessages(messages);

      const stored = await thread.getMessages();
      expect(stored).toHaveLength(3);
      expect(stored[0].role).toBe(MessageRole.User);
      expect(stored[1].role).toBe(MessageRole.Assistant);
      expect(stored[2].role).toBe(MessageRole.User);
    });

    it('should handle single message (not array)', async () => {
      const message = createUserMessage('Hello');
      await thread.onNewMessages(message);

      const messages = await thread.getMessages();
      expect(messages).toHaveLength(1);
    });

    it('should accumulate messages across multiple calls', async () => {
      await thread.onNewMessages(createUserMessage('First'));
      await thread.onNewMessages(createAssistantMessage('Second'));
      await thread.onNewMessages(createUserMessage('Third'));

      const messages = await thread.getMessages();
      expect(messages).toHaveLength(3);
    });

    it('should clear all messages from thread', async () => {
      await thread.onNewMessages([createUserMessage('Hello'), createAssistantMessage('Hi')]);

      let messages = await thread.getMessages();
      expect(messages).toHaveLength(2);

      await thread.clear();

      messages = await thread.getMessages();
      expect(messages).toHaveLength(0);
    });
  });

  describe('Uninitialized Thread Operations', () => {
    it('should create default in-memory store when adding messages to uninitialized thread', async () => {
      const thread = new AgentThread({});
      expect(thread.messageStore).toBeUndefined();

      const message = createUserMessage('Hello');
      await thread.onNewMessages([message]);

      // Should now have a message store
      expect(thread.messageStore).toBeDefined();
      expect(thread.isLocalManaged).toBe(true);

      const messages = await thread.getMessages();
      expect(messages).toHaveLength(1);
    });

    it('should return empty array for getMessages on uninitialized thread', async () => {
      const thread = new AgentThread({});
      const messages = await thread.getMessages();
      expect(messages).toEqual([]);
    });
  });

  describe('Serialization', () => {
    describe('Service-Managed Thread', () => {
      it('should serialize service-managed thread with serviceThreadId', async () => {
        const thread = new AgentThread({ serviceThreadId: 'thread_123' });
        const state = await thread.serialize();

        expect(state.serviceThreadId).toBe('thread_123');
        expect(state.messageStoreState).toBeUndefined();
      });

      it('should serialize correctly even with messages added (no-op)', async () => {
        const thread = new AgentThread({ serviceThreadId: 'thread_123' });
        await thread.onNewMessages(createUserMessage('Hello'));

        const state = await thread.serialize();

        expect(state.serviceThreadId).toBe('thread_123');
        expect(state.messageStoreState).toBeUndefined();
      });
    });

    describe('Local-Managed Thread', () => {
      it('should serialize local-managed thread with empty message store', async () => {
        const store = new InMemoryMessageStore();
        const thread = new AgentThread({ messageStore: store });

        const state = await thread.serialize();

        expect(state.serviceThreadId).toBeUndefined();
        expect(state.messageStoreState).toBeDefined();
        expect(state.messageStoreState?.messages).toEqual([]);
      });

      it('should serialize local-managed thread with messages', async () => {
        const store = new InMemoryMessageStore();
        const thread = new AgentThread({ messageStore: store });

        const msg1 = createUserMessage('Hello');
        const msg2 = createAssistantMessage('Hi there');
        await thread.onNewMessages([msg1, msg2]);

        const state = await thread.serialize();

        expect(state.serviceThreadId).toBeUndefined();
        expect(state.messageStoreState).toBeDefined();
        expect(state.messageStoreState?.messages).toHaveLength(2);
        expect(state.messageStoreState?.messages[0].role).toBe(MessageRole.User);
        expect(state.messageStoreState?.messages[1].role).toBe(MessageRole.Assistant);
      });
    });

    describe('Uninitialized Thread', () => {
      it('should serialize uninitialized thread to empty state', async () => {
        const thread = new AgentThread({});
        const state = await thread.serialize();

        expect(state.serviceThreadId).toBeUndefined();
        expect(state.messageStoreState).toBeUndefined();
      });
    });
  });

  describe('Deserialization', () => {
    describe('Service-Managed Thread', () => {
      it('should deserialize service-managed thread from state', async () => {
        const state = { serviceThreadId: 'thread_123' };
        const thread = await AgentThread.deserialize(state);

        expect(thread.serviceThreadId).toBe('thread_123');
        expect(thread.messageStore).toBeUndefined();
        expect(thread.isServiceManaged).toBe(true);
      });
    });

    describe('Local-Managed Thread', () => {
      it('should deserialize local-managed thread with empty messages', async () => {
        const state = { messageStoreState: { messages: [] } };
        const thread = await AgentThread.deserialize(state);

        expect(thread.serviceThreadId).toBeUndefined();
        expect(thread.messageStore).toBeDefined();
        expect(thread.isLocalManaged).toBe(true);

        const messages = await thread.getMessages();
        expect(messages).toEqual([]);
      });

      it('should deserialize local-managed thread with messages', async () => {
        const msg1 = createUserMessage('Hello');
        const msg2 = createAssistantMessage('Hi there');
        const state = {
          messageStoreState: {
            messages: [msg1, msg2],
          },
        };

        const thread = await AgentThread.deserialize(state);

        expect(thread.isLocalManaged).toBe(true);

        const messages = await thread.getMessages();
        expect(messages).toHaveLength(2);
        expect(messages[0].role).toBe(MessageRole.User);
        expect(messages[1].role).toBe(MessageRole.Assistant);
      });

      it('should deserialize with custom message store', async () => {
        const customStore = new InMemoryMessageStore();
        const msg = createUserMessage('Hello');
        const state = {
          messageStoreState: {
            messages: [msg],
          },
        };

        const thread = await AgentThread.deserialize(state, customStore);

        expect(thread.messageStore).toBe(customStore);

        const messages = await thread.getMessages();
        expect(messages).toHaveLength(1);
      });
    });

    describe('Uninitialized Thread', () => {
      it('should deserialize empty state to uninitialized thread', async () => {
        const state = {};
        const thread = await AgentThread.deserialize(state);

        expect(thread.serviceThreadId).toBeUndefined();
        expect(thread.messageStore).toBeUndefined();
        expect(thread.isInitialized).toBe(false);
      });
    });

    describe('Invalid State', () => {
      it('should throw error when state has both serviceThreadId and messageStoreState', async () => {
        const state = {
          serviceThreadId: 'thread_123',
          messageStoreState: { messages: [] },
        };

        await expect(AgentThread.deserialize(state)).rejects.toThrow(AgentThreadError);
        await expect(AgentThread.deserialize(state)).rejects.toThrow(
          /Invalid thread state: cannot have both serviceThreadId and messageStoreState/,
        );
      });
    });
  });

  describe('Round-Trip Serialization', () => {
    it('should round-trip service-managed thread', async () => {
      const original = new AgentThread({ serviceThreadId: 'thread_xyz' });
      const state = await original.serialize();
      const restored = await AgentThread.deserialize(state);

      expect(restored.serviceThreadId).toBe(original.serviceThreadId);
      expect(restored.isServiceManaged).toBe(true);
    });

    it('should round-trip local-managed thread with messages', async () => {
      const store = new InMemoryMessageStore();
      const original = new AgentThread({ messageStore: store });

      await original.onNewMessages([createUserMessage('Hello'), createAssistantMessage('Hi there')]);

      const state = await original.serialize();
      const restored = await AgentThread.deserialize(state);

      expect(restored.isLocalManaged).toBe(true);

      const messages = await restored.getMessages();
      expect(messages).toHaveLength(2);
      expect(messages[0].role).toBe(MessageRole.User);
      expect(messages[1].role).toBe(MessageRole.Assistant);
    });

    it('should round-trip uninitialized thread', async () => {
      const original = new AgentThread({});
      const state = await original.serialize();
      const restored = await AgentThread.deserialize(state);

      expect(restored.isInitialized).toBe(false);
    });
  });

  describe('updateFromState', () => {
    it('should update uninitialized thread with service thread ID', async () => {
      const thread = new AgentThread({});
      const state = { serviceThreadId: 'thread_123' };

      await thread.updateFromState(state);

      expect(thread.serviceThreadId).toBe('thread_123');
      expect(thread.isServiceManaged).toBe(true);
    });

    it('should update uninitialized thread with messages', async () => {
      const thread = new AgentThread({});
      const msg = createUserMessage('Hello');
      const state = { messageStoreState: { messages: [msg] } };

      await thread.updateFromState(state);

      expect(thread.isLocalManaged).toBe(true);

      const messages = await thread.getMessages();
      expect(messages).toHaveLength(1);
      expect(messages[0].role).toBe(MessageRole.User);
    });

    it('should throw error when state has both serviceThreadId and messageStoreState', async () => {
      const thread = new AgentThread({});
      const state = {
        serviceThreadId: 'thread_123',
        messageStoreState: { messages: [] },
      };

      await expect(thread.updateFromState(state)).rejects.toThrow(AgentThreadError);
      await expect(thread.updateFromState(state)).rejects.toThrow(
        /Invalid thread state: cannot have both serviceThreadId and messageStoreState/,
      );
    });

    it('should throw error when trying to update service-managed thread with message store', async () => {
      const thread = new AgentThread({ serviceThreadId: 'thread_123' });
      const state = { messageStoreState: { messages: [createUserMessage('Hello')] } };

      await expect(thread.updateFromState(state)).rejects.toThrow(AgentThreadError);
    });

    it('should throw error when trying to update local-managed thread with service thread ID', async () => {
      const store = new InMemoryMessageStore();
      const thread = new AgentThread({ messageStore: store });
      const state = { serviceThreadId: 'thread_123' };

      await expect(thread.updateFromState(state)).rejects.toThrow(AgentThreadError);
    });

    it('should add messages to existing local store', async () => {
      const store = new InMemoryMessageStore();
      const thread = new AgentThread({ messageStore: store });

      await thread.onNewMessages(createUserMessage('First'));

      const state = {
        messageStoreState: {
          messages: [createUserMessage('Second')],
        },
      };

      await thread.updateFromState(state);

      const messages = await thread.getMessages();
      expect(messages).toHaveLength(2);
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty message array', async () => {
      const store = new InMemoryMessageStore();
      const thread = new AgentThread({ messageStore: store });

      await thread.onNewMessages([]);

      const messages = await thread.getMessages();
      expect(messages).toEqual([]);
    });

    it('should generate unique thread IDs', () => {
      const thread1 = new AgentThread({});
      const thread2 = new AgentThread({});

      expect(thread1.threadId).not.toBe(thread2.threadId);
    });

    it('should handle clear on service-managed thread (no-op)', async () => {
      const thread = new AgentThread({ serviceThreadId: 'thread_123' });
      await thread.clear(); // Should not throw
      expect(thread.messageStore).toBeUndefined();
    });

    it('should handle clear on uninitialized thread (no-op)', async () => {
      const thread = new AgentThread({});
      await thread.clear(); // Should not throw
      expect(thread.messageStore).toBeUndefined();
    });
  });
});
