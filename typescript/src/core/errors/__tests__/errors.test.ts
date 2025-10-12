import { describe, it, expect } from 'vitest';
import { AgentFrameworkError } from '../base-error';
import { AgentExecutionError, AgentInitializationError } from '../agent-errors';
import { ToolExecutionError } from '../tool-errors';
import { ChatClientError } from '../chat-client-error';
import {
  WorkflowValidationError,
  GraphConnectivityError,
  TypeCompatibilityError,
} from '../workflow-errors';

describe('AgentFrameworkError', () => {
  it('should create error with message', () => {
    const error = new AgentFrameworkError('Test error');
    expect(error.message).toBe('Test error');
    expect(error.name).toBe('AgentFrameworkError');
    expect(error.cause).toBeUndefined();
    expect(error.code).toBeUndefined();
  });

  it('should create error with cause', () => {
    const cause = new Error('Underlying error');
    const error = new AgentFrameworkError('Test error', cause);
    expect(error.message).toBe('Test error');
    expect(error.cause).toBe(cause);
    expect(error.code).toBeUndefined();
  });

  it('should create error with code', () => {
    const error = new AgentFrameworkError('Test error', undefined, 'ERR_001');
    expect(error.message).toBe('Test error');
    expect(error.code).toBe('ERR_001');
    expect(error.cause).toBeUndefined();
  });

  it('should create error with cause and code', () => {
    const cause = new Error('Underlying error');
    const error = new AgentFrameworkError('Test error', cause, 'ERR_001');
    expect(error.message).toBe('Test error');
    expect(error.cause).toBe(cause);
    expect(error.code).toBe('ERR_001');
  });

  it('should capture stack trace', () => {
    const error = new AgentFrameworkError('Test error');
    expect(error.stack).toBeDefined();
    expect(error.stack).toContain('AgentFrameworkError');
  });

  it('should be instance of Error', () => {
    const error = new AgentFrameworkError('Test error');
    expect(error instanceof Error).toBe(true);
    expect(error instanceof AgentFrameworkError).toBe(true);
  });

  it('should convert to string without cause', () => {
    const error = new AgentFrameworkError('Test error', undefined, 'ERR_001');
    const str = error.toString();
    expect(str).toContain('AgentFrameworkError: Test error');
    expect(str).toContain('[ERR_001]');
  });

  it('should convert to string with cause', () => {
    const cause = new Error('Underlying error');
    const error = new AgentFrameworkError('Test error', cause);
    const str = error.toString();
    expect(str).toContain('AgentFrameworkError: Test error');
    expect(str).toContain('Caused by: Error: Underlying error');
  });

  it('should serialize to JSON without cause', () => {
    const error = new AgentFrameworkError('Test error', undefined, 'ERR_001');
    const json = error.toJSON();
    expect(json).toEqual({
      name: 'AgentFrameworkError',
      message: 'Test error',
      code: 'ERR_001',
      cause: undefined,
    });
  });

  it('should serialize to JSON with cause', () => {
    const cause = new Error('Underlying error');
    const error = new AgentFrameworkError('Test error', cause, 'ERR_001');
    const json = error.toJSON();
    expect(json).toEqual({
      name: 'AgentFrameworkError',
      message: 'Test error',
      code: 'ERR_001',
      cause: {
        name: 'Error',
        message: 'Underlying error',
      },
    });
  });
});

describe('AgentExecutionError', () => {
  it('should create error with correct name', () => {
    const error = new AgentExecutionError('Execution failed');
    expect(error.name).toBe('AgentExecutionError');
    expect(error.message).toBe('Execution failed');
  });

  it('should extend AgentFrameworkError', () => {
    const error = new AgentExecutionError('Execution failed');
    expect(error instanceof AgentFrameworkError).toBe(true);
    expect(error instanceof AgentExecutionError).toBe(true);
  });

  it('should support cause chaining', () => {
    const cause = new Error('Network error');
    const error = new AgentExecutionError('Execution failed', cause, 'AGENT_EXEC_001');
    expect(error.cause).toBe(cause);
    expect(error.code).toBe('AGENT_EXEC_001');
  });

  it('should capture stack trace', () => {
    const error = new AgentExecutionError('Execution failed');
    expect(error.stack).toBeDefined();
    expect(error.stack).toContain('AgentExecutionError');
  });
});

