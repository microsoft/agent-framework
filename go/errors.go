package agentframework

import "errors"

var (
	// ErrEmptyMessages is returned when an agent is called with no messages.
	ErrEmptyMessages = errors.New("agentframework: messages must not be empty")

	// ErrNilClient is returned when an agent is created with a nil ChatClient.
	ErrNilClient = errors.New("agentframework: chat client must not be nil")
)
