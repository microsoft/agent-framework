import { describe, it, expect } from 'vitest';
import {
  MessageRole,
  type ChatMessage,
  type Content,
  type TextContent,
  type FunctionCallContent,
  type FunctionResultContent,
  type FunctionApprovalRequestContent,
  type FunctionApprovalResponseContent,
  type ImageContent,
  type AudioContent,
  type FileContent,
  type VectorStoreContent,
  createUserMessage,
  createAssistantMessage,
  createSystemMessage,
  createToolMessage,
  isTextContent,
  isFunctionCallContent,
  isFunctionResultContent,
  isFunctionApprovalRequest,
  isFunctionApprovalResponse,
  isImageContent,
  isAudioContent,
  isFileContent,
  isVectorStoreContent,
  getTextContent,
  getFunctionCalls,
  getFunctionResults,
  hasContent,
} from '../chat-message';

describe('MessageRole', () => {
  it('should have all required roles', () => {
    expect(MessageRole.User).toBe('user');
    expect(MessageRole.Assistant).toBe('assistant');
    expect(MessageRole.System).toBe('system');
    expect(MessageRole.Tool).toBe('tool');
  });
});

describe('Factory Functions', () => {
  describe('createUserMessage', () => {
    it('should create message with text string', () => {
      const msg = createUserMessage('Hello world');

      expect(msg.role).toBe(MessageRole.User);
      expect(msg.timestamp).toBeInstanceOf(Date);
      expect(Array.isArray(msg.content)).toBe(false);

      const content = msg.content as TextContent;
      expect(content.type).toBe('text');
      expect(content.text).toBe('Hello world');
    });

    it('should create message with content array', () => {
      const contents: Content[] = [
        { type: 'text', text: 'Hello' },
        { type: 'image', url: 'https://example.com/image.png' },
      ];
      const msg = createUserMessage(contents);

      expect(msg.role).toBe(MessageRole.User);
      expect(msg.timestamp).toBeInstanceOf(Date);
      expect(Array.isArray(msg.content)).toBe(true);
      expect(msg.content).toBe(contents);
    });

    it('should set timestamp automatically', () => {
      const before = new Date();
      const msg = createUserMessage('test');
      const after = new Date();

      expect(msg.timestamp).toBeDefined();
      expect(msg.timestamp!.getTime()).toBeGreaterThanOrEqual(before.getTime());
      expect(msg.timestamp!.getTime()).toBeLessThanOrEqual(after.getTime());
    });
  });

  describe('createAssistantMessage', () => {
    it('should create message with text string', () => {
      const msg = createAssistantMessage('How can I help?');

      expect(msg.role).toBe(MessageRole.Assistant);
      expect(msg.timestamp).toBeInstanceOf(Date);

      const content = msg.content as TextContent;
      expect(content.type).toBe('text');
      expect(content.text).toBe('How can I help?');
    });

    it('should create message with function call content', () => {
      const functionCall: FunctionCallContent = {
        type: 'function_call',
        callId: 'call_123',
        name: 'get_weather',
        arguments: JSON.stringify({ location: 'Seattle' }),
      };
      const msg = createAssistantMessage([functionCall]);

      expect(msg.role).toBe(MessageRole.Assistant);
      expect(Array.isArray(msg.content)).toBe(true);

      const contents = msg.content as Content[];
      expect(contents[0]).toBe(functionCall);
    });

    it('should set timestamp automatically', () => {
      const msg = createAssistantMessage('test');
      expect(msg.timestamp).toBeInstanceOf(Date);
    });
  });

  describe('createSystemMessage', () => {
    it('should create message with system role', () => {
      const msg = createSystemMessage('You are a helpful assistant.');

      expect(msg.role).toBe(MessageRole.System);
      expect(msg.timestamp).toBeInstanceOf(Date);

      const content = msg.content as TextContent;
      expect(content.type).toBe('text');
      expect(content.text).toBe('You are a helpful assistant.');
    });

    it('should set timestamp automatically', () => {
      const msg = createSystemMessage('test');
      expect(msg.timestamp).toBeInstanceOf(Date);
    });
  });

  describe('createToolMessage', () => {
    it('should create message with result', () => {
      const result = { temperature: 72, condition: 'sunny' };
      const msg = createToolMessage('call_123', result);

      expect(msg.role).toBe(MessageRole.Tool);
      expect(msg.timestamp).toBeInstanceOf(Date);

      const content = msg.content as FunctionResultContent;
      expect(content.type).toBe('function_result');
      expect(content.callId).toBe('call_123');
      expect(content.result).toBe(result);
      expect(content.error).toBeUndefined();
    });

    it('should create message with error', () => {
      const error = new Error('API call failed');
      const msg = createToolMessage('call_456', null, error);

      expect(msg.role).toBe(MessageRole.Tool);

      const content = msg.content as FunctionResultContent;
      expect(content.type).toBe('function_result');
      expect(content.callId).toBe('call_456');
      expect(content.result).toBeNull();
      expect(content.error).toBe(error);
    });

    it('should set timestamp automatically', () => {
      const msg = createToolMessage('call_789', { success: true });
      expect(msg.timestamp).toBeInstanceOf(Date);
    });
  });
});

