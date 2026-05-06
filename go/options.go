package agentframework

// ChatOptions holds configuration for a ChatClient.GetResponse call.
type ChatOptions struct {
	Temperature *float64
	MaxTokens   *int
	Model       string
	Metadata    map[string]any
}

// ChatOption is a functional option for ChatOptions.
type ChatOption func(*ChatOptions)

// NewChatOptions creates ChatOptions by applying the given options.
func NewChatOptions(opts ...ChatOption) ChatOptions {
	var o ChatOptions
	for _, opt := range opts {
		opt(&o)
	}
	return o
}

// WithTemperature sets the sampling temperature.
func WithTemperature(t float64) ChatOption {
	return func(o *ChatOptions) {
		o.Temperature = &t
	}
}

// WithMaxTokens sets the maximum number of tokens to generate.
func WithMaxTokens(n int) ChatOption {
	return func(o *ChatOptions) {
		o.MaxTokens = &n
	}
}

// WithModel sets the model name.
func WithModel(m string) ChatOption {
	return func(o *ChatOptions) {
		o.Model = m
	}
}

// RunOptions holds configuration for an Agent.Run call.
type RunOptions struct {
	ChatOptions ChatOptions
}

// RunOption is a functional option for RunOptions.
type RunOption func(*RunOptions)

// NewRunOptions creates RunOptions by applying the given options.
func NewRunOptions(opts ...RunOption) RunOptions {
	var o RunOptions
	for _, opt := range opts {
		opt(&o)
	}
	return o
}

// WithChatOption wraps a ChatOption into a RunOption.
func WithChatOption(co ChatOption) RunOption {
	return func(o *RunOptions) {
		co(&o.ChatOptions)
	}
}
