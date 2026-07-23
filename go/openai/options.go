package openai

// ClientOption configures the OpenAI Client.
type ClientOption func(*clientConfig)

type clientConfig struct {
	baseURL string
}

// WithBaseURL sets the base URL for the OpenAI API (useful for testing or proxies).
func WithBaseURL(url string) ClientOption {
	return func(c *clientConfig) {
		c.baseURL = url
	}
}
