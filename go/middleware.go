package agentframework

import "context"

// --- Agent Middleware ---

type AgentHandler func(ctx context.Context, ac *AgentContext) error

type AgentMiddleware interface {
	HandleAgent(ctx context.Context, ac *AgentContext, next AgentHandler) error
}

type AgentMiddlewareFunc func(ctx context.Context, ac *AgentContext, next AgentHandler) error

func (f AgentMiddlewareFunc) HandleAgent(ctx context.Context, ac *AgentContext, next AgentHandler) error {
	return f(ctx, ac, next)
}

type AgentContext struct {
	Agent    Agent
	Messages []Message
	Options  *RunOptions
	Response *AgentResponse
	Metadata map[string]any
}

// --- Chat Middleware ---

type ChatHandler func(ctx context.Context, cc *ChatContext) error

type ChatMiddleware interface {
	HandleChat(ctx context.Context, cc *ChatContext, next ChatHandler) error
}

type ChatMiddlewareFunc func(ctx context.Context, cc *ChatContext, next ChatHandler) error

func (f ChatMiddlewareFunc) HandleChat(ctx context.Context, cc *ChatContext, next ChatHandler) error {
	return f(ctx, cc, next)
}

type ChatContext struct {
	Client   ChatClient
	Messages []Message
	Options  *ChatOptions
	Response *ChatResponse
	Metadata map[string]any
}

// --- Function Middleware ---

type FunctionHandler func(ctx context.Context, fc *FunctionContext) error

type FunctionMiddleware interface {
	HandleFunction(ctx context.Context, fc *FunctionContext, next FunctionHandler) error
}

type FunctionMiddlewareFunc func(ctx context.Context, fc *FunctionContext, next FunctionHandler) error

func (f FunctionMiddlewareFunc) HandleFunction(ctx context.Context, fc *FunctionContext, next FunctionHandler) error {
	return f(ctx, fc, next)
}

type FunctionContext struct {
	ToolName  string
	Arguments map[string]any
	Result    string
	Err       error
	Metadata  map[string]any
}

// --- Chain Builders ---

func buildAgentChain(middlewares []AgentMiddleware, terminal AgentHandler) AgentHandler {
	handler := terminal
	for i := len(middlewares) - 1; i >= 0; i-- {
		mw := middlewares[i]
		next := handler
		handler = func(ctx context.Context, ac *AgentContext) error {
			return mw.HandleAgent(ctx, ac, next)
		}
	}
	return handler
}

func buildChatChain(middlewares []ChatMiddleware, terminal ChatHandler) ChatHandler {
	handler := terminal
	for i := len(middlewares) - 1; i >= 0; i-- {
		mw := middlewares[i]
		next := handler
		handler = func(ctx context.Context, cc *ChatContext) error {
			return mw.HandleChat(ctx, cc, next)
		}
	}
	return handler
}

func buildFunctionChain(middlewares []FunctionMiddleware, terminal FunctionHandler) FunctionHandler {
	handler := terminal
	for i := len(middlewares) - 1; i >= 0; i-- {
		mw := middlewares[i]
		next := handler
		handler = func(ctx context.Context, fc *FunctionContext) error {
			return mw.HandleFunction(ctx, fc, next)
		}
	}
	return handler
}
