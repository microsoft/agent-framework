package agentframework

// UsageDetails contains token usage information from a chat response.
type UsageDetails struct {
	InputTokens  int
	OutputTokens int
	TotalTokens  int
}

// ChatResponse is the result of a ChatClient.GetResponse call.
type ChatResponse struct {
	Messages   []Message
	ResponseID string
	Usage      *UsageDetails
}

// AgentResponse is the result of an Agent.Run call.
type AgentResponse struct {
	ChatResponse
	AgentID string
}
