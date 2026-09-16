export class AgentFrameworkError extends Error {
  public constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = new.target.name;
  }
}

export class AgentInvalidRequestError extends AgentFrameworkError {}
export class AgentInvalidResponseError extends AgentFrameworkError {}
export class ToolExecutionError extends AgentFrameworkError {}

export class MiddlewareFailure extends AgentFrameworkError {}