describe('Type Guard Functions', () => {
  const textContent: TextContent = { type: 'text', text: 'Hello' };
  const functionCallContent: FunctionCallContent = {
    type: 'function_call',
    callId: 'call_1',
    name: 'test',
    arguments: '{}',
  };
  const functionResultContent: FunctionResultContent = {
    type: 'function_result',
    callId: 'call_1',
    result: {},
  };
  const approvalRequestContent: FunctionApprovalRequestContent = {
    type: 'function_approval_request',
    id: 'approval_1',
    functionCall: functionCallContent,
  };
  const approvalResponseContent: FunctionApprovalResponseContent = {
    type: 'function_approval_response',
    id: 'approval_1',
    approved: true,
    functionCall: functionCallContent,
  };
  const imageContent: ImageContent = {
    type: 'image',
    url: 'https://example.com/image.png',
  };
  const audioContent: AudioContent = {
    type: 'audio',
    data: Buffer.from('audio data'),
    format: 'mp3',
  };
  const fileContent: FileContent = {
    type: 'file',
    fileId: 'file_123',
  };
  const vectorStoreContent: VectorStoreContent = {
    type: 'vector_store',
    vectorStoreId: 'vs_789',
  };

  describe('isTextContent', () => {
    it('should return true for text content', () => {
      expect(isTextContent(textContent)).toBe(true);
    });

    it('should return false for non-text content', () => {
      expect(isTextContent(functionCallContent)).toBe(false);
      expect(isTextContent(imageContent)).toBe(false);
      expect(isTextContent(audioContent)).toBe(false);
    });

    it('should enable TypeScript type narrowing', () => {
      const content: Content = textContent;
      if (isTextContent(content)) {
        // TypeScript should know this is TextContent
        expect(content.text).toBe('Hello');
      }
    });
  });

  describe('isFunctionCallContent', () => {
    it('should return true for function call content', () => {
      expect(isFunctionCallContent(functionCallContent)).toBe(true);
    });

    it('should return false for non-function call content', () => {
      expect(isFunctionCallContent(textContent)).toBe(false);
      expect(isFunctionCallContent(functionResultContent)).toBe(false);
      expect(isFunctionCallContent(imageContent)).toBe(false);
    });
  });

  describe('isFunctionResultContent', () => {
    it('should return true for function result content', () => {
      expect(isFunctionResultContent(functionResultContent)).toBe(true);
    });

    it('should return false for non-function result content', () => {
      expect(isFunctionResultContent(textContent)).toBe(false);
      expect(isFunctionResultContent(functionCallContent)).toBe(false);
      expect(isFunctionResultContent(imageContent)).toBe(false);
    });
  });

  describe('isFunctionApprovalRequest', () => {
    it('should return true for function approval request content', () => {
      expect(isFunctionApprovalRequest(approvalRequestContent)).toBe(true);
    });

    it('should return false for non-approval request content', () => {
      expect(isFunctionApprovalRequest(textContent)).toBe(false);
      expect(isFunctionApprovalRequest(functionCallContent)).toBe(false);
      expect(isFunctionApprovalRequest(approvalResponseContent)).toBe(false);
    });
  });

  describe('isFunctionApprovalResponse', () => {
    it('should return true for function approval response content', () => {
      expect(isFunctionApprovalResponse(approvalResponseContent)).toBe(true);
    });

    it('should return false for non-approval response content', () => {
      expect(isFunctionApprovalResponse(textContent)).toBe(false);
      expect(isFunctionApprovalResponse(functionCallContent)).toBe(false);
      expect(isFunctionApprovalResponse(approvalRequestContent)).toBe(false);
    });
  });

  describe('isImageContent', () => {
    it('should return true for image content', () => {
      expect(isImageContent(imageContent)).toBe(true);
    });

    it('should return false for non-image content', () => {
      expect(isImageContent(textContent)).toBe(false);
      expect(isImageContent(audioContent)).toBe(false);
      expect(isImageContent(fileContent)).toBe(false);
    });
  });

  describe('isAudioContent', () => {
    it('should return true for audio content', () => {
      expect(isAudioContent(audioContent)).toBe(true);
    });

    it('should return false for non-audio content', () => {
      expect(isAudioContent(textContent)).toBe(false);
      expect(isAudioContent(imageContent)).toBe(false);
      expect(isAudioContent(fileContent)).toBe(false);
    });
  });

  describe('isFileContent', () => {
    it('should return true for file content', () => {
      expect(isFileContent(fileContent)).toBe(true);
    });

    it('should return false for non-file content', () => {
      expect(isFileContent(textContent)).toBe(false);
      expect(isFileContent(imageContent)).toBe(false);
      expect(isFileContent(vectorStoreContent)).toBe(false);
    });
  });

  describe('isVectorStoreContent', () => {
    it('should return true for vector store content', () => {
      expect(isVectorStoreContent(vectorStoreContent)).toBe(true);
    });

    it('should return false for non-vector store content', () => {
      expect(isVectorStoreContent(textContent)).toBe(false);
      expect(isVectorStoreContent(fileContent)).toBe(false);
      expect(isVectorStoreContent(imageContent)).toBe(false);
    });
  });
});

