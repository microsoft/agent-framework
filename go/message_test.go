package agentframework_test

import (
	"testing"

	af "github.com/microsoft/agent-framework/go"
	"github.com/stretchr/testify/assert"
)

func TestNewTextMessage(t *testing.T) {
	msg := af.NewTextMessage(af.RoleAssistant, "hello")

	assert.Equal(t, af.RoleAssistant, msg.Role)
	assert.Len(t, msg.Contents, 1)
	assert.Equal(t, af.ContentTypeText, msg.Contents[0].Type)
	assert.Equal(t, "hello", msg.Contents[0].Text)
	assert.NotEmpty(t, msg.ID, "message should have an auto-generated ID")
}

func TestNewUserMessage(t *testing.T) {
	msg := af.NewUserMessage("how are you?")

	assert.Equal(t, af.RoleUser, msg.Role)
	assert.Len(t, msg.Contents, 1)
	assert.Equal(t, af.ContentTypeText, msg.Contents[0].Type)
	assert.Equal(t, "how are you?", msg.Contents[0].Text)
}

func TestNewSystemMessage(t *testing.T) {
	msg := af.NewSystemMessage("you are helpful")

	assert.Equal(t, af.RoleSystem, msg.Role)
	assert.Len(t, msg.Contents, 1)
	assert.Equal(t, af.ContentTypeText, msg.Contents[0].Type)
	assert.Equal(t, "you are helpful", msg.Contents[0].Text)
}

func TestMessageText(t *testing.T) {
	tests := []struct {
		name     string
		msg      af.Message
		expected string
	}{
		{
			name:     "single text content",
			msg:      af.NewUserMessage("hello"),
			expected: "hello",
		},
		{
			name: "multiple text contents concatenated",
			msg: af.Message{
				Role: af.RoleAssistant,
				Contents: []af.Content{
					{Type: af.ContentTypeText, Text: "hello "},
					{Type: af.ContentTypeText, Text: "world"},
				},
			},
			expected: "hello world",
		},
		{
			name: "non-text contents skipped",
			msg: af.Message{
				Role: af.RoleAssistant,
				Contents: []af.Content{
					{Type: af.ContentTypeText, Text: "hello"},
					{Type: af.ContentTypeFunctionCall, Name: "foo"},
				},
			},
			expected: "hello",
		},
		{
			name:     "empty contents",
			msg:      af.Message{Role: af.RoleUser},
			expected: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.expected, tt.msg.Text())
		})
	}
}
