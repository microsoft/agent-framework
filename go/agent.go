package agentframework

import (
	"context"

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
	id              string
	name            string
	description     string
	client          ChatClient
	instructions    []string
	defaultChatOpts []ChatOption
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

	// Build the full message list: instructions first, then user messages.
	var fullMessages []Message
	for _, instr := range a.instructions {
		fullMessages = append(fullMessages, NewSystemMessage(instr))
	}
	fullMessages = append(fullMessages, messages...)

	// Merge default chat options with run-level overrides.
	// Defaults are applied first, then run-level options override.
	chatOpts := make([]ChatOption, 0, len(a.defaultChatOpts)+1)
	chatOpts = append(chatOpts, a.defaultChatOpts...)
	chatOpts = append(chatOpts, func(o *ChatOptions) {
		merged := runOpts.ChatOptions
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
			for k, v := range merged.Metadata {
				o.Metadata[k] = v
			}
		}
	})

	resp, err := a.client.GetResponse(ctx, fullMessages, chatOpts...)
	if err != nil {
		return nil, err
	}

	return &AgentResponse{
		ChatResponse: *resp,
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
