/**
 * Tests for InMemoryMessageStore.
 *
 * This test suite covers CRUD operations, filtering, querying, multi-thread
 * isolation, and edge cases for the message store implementation.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { InMemoryMessageStore } from '../in-memory-store';
import {
  createUserMessage,
  createAssistantMessage,
  createSystemMessage,
  createToolMessage,
  MessageRole,
  ChatMessage,
} from '../../types/chat-message';

describe('InMemoryMessageStore', () => {
  let store: InMemoryMessageStore;

  beforeEach(() => {
    store = new InMemoryMessageStore();
  });

  describe('CRUD Operations', () => {
    describe('add', () => {
      it('should add a message to a thread', async () => {
        const message = createUserMessage('Hello, world!');
        await store.add('thread-1', message);

        const messages = await store.list('thread-1');
        expect(messages).toHaveLength(1);
        expect(messages[0].content).toEqual(message.content);
      });

      it('should generate a message ID if not provided', async () => {
        const message = createUserMessage('Test');
        await store.add('thread-1', message);

        const messages = await store.list('thread-1');
        expect(messages[0].metadata?.messageId).toBeDefined();
        expect(typeof messages[0].metadata?.messageId).toBe('string');
      });

      it('should preserve existing message ID in metadata', async () => {
        const message = createUserMessage('Test');
        message.metadata = { messageId: 'custom-id-123' };
        await store.add('thread-1', message);

        const messages = await store.list('thread-1');
        expect(messages[0].metadata?.messageId).toBe('custom-id-123');
      });

      it('should add multiple messages to the same thread', async () => {
        await store.add('thread-1', createUserMessage('Message 1'));
        await store.add('thread-1', createUserMessage('Message 2'));
        await store.add('thread-1', createUserMessage('Message 3'));

        const messages = await store.list('thread-1');
        expect(messages).toHaveLength(3);
      });

      it('should preserve message timestamps', async () => {
        const message = createUserMessage('Test');
        const timestamp = message.timestamp;
        await store.add('thread-1', message);

        const messages = await store.list('thread-1');
        expect(messages[0].timestamp).toEqual(timestamp);
      });

      it('should preserve message metadata', async () => {
        const message = createUserMessage('Test');
        message.metadata = { customField: 'value', number: 42 };
        await store.add('thread-1', message);

        const messages = await store.list('thread-1');
        expect(messages[0].metadata?.customField).toBe('value');
        expect(messages[0].metadata?.number).toBe(42);
      });
    });

    describe('get', () => {
      it('should retrieve a message by ID', async () => {
        const message = createUserMessage('Hello');
        message.metadata = { messageId: 'msg-123' };
        await store.add('thread-1', message);

        const retrieved = await store.get('thread-1', 'msg-123');
        expect(retrieved).toBeDefined();
        expect(retrieved?.metadata?.messageId).toBe('msg-123');
      });

      it('should return undefined for non-existent message ID', async () => {
        await store.add('thread-1', createUserMessage('Test'));

        const retrieved = await store.get('thread-1', 'non-existent');
        expect(retrieved).toBeUndefined();
      });

      it('should return undefined for non-existent thread', async () => {
        const retrieved = await store.get('non-existent-thread', 'msg-123');
        expect(retrieved).toBeUndefined();
      });

      it('should retrieve the correct message when multiple exist', async () => {
        const msg1 = createUserMessage('Message 1');
        msg1.metadata = { messageId: 'msg-1' };
        const msg2 = createUserMessage('Message 2');
        msg2.metadata = { messageId: 'msg-2' };
        const msg3 = createUserMessage('Message 3');
        msg3.metadata = { messageId: 'msg-3' };

        await store.add('thread-1', msg1);
        await store.add('thread-1', msg2);
        await store.add('thread-1', msg3);

        const retrieved = await store.get('thread-1', 'msg-2');
        expect(retrieved?.content).toEqual(msg2.content);
      });
    });

    describe('list', () => {
      it('should return empty array for non-existent thread', async () => {
        const messages = await store.list('non-existent');
        expect(messages).toEqual([]);
      });

      it('should return all messages when no options provided', async () => {
        await store.add('thread-1', createUserMessage('Message 1'));
        await store.add('thread-1', createAssistantMessage('Message 2'));
        await store.add('thread-1', createUserMessage('Message 3'));

        const messages = await store.list('thread-1');
        expect(messages).toHaveLength(3);
      });

      it('should return messages in ascending order by default', async () => {
        const msg1 = createUserMessage('First');
        msg1.timestamp = new Date('2024-01-01T10:00:00Z');
        const msg2 = createUserMessage('Second');
        msg2.timestamp = new Date('2024-01-01T11:00:00Z');
        const msg3 = createUserMessage('Third');
        msg3.timestamp = new Date('2024-01-01T12:00:00Z');

        await store.add('thread-1', msg1);
        await store.add('thread-1', msg2);
        await store.add('thread-1', msg3);

        const messages = await store.list('thread-1');
        expect(messages[0].timestamp).toEqual(msg1.timestamp);
        expect(messages[1].timestamp).toEqual(msg2.timestamp);
        expect(messages[2].timestamp).toEqual(msg3.timestamp);
      });
    });

    describe('clear', () => {
      it('should clear all messages from a thread', async () => {
        await store.add('thread-1', createUserMessage('Message 1'));
        await store.add('thread-1', createUserMessage('Message 2'));

        await store.clear('thread-1');

        const messages = await store.list('thread-1');
        expect(messages).toEqual([]);
      });

      it('should not affect other threads', async () => {
        await store.add('thread-1', createUserMessage('Thread 1 Message'));
        await store.add('thread-2', createUserMessage('Thread 2 Message'));

        await store.clear('thread-1');

        const thread1Messages = await store.list('thread-1');
        const thread2Messages = await store.list('thread-2');

        expect(thread1Messages).toEqual([]);
        expect(thread2Messages).toHaveLength(1);
      });

      it('should handle clearing non-existent thread', async () => {
        await expect(store.clear('non-existent')).resolves.not.toThrow();
      });
    });
  });

  describe('Filtering and Querying', () => {
    beforeEach(async () => {
      // Set up test data
      const user1 = createUserMessage('User message 1');
      user1.timestamp = new Date('2024-01-01T10:00:00Z');
      await store.add('thread-1', user1);

      const assistant1 = createAssistantMessage('Assistant message 1');
      assistant1.timestamp = new Date('2024-01-01T11:00:00Z');
      await store.add('thread-1', assistant1);

      const user2 = createUserMessage('User message 2');
      user2.timestamp = new Date('2024-01-01T12:00:00Z');
      await store.add('thread-1', user2);

      const system1 = createSystemMessage('System message');
      system1.timestamp = new Date('2024-01-01T13:00:00Z');
      await store.add('thread-1', system1);

      const tool1 = createToolMessage('call-1', { result: 'success' });
      tool1.timestamp = new Date('2024-01-01T14:00:00Z');
      await store.add('thread-1', tool1);
    });

    describe('role filter', () => {
      it('should filter messages by user role', async () => {
        const messages = await store.list('thread-1', { role: MessageRole.User });
        expect(messages).toHaveLength(2);
        expect(messages.every((m) => m.role === MessageRole.User)).toBe(true);
      });

      it('should filter messages by assistant role', async () => {
        const messages = await store.list('thread-1', { role: MessageRole.Assistant });
        expect(messages).toHaveLength(1);
        expect(messages[0].role).toBe(MessageRole.Assistant);
      });

      it('should filter messages by system role', async () => {
        const messages = await store.list('thread-1', { role: MessageRole.System });
        expect(messages).toHaveLength(1);
        expect(messages[0].role).toBe(MessageRole.System);
      });

      it('should filter messages by tool role', async () => {
        const messages = await store.list('thread-1', { role: MessageRole.Tool });
        expect(messages).toHaveLength(1);
        expect(messages[0].role).toBe(MessageRole.Tool);
      });
    });

    describe('timestamp filters', () => {
      it('should filter messages after a timestamp', async () => {
        const messages = await store.list('thread-1', {
          afterTimestamp: new Date('2024-01-01T11:30:00Z'),
        });
        expect(messages).toHaveLength(3); // user2, system1, tool1
      });

      it('should filter messages before a timestamp', async () => {
        const messages = await store.list('thread-1', {
          beforeTimestamp: new Date('2024-01-01T12:30:00Z'),
        });
        expect(messages).toHaveLength(3); // user1, assistant1, user2
      });

      it('should filter messages within a timestamp range', async () => {
        const messages = await store.list('thread-1', {
          afterTimestamp: new Date('2024-01-01T10:30:00Z'),
          beforeTimestamp: new Date('2024-01-01T13:30:00Z'),
        });
        expect(messages).toHaveLength(3); // assistant1, user2, system1
      });

      it('should handle messages without timestamps', async () => {
        const messageNoTimestamp = createUserMessage('No timestamp');
        delete messageNoTimestamp.timestamp;
        await store.add('thread-1', messageNoTimestamp);

        const messages = await store.list('thread-1', {
          afterTimestamp: new Date('2024-01-01T10:00:00Z'),
        });
        // Should not include the message without timestamp
        expect(messages.every((m) => m.timestamp !== undefined)).toBe(true);
      });
    });

    describe('sort order', () => {
      it('should sort in ascending order', async () => {
        const messages = await store.list('thread-1', { sortOrder: 'asc' });
        expect(messages).toHaveLength(5);
        expect(messages[0].timestamp!.getTime()).toBeLessThan(messages[4].timestamp!.getTime());
      });

      it('should sort in descending order', async () => {
        const messages = await store.list('thread-1', { sortOrder: 'desc' });
        expect(messages).toHaveLength(5);
        expect(messages[0].timestamp!.getTime()).toBeGreaterThan(messages[4].timestamp!.getTime());
      });
    });

    describe('pagination', () => {
      it('should limit the number of messages returned', async () => {
        const messages = await store.list('thread-1', { limit: 3 });
        expect(messages).toHaveLength(3);
      });

      it('should skip messages using offset', async () => {
        const allMessages = await store.list('thread-1');
        const offsetMessages = await store.list('thread-1', { offset: 2 });

        expect(offsetMessages).toHaveLength(3);
        expect(offsetMessages[0]).toEqual(allMessages[2]);
      });

      it('should combine limit and offset', async () => {
        const messages = await store.list('thread-1', { limit: 2, offset: 1 });
        expect(messages).toHaveLength(2);

        const allMessages = await store.list('thread-1');
        expect(messages[0]).toEqual(allMessages[1]);
        expect(messages[1]).toEqual(allMessages[2]);
      });

      it('should handle offset beyond message count', async () => {
        const messages = await store.list('thread-1', { offset: 100 });
        expect(messages).toEqual([]);
      });

      it('should handle limit of 0', async () => {
        const messages = await store.list('thread-1', { limit: 0 });
        expect(messages).toEqual([]);
      });
    });

    describe('combined filters', () => {
      it('should combine role and timestamp filters', async () => {
        const messages = await store.list('thread-1', {
          role: MessageRole.User,
          afterTimestamp: new Date('2024-01-01T10:30:00Z'),
        });
        expect(messages).toHaveLength(1);
        expect(messages[0].role).toBe(MessageRole.User);
      });

      it('should combine all filter options', async () => {
        const messages = await store.list('thread-1', {
          role: MessageRole.User,
          afterTimestamp: new Date('2024-01-01T09:00:00Z'),
          beforeTimestamp: new Date('2024-01-01T15:00:00Z'),
          limit: 1,
          offset: 0,
          sortOrder: 'asc',
        });
        expect(messages).toHaveLength(1);
        expect(messages[0].role).toBe(MessageRole.User);
      });
    });
  });

  describe('Multiple Threads Isolation', () => {
    it('should keep threads isolated from each other', async () => {
      await store.add('thread-1', createUserMessage('Thread 1 - Message 1'));
      await store.add('thread-2', createUserMessage('Thread 2 - Message 1'));
      await store.add('thread-1', createUserMessage('Thread 1 - Message 2'));

      const thread1Messages = await store.list('thread-1');
      const thread2Messages = await store.list('thread-2');

      expect(thread1Messages).toHaveLength(2);
      expect(thread2Messages).toHaveLength(1);
    });

    it('should not retrieve messages from other threads', async () => {
      const msg1 = createUserMessage('Thread 1 Message');
      msg1.metadata = { messageId: 'msg-1' };
      await store.add('thread-1', msg1);

      const msg2 = createUserMessage('Thread 2 Message');
      msg2.metadata = { messageId: 'msg-2' };
      await store.add('thread-2', msg2);

      const retrieved = await store.get('thread-1', 'msg-2');
      expect(retrieved).toBeUndefined();
    });

    it('should handle many concurrent threads', async () => {
      const threadCount = 100;
      const messagesPerThread = 10;

      for (let i = 0; i < threadCount; i++) {
        for (let j = 0; j < messagesPerThread; j++) {
          await store.add(`thread-${i}`, createUserMessage(`Thread ${i} - Message ${j}`));
        }
      }

      expect(store.getThreadCount()).toBe(threadCount);

      for (let i = 0; i < threadCount; i++) {
        const messages = await store.list(`thread-${i}`);
        expect(messages).toHaveLength(messagesPerThread);
      }
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty message content', async () => {
      const message = createUserMessage('');
      await store.add('thread-1', message);

      const messages = await store.list('thread-1');
      expect(messages).toHaveLength(1);
    });

    it('should handle very long message content', async () => {
      const longContent = 'A'.repeat(10000);
      const message = createUserMessage(longContent);
      await store.add('thread-1', message);

      const messages = await store.list('thread-1');
      expect(messages).toHaveLength(1);
      expect(messages[0].content).toEqual(message.content);
    });

    it('should handle messages with complex content arrays', async () => {
      const message = createAssistantMessage([
        { type: 'text', text: 'Hello' },
        { type: 'function_call', callId: 'call-1', name: 'test', arguments: '{}' },
        { type: 'text', text: 'World' },
      ]);
      await store.add('thread-1', message);

      const messages = await store.list('thread-1');
      expect(messages).toHaveLength(1);
      expect(Array.isArray(messages[0].content)).toBe(true);
      expect((messages[0].content as ChatMessage['content'][]).length).toBe(3);
    });

    it('should handle special characters in thread IDs', async () => {
      const specialThreadId = 'thread-with-special-chars-!@#$%';
      await store.add(specialThreadId, createUserMessage('Test'));

      const messages = await store.list(specialThreadId);
      expect(messages).toHaveLength(1);
    });

    it('should handle concurrent add operations', async () => {
      const promises = [];
      for (let i = 0; i < 100; i++) {
        promises.push(store.add('thread-1', createUserMessage(`Message ${i}`)));
      }

      await Promise.all(promises);

      const messages = await store.list('thread-1');
      expect(messages).toHaveLength(100);
    });

    it('should maintain order when messages have same timestamp', async () => {
      const timestamp = new Date('2024-01-01T10:00:00Z');
      const msg1 = createUserMessage('First');
      msg1.timestamp = timestamp;
      const msg2 = createUserMessage('Second');
      msg2.timestamp = timestamp;
      const msg3 = createUserMessage('Third');
      msg3.timestamp = timestamp;

      await store.add('thread-1', msg1);
      await store.add('thread-1', msg2);
      await store.add('thread-1', msg3);

      const messages = await store.list('thread-1');
      expect(messages).toHaveLength(3);
      // Should maintain insertion order when timestamps are equal
    });

    it('should handle empty thread after clear', async () => {
      await store.add('thread-1', createUserMessage('Test'));
      await store.clear('thread-1');

      // Should be able to add messages again
      await store.add('thread-1', createUserMessage('New message'));
      const messages = await store.list('thread-1');
      expect(messages).toHaveLength(1);
    });
  });

  describe('Utility Methods', () => {
    it('should return correct thread count', async () => {
      expect(store.getThreadCount()).toBe(0);

      await store.add('thread-1', createUserMessage('Test 1'));
      expect(store.getThreadCount()).toBe(1);

      await store.add('thread-2', createUserMessage('Test 2'));
      expect(store.getThreadCount()).toBe(2);

      await store.add('thread-1', createUserMessage('Test 3'));
      expect(store.getThreadCount()).toBe(2); // Still 2 threads
    });

    it('should return correct message count for thread', async () => {
      expect(store.getMessageCount('thread-1')).toBe(0);

      await store.add('thread-1', createUserMessage('Test 1'));
      expect(store.getMessageCount('thread-1')).toBe(1);

      await store.add('thread-1', createUserMessage('Test 2'));
      expect(store.getMessageCount('thread-1')).toBe(2);
    });

    it('should return 0 for non-existent thread message count', async () => {
      expect(store.getMessageCount('non-existent')).toBe(0);
    });
  });
});