describe('Utility Functions', () => {
  describe('getTextContent', () => {
    it('should extract text from single text content', () => {
      const msg = createUserMessage('Hello world');
      expect(getTextContent(msg)).toBe('Hello world');
    });

    it('should extract and join multiple text contents', () => {
      const msg: ChatMessage = {
        role: MessageRole.User,
        content: [
          { type: 'text', text: 'First line' },
          { type: 'text', text: 'Second line' },
          { type: 'text', text: 'Third line' },
        ],
      };
      expect(getTextContent(msg)).toBe('First line\nSecond line\nThird line');
    });

    it('should return empty string when no text content', () => {
      const msg: ChatMessage = {
        role: MessageRole.User,
        content: [
          { type: 'image', url: 'https://example.com/image.png' },
          { type: 'file', fileId: 'file_123' },
        ],
      };
      expect(getTextContent(msg)).toBe('');
    });

    it('should filter out non-text content', () => {
      const msg: ChatMessage = {
        role: MessageRole.User,
        content: [
          { type: 'text', text: 'Hello' },
          { type: 'image', url: 'https://example.com/image.png' },
          { type: 'text', text: 'World' },
        ],
      };
      expect(getTextContent(msg)).toBe('Hello\nWorld');
    });
  });

  describe('getFunctionCalls', () => {
    it('should extract all function calls from content array', () => {
      const msg: ChatMessage = {
        role: MessageRole.Assistant,
        content: [
          { type: 'text', text: 'Let me check that' },
          {
            type: 'function_call',
            callId: 'call_1',
            name: 'get_weather',
            arguments: '{"location":"Seattle"}',
          },
          {
            type: 'function_call',
            callId: 'call_2',
            name: 'get_time',
            arguments: '{}',
          },
        ],
      };

      const calls = getFunctionCalls(msg);
      expect(calls).toHaveLength(2);
      expect(calls[0].callId).toBe('call_1');
      expect(calls[0].name).toBe('get_weather');
      expect(calls[1].callId).toBe('call_2');
      expect(calls[1].name).toBe('get_time');
    });

    it('should return empty array when no function calls', () => {
      const msg = createUserMessage('Hello');
      expect(getFunctionCalls(msg)).toEqual([]);
    });

    it('should handle single content that is a function call', () => {
      const msg: ChatMessage = {
        role: MessageRole.Assistant,
        content: {
          type: 'function_call',
          callId: 'call_1',
          name: 'test',
          arguments: '{}',
        },
      };

      const calls = getFunctionCalls(msg);
      expect(calls).toHaveLength(1);
      expect(calls[0].name).toBe('test');
    });
  });

  describe('getFunctionResults', () => {
    it('should extract all function results from content array', () => {
      const msg: ChatMessage = {
        role: MessageRole.Tool,
        content: [
          {
            type: 'function_result',
            callId: 'call_1',
            result: { temperature: 72 },
          },
          {
            type: 'function_result',
            callId: 'call_2',
            result: { time: '12:00' },
          },
        ],
      };

      const results = getFunctionResults(msg);
      expect(results).toHaveLength(2);
      expect(results[0].callId).toBe('call_1');
      expect(results[0].result).toEqual({ temperature: 72 });
      expect(results[1].callId).toBe('call_2');
      expect(results[1].result).toEqual({ time: '12:00' });
    });

    it('should return empty array when no function results', () => {
      const msg = createUserMessage('Hello');
      expect(getFunctionResults(msg)).toEqual([]);
    });
  });

  describe('hasContent', () => {
    it('should return true when content type present', () => {
      const msg: ChatMessage = {
        role: MessageRole.User,
        content: [
          { type: 'text', text: 'Hello' },
          { type: 'image', url: 'https://example.com/image.png' },
        ],
      };

      expect(hasContent(msg, 'text')).toBe(true);
      expect(hasContent(msg, 'image')).toBe(true);
    });

    it('should return false when content type absent', () => {
      const msg = createUserMessage('Hello');

      expect(hasContent(msg, 'image')).toBe(false);
      expect(hasContent(msg, 'audio')).toBe(false);
      expect(hasContent(msg, 'function_call')).toBe(false);
    });

    it('should handle single content', () => {
      const msg = createUserMessage('Hello');
      expect(hasContent(msg, 'text')).toBe(true);
    });
  });
});

