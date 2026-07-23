package agentframework

import (
	"context"
	"maps"

	"github.com/google/uuid"
)

// Agent runs a conversation with a language model.
type Agent interface {
	ID() string
	Name() string
	Description() string
	Run(ctx context.Context, messages []Message, opts ...RunOption) (*AgentResponse, error)
}

// BaseAgent is the standard Agent implementation backed by a ChatClient.
type BaseAgent struct {
	id                 string
	name               string
	description        string
	client             ChatClient
	instructions       []string
	defaultChatOpts    []ChatOption
	agentMiddleware    []AgentMiddleware
	chatMiddleware     []ChatMiddleware
	functionMiddleware []FunctionMiddleware
}

// AgentOption configures a BaseAgent.
type AgentOption func(*BaseAgent)

// NewAgent creates a new BaseAgent with the given ChatClient and options.
func NewAgent(client ChatClient, opts ...AgentOption) *BaseAgent {
	a := &BaseAgent{
		id:     uuid.New().String(),
		client: client,
	}
	for _, opt := range opts {
		opt(a)
	}
	return a
}

func (a *BaseAgent) ID() string          { return a.id }
func (a *BaseAgent) Name() string        { return a.name }
func (a *BaseAgent) Description() string { return a.description }

// Run executes the agent with the given messages.
func (a *BaseAgent) Run(ctx context.Context, messages []Message, opts ...RunOption) (*AgentResponse, error) {
	if len(messages) == 0 {
		return nil, ErrEmptyMessages
	}

	runOpts := NewRunOptions(opts...)

	ac := &AgentContext{
		Agent:    a,
		Messages: messages,
		Options:  &runOpts,
		Metadata: make(map[string]any),
	}

	terminal := func(ctx context.Context, ac *AgentContext) error {
		resp, err := a.runCore(ctx, ac)
		if err != nil {
			return err
		}
		ac.Response = resp
		return nil
	}

	handler := buildAgentChain(a.agentMiddleware, terminal)
	if err := handler(ctx, ac); err != nil {
		return nil, err
	}

	return ac.Response, nil
}

func (a *BaseAgent) runCore(ctx context.Context, ac *AgentContext) (*AgentResponse, error) {
	var fullMessages []Message
	for _, instr := range a.instructions {
		fullMessages = append(fullMessages, NewSystemMessage(instr))
	}
	fullMessages = append(fullMessages, ac.Messages...)

	chatOpts := make([]ChatOption, 0, len(a.defaultChatOpts)+1)
	chatOpts = append(chatOpts, a.defaultChatOpts...)
	chatOpts = append(chatOpts, func(o *ChatOptions) {
		merged := ac.Options.ChatOptions
		if merged.Temperature != nil {
			o.Temperature = merged.Temperature
		}
		if merged.MaxTokens != nil {
			o.MaxTokens = merged.MaxTokens
		}
		if merged.Model != "" {
			o.Model = merged.Model
		}
		if merged.Metadata != nil {
			if o.Metadata == nil {
				o.Metadata = make(map[string]any)
			}
			maps.Copy(o.Metadata, merged.Metadata)
		}
	})

	resolvedOpts := NewChatOptions(chatOpts...)

	cc := &ChatContext{
		Client:   a.client,
		Messages: fullMessages,
		Options:  &resolvedOpts,
		Metadata: make(map[string]any),
	}

	chatTerminal := func(ctx context.Context, cc *ChatContext) error {
		var opts []ChatOption
		if cc.Options.Temperature != nil {
			t := *cc.Options.Temperature
			opts = append(opts, WithTemperature(t))
		}
		if cc.Options.MaxTokens != nil {
			n := *cc.Options.MaxTokens
			opts = append(opts, WithMaxTokens(n))
		}
		if cc.Options.Model != "" {
			opts = append(opts, WithModel(cc.Options.Model))
		}
		resp, err := cc.Client.GetResponse(ctx, cc.Messages, opts...)
		if err != nil {
			return err
		}
		cc.Response = resp
		return nil
	}

	chatHandler := buildChatChain(a.chatMiddleware, chatTerminal)
	if err := chatHandler(ctx, cc); err != nil {
		return nil, err
	}

	return &AgentResponse{
		ChatResponse: *cc.Response,
		AgentID:      a.id,
	}, nil
}

// WithID sets the agent ID.
func WithID(id string) AgentOption {
	return func(a *BaseAgent) {
		a.id = id
	}
}

// WithName sets the agent name.
func WithName(name string) AgentOption {
	return func(a *BaseAgent) {
		a.name = name
	}
}

// WithDescription sets the agent description.
func WithDescription(desc string) AgentOption {
	return func(a *BaseAgent) {
		a.description = desc
	}
}

// WithInstructions sets the system instructions prepended to every request.
func WithInstructions(instructions ...string) AgentOption {
	return func(a *BaseAgent) {
		a.instructions = instructions
	}
}

// WithDefaultChatOptions sets default ChatOptions applied to every request.
func WithDefaultChatOptions(opts ...ChatOption) AgentOption {
	return func(a *BaseAgent) {
		a.defaultChatOpts = opts
	}
}

// WithAgentMiddleware appends agent-level middleware to the pipeline.
func WithAgentMiddleware(mw ...AgentMiddleware) AgentOption {
	return func(a *BaseAgent) {
		a.agentMiddleware = append(a.agentMiddleware, mw...)
	}
}

// WithChatMiddleware appends chat-level middleware to the pipeline.
func WithChatMiddleware(mw ...ChatMiddleware) AgentOption {
	return func(a *BaseAgent) {
		a.chatMiddleware = append(a.chatMiddleware, mw...)
	}
}

// WithFunctionMiddleware appends function-level middleware to the pipeline.
func WithFunctionMiddleware(mw ...FunctionMiddleware) AgentOption {
	return func(a *BaseAgent) {
		a.functionMiddleware = append(a.functionMiddleware, mw...)
	}
}
