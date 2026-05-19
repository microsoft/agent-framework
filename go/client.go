package agentframework

import "context"

// ChatClient sends messages to a language model and returns a response.
type ChatClient interface {
	GetResponse(ctx context.Context, messages []Message, opts ...ChatOption) (*ChatResponse, error)
}
