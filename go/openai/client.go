package openai

import (
	"context"
	"fmt"

	af "github.com/microsoft/agent-framework/go"
	gogpt "github.com/sashabaranov/go-openai"
)

// Client is an OpenAI-backed ChatClient.
type Client struct {
	inner *gogpt.Client
	model string
}

// NewClient creates a new OpenAI ChatClient.
func NewClient(apiKey string, model string, opts ...ClientOption) *Client {
	var cfg clientConfig
	for _, opt := range opts {
		opt(&cfg)
	}

	clientCfg := gogpt.DefaultConfig(apiKey)
	if cfg.baseURL != "" {
		clientCfg.BaseURL = cfg.baseURL
	}

	return &Client{
		inner: gogpt.NewClientWithConfig(clientCfg),
		model: model,
	}
}

// GetResponse sends messages to OpenAI and returns the response.
func (c *Client) GetResponse(ctx context.Context, messages []af.Message, opts ...af.ChatOption) (*af.ChatResponse, error) {
	chatOpts := af.NewChatOptions(opts...)

	model := c.model
	if chatOpts.Model != "" {
		model = chatOpts.Model
	}

	req := gogpt.ChatCompletionRequest{
		Model:    model,
		Messages: toOpenAIMessages(messages),
	}

	if chatOpts.Temperature != nil {
		req.Temperature = float32(*chatOpts.Temperature)
	}
	if chatOpts.MaxTokens != nil {
		req.MaxTokens = *chatOpts.MaxTokens
	}

	resp, err := c.inner.CreateChatCompletion(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("openai: %w", err)
	}

	return fromOpenAIResponse(resp), nil
}

func toOpenAIMessages(messages []af.Message) []gogpt.ChatCompletionMessage {
	out := make([]gogpt.ChatCompletionMessage, 0, len(messages))
	for _, m := range messages {
		out = append(out, gogpt.ChatCompletionMessage{
			Role:    string(m.Role),
			Content: m.Text(),
		})
	}
	return out
}

func fromOpenAIResponse(resp gogpt.ChatCompletionResponse) *af.ChatResponse {
	messages := make([]af.Message, 0, len(resp.Choices))
	for _, choice := range resp.Choices {
		messages = append(messages, af.NewTextMessage(
			af.Role(choice.Message.Role),
			choice.Message.Content,
		))
	}

	return &af.ChatResponse{
		Messages:   messages,
		ResponseID: resp.ID,
		Usage: &af.UsageDetails{
			InputTokens:  resp.Usage.PromptTokens,
			OutputTokens: resp.Usage.CompletionTokens,
			TotalTokens:  resp.Usage.TotalTokens,
		},
	}
}
