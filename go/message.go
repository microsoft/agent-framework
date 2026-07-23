package agentframework

import (
	"strings"

	"github.com/google/uuid"
)

// Role represents the role of a message sender.
type Role string

const (
	RoleSystem    Role = "system"
	RoleUser      Role = "user"
	RoleAssistant Role = "assistant"
	RoleTool      Role = "tool"
)

// ContentType identifies the kind of content in a message.
type ContentType string

const (
	ContentTypeText           ContentType = "text"
	ContentTypeFunctionCall   ContentType = "function_call"
	ContentTypeFunctionResult ContentType = "function_result"
	ContentTypeError          ContentType = "error"
	ContentTypeUsage          ContentType = "usage"
)

// Content is a single piece of content within a message.
type Content struct {
	Type      ContentType
	Text      string
	Name      string
	Arguments map[string]any
	CallID    string
	Result    string
	Message   string
	Code      string
}

// Message is a single message in a conversation.
type Message struct {
	Role     Role
	Contents []Content
	ID       string
	Metadata map[string]any
}

// Text returns the concatenation of all text contents in the message.
func (m Message) Text() string {
	var b strings.Builder
	for _, c := range m.Contents {
		if c.Type == ContentTypeText {
			b.WriteString(c.Text)
		}
	}
	return b.String()
}

// NewTextMessage creates a message with a single text content.
func NewTextMessage(role Role, text string) Message {
	return Message{
		Role: role,
		Contents: []Content{
			{Type: ContentTypeText, Text: text},
		},
		ID: uuid.New().String(),
	}
}

// NewUserMessage creates a user message with text content.
func NewUserMessage(text string) Message {
	return NewTextMessage(RoleUser, text)
}

// NewSystemMessage creates a system message with text content.
func NewSystemMessage(text string) Message {
	return NewTextMessage(RoleSystem, text)
}