describe('AgentInitializationError', () => {
  it('should create error with correct name', () => {
    const error = new AgentInitializationError('Initialization failed');
    expect(error.name).toBe('AgentInitializationError');
    expect(error.message).toBe('Initialization failed');
  });

  it('should extend AgentFrameworkError', () => {
    const error = new AgentInitializationError('Initialization failed');
    expect(error instanceof AgentFrameworkError).toBe(true);
    expect(error instanceof AgentInitializationError).toBe(true);
  });

  it('should support cause and code', () => {
    const cause = new Error('Config error');
    const error = new AgentInitializationError('Initialization failed', cause, 'AGENT_INIT_001');
    expect(error.cause).toBe(cause);
    expect(error.code).toBe('AGENT_INIT_001');
  });
});

describe('ToolExecutionError', () => {
  it('should create error with correct name', () => {
    const error = new ToolExecutionError('Tool execution failed');
    expect(error.name).toBe('ToolExecutionError');
    expect(error.message).toBe('Tool execution failed');
  });

  it('should extend AgentFrameworkError', () => {
    const error = new ToolExecutionError('Tool execution failed');
    expect(error instanceof AgentFrameworkError).toBe(true);
    expect(error instanceof ToolExecutionError).toBe(true);
  });

  it('should support cause and code', () => {
    const cause = new Error('API error');
    const error = new ToolExecutionError('Tool execution failed', cause, 'TOOL_EXEC_001');
    expect(error.cause).toBe(cause);
    expect(error.code).toBe('TOOL_EXEC_001');
  });
});

describe('ChatClientError', () => {
  it('should create error with correct name', () => {
    const error = new ChatClientError('Chat client error');
    expect(error.name).toBe('ChatClientError');
    expect(error.message).toBe('Chat client error');
  });

  it('should extend AgentFrameworkError', () => {
    const error = new ChatClientError('Chat client error');
    expect(error instanceof AgentFrameworkError).toBe(true);
    expect(error instanceof ChatClientError).toBe(true);
  });

  it('should support cause and code', () => {
    const cause = new Error('Network timeout');
    const error = new ChatClientError('Chat client error', cause, 'CHAT_CLIENT_TIMEOUT_001');
    expect(error.cause).toBe(cause);
    expect(error.code).toBe('CHAT_CLIENT_TIMEOUT_001');
  });
});

describe('WorkflowValidationError', () => {
  it('should create error with correct name', () => {
    const error = new WorkflowValidationError('Workflow validation failed');
    expect(error.name).toBe('WorkflowValidationError');
    expect(error.message).toBe('Workflow validation failed');
  });

  it('should extend AgentFrameworkError', () => {
    const error = new WorkflowValidationError('Workflow validation failed');
    expect(error instanceof AgentFrameworkError).toBe(true);
    expect(error instanceof WorkflowValidationError).toBe(true);
  });

  it('should support cause and code', () => {
    const cause = new Error('Invalid definition');
    const error = new WorkflowValidationError('Workflow validation failed', cause, 'WORKFLOW_VAL_001');
    expect(error.cause).toBe(cause);
    expect(error.code).toBe('WORKFLOW_VAL_001');
  });
});

describe('GraphConnectivityError', () => {
  it('should create error with correct name', () => {
    const error = new GraphConnectivityError('Graph connectivity error');
    expect(error.name).toBe('GraphConnectivityError');
    expect(error.message).toBe('Graph connectivity error');
  });

  it('should extend WorkflowValidationError', () => {
    const error = new GraphConnectivityError('Graph connectivity error');
    expect(error instanceof AgentFrameworkError).toBe(true);
    expect(error instanceof WorkflowValidationError).toBe(true);
    expect(error instanceof GraphConnectivityError).toBe(true);
  });

  it('should support cause and code', () => {
    const cause = new Error('Disconnected node');
    const error = new GraphConnectivityError('Graph connectivity error', cause, 'WORKFLOW_GRAPH_001');
    expect(error.cause).toBe(cause);
    expect(error.code).toBe('WORKFLOW_GRAPH_001');
  });
});