describe('Edge Cases', () => {
  it('should handle message with empty string content', () => {
    const msg = createUserMessage('');
    expect(getTextContent(msg)).toBe('');
  });

  it('should handle message with empty content array', () => {
    const msg: ChatMessage = {
      role: MessageRole.User,
      content: [],
    };
    expect(getTextContent(msg)).toBe('');
    expect(getFunctionCalls(msg)).toEqual([]);
    expect(getFunctionResults(msg)).toEqual([]);
  });

  it('should handle message with undefined optional fields', () => {
    const msg: ChatMessage = {
      role: MessageRole.User,
      content: { type: 'text', text: 'Hello' },
    };

    expect(msg.name).toBeUndefined();
    expect(msg.timestamp).toBeUndefined();
    expect(msg.metadata).toBeUndefined();
  });

  it('should handle message with all optional fields', () => {
    const msg: ChatMessage = {
      role: MessageRole.User,
      content: { type: 'text', text: 'Hello' },
      name: 'John',
      timestamp: new Date('2024-01-01'),
      metadata: { source: 'web', sessionId: '123' },
    };

    expect(msg.name).toBe('John');
    expect(msg.timestamp).toBeInstanceOf(Date);
    expect(msg.metadata?.source).toBe('web');
    expect(msg.metadata?.sessionId).toBe('123');
  });

  it('should handle message with multiple content types in array', () => {
    const msg: ChatMessage = {
      role: MessageRole.User,
      content: [
        { type: 'text', text: 'Check this image' },
        { type: 'image', url: 'https://example.com/img.png', detail: 'high' },
        { type: 'file', fileId: 'file_123', purpose: 'analysis' },
      ],
    };

    expect(getTextContent(msg)).toBe('Check this image');
    expect(hasContent(msg, 'text')).toBe(true);
    expect(hasContent(msg, 'image')).toBe(true);
    expect(hasContent(msg, 'file')).toBe(true);
  });

  it('should work with type inference without type assertions', () => {
    // This tests that TypeScript inference works properly
    const msg = createUserMessage('Hello');
    const text = getTextContent(msg);

    // TypeScript should infer text as string
    expect(typeof text).toBe('string');

    const calls = getFunctionCalls(msg);
    // TypeScript should infer calls as FunctionCallContent[]
    expect(Array.isArray(calls)).toBe(true);
  });

  it('should handle image content with detail options', () => {
    const lowDetail: ImageContent = {
      type: 'image',
      url: 'https://example.com/img.png',
      detail: 'low',
    };
    const highDetail: ImageContent = {
      type: 'image',
      url: 'https://example.com/img.png',
      detail: 'high',
    };
    const autoDetail: ImageContent = {
      type: 'image',
      url: 'https://example.com/img.png',
      detail: 'auto',
    };
    const noDetail: ImageContent = {
      type: 'image',
      url: 'https://example.com/img.png',
    };

    expect(lowDetail.detail).toBe('low');
    expect(highDetail.detail).toBe('high');
    expect(autoDetail.detail).toBe('auto');
    expect(noDetail.detail).toBeUndefined();
  });

  it('should handle audio content with different formats', () => {
    const wavAudio: AudioContent = {
      type: 'audio',
      data: Buffer.from('wav data'),
      format: 'wav',
    };
    const mp3Audio: AudioContent = {
      type: 'audio',
      data: Buffer.from('mp3 data'),
      format: 'mp3',
    };

    expect(wavAudio.format).toBe('wav');
    expect(mp3Audio.format).toBe('mp3');
  });

  it('should handle file content with optional purpose', () => {
    const fileWithPurpose: FileContent = {
      type: 'file',
      fileId: 'file_123',
      purpose: 'assistants',
    };
    const fileWithoutPurpose: FileContent = {
      type: 'file',
      fileId: 'file_456',
    };

    expect(fileWithPurpose.purpose).toBe('assistants');
    expect(fileWithoutPurpose.purpose).toBeUndefined();
  });

  it('should handle function result with error', () => {
    const error = new Error('Network timeout');
    const result: FunctionResultContent = {
      type: 'function_result',
      callId: 'call_123',
      result: null,
      error,
    };

    expect(result.error).toBe(error);
    expect(result.error?.message).toBe('Network timeout');
  });
});