describe('TypeCompatibilityError', () => {
  it('should create error with correct name', () => {
    const error = new TypeCompatibilityError('Type compatibility error');
    expect(error.name).toBe('TypeCompatibilityError');
    expect(error.message).toBe('Type compatibility error');
  });

  it('should extend WorkflowValidationError', () => {
    const error = new TypeCompatibilityError('Type compatibility error');
    expect(error instanceof AgentFrameworkError).toBe(true);
    expect(error instanceof WorkflowValidationError).toBe(true);
    expect(error instanceof TypeCompatibilityError).toBe(true);
  });

  it('should support cause and code', () => {
    const cause = new Error('Type mismatch');
    const error = new TypeCompatibilityError('Type compatibility error', cause, 'WORKFLOW_TYPE_001');
    expect(error.cause).toBe(cause);
    expect(error.code).toBe('WORKFLOW_TYPE_001');
  });
});

describe('Error instanceof checks', () => {
  it('should correctly identify error types', () => {
    const agentExecError = new AgentExecutionError('test');
    const agentInitError = new AgentInitializationError('test');
    const toolError = new ToolExecutionError('test');
    const chatError = new ChatClientError('test');
    const workflowError = new WorkflowValidationError('test');
    const graphError = new GraphConnectivityError('test');
    const typeError = new TypeCompatibilityError('test');

    // All should be instances of AgentFrameworkError
    expect(agentExecError instanceof AgentFrameworkError).toBe(true);
    expect(agentInitError instanceof AgentFrameworkError).toBe(true);
    expect(toolError instanceof AgentFrameworkError).toBe(true);
    expect(chatError instanceof AgentFrameworkError).toBe(true);
    expect(workflowError instanceof AgentFrameworkError).toBe(true);
    expect(graphError instanceof AgentFrameworkError).toBe(true);
    expect(typeError instanceof AgentFrameworkError).toBe(true);

    // Graph and Type errors should be instances of WorkflowValidationError
    expect(graphError instanceof WorkflowValidationError).toBe(true);
    expect(typeError instanceof WorkflowValidationError).toBe(true);

    // But not vice versa
    expect(workflowError instanceof GraphConnectivityError).toBe(false);
    expect(workflowError instanceof TypeCompatibilityError).toBe(false);
  });
});

describe('Error cause chaining', () => {
  it('should chain errors correctly', () => {
    const originalError = new Error('Original error');
    const wrappedError = new ToolExecutionError('Tool failed', originalError);
    const topError = new AgentExecutionError('Agent failed', wrappedError);

    expect(topError.cause).toBe(wrappedError);
    expect(topError.cause?.cause).toBe(originalError);
  });

  it('should include cause in toString', () => {
    const originalError = new Error('Database connection failed');
    const wrappedError = new ToolExecutionError('Query failed', originalError);
    const str = wrappedError.toString();

    expect(str).toContain('ToolExecutionError: Query failed');
    expect(str).toContain('Caused by: Error: Database connection failed');
  });
});

describe('Error code handling', () => {
  it('should allow programmatic error handling by code', () => {
    const error = new ChatClientError('Rate limit exceeded', undefined, 'CHAT_CLIENT_RATE_LIMIT_001');

    // Simulate error handling logic
    if (error.code === 'CHAT_CLIENT_RATE_LIMIT_001') {
      expect(true).toBe(true); // Would trigger retry logic
    } else {
      expect(true).toBe(false);
    }
  });

  it('should include code in JSON serialization', () => {
    const error = new AgentExecutionError('Execution failed', undefined, 'AGENT_EXEC_TIMEOUT_001');
    const json = error.toJSON();

    expect(json.code).toBe('AGENT_EXEC_TIMEOUT_001');
  });
});
