package agentframework_test

import (
	"context"
	"errors"
	"testing"

	af "github.com/microsoft/agent-framework/go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockChatClient is a test double for ChatClient.
type mockChatClient struct {
	response *af.ChatResponse
	err      error
	captured struct {
		messages []af.Message
		opts     af.ChatOptions
	}
}

func (m *mockChatClient) GetResponse(_ context.Context, messages []af.Message, opts ...af.ChatOption) (*af.ChatResponse, error) {
	m.captured.messages = messages
	m.captured.opts = af.NewChatOptions(opts...)
	if m.err != nil {
		return nil, m.err
	}
	return m.response, nil
}

func TestNewAgent(t *testing.T) {
	t.Run("generates a UUID id by default", func(t *testing.T) {
		agent := af.NewAgent(&mockChatClient{})
		assert.NotEmpty(t, agent.ID())
	})

	t.Run("uses custom id when provided", func(t *testing.T) {
		agent := af.NewAgent(&mockChatClient{}, af.WithID("custom-id"))
		assert.Equal(t, "custom-id", agent.ID())
	})

	t.Run("sets name and description", func(t *testing.T) {
		agent := af.NewAgent(&mockChatClient{},
			af.WithName("TestBot"),
			af.WithDescription("A test bot"),
		)
		assert.Equal(t, "TestBot", agent.Name())
		assert.Equal(t, "A test bot", agent.Description())
	})
}

func TestBaseAgentRun(t *testing.T) {
	t.Run("delegates to chat client and returns AgentResponse", func(t *testing.T) {
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages:   []af.Message{af.NewTextMessage(af.RoleAssistant, "Paris")},
				ResponseID: "resp-1",
				Usage:      &af.UsageDetails{InputTokens: 10, OutputTokens: 5, TotalTokens: 15},
			},
		}
		agent := af.NewAgent(mock, af.WithName("Geo"))

		resp, err := agent.Run(context.Background(), []af.Message{
			af.NewUserMessage("What is the capital of France?"),
		})

		require.NoError(t, err)
		assert.Equal(t, "resp-1", resp.ResponseID)
		assert.Equal(t, agent.ID(), resp.AgentID)
		assert.Len(t, resp.Messages, 1)
		assert.Equal(t, "Paris", resp.Messages[0].Text())
		assert.Equal(t, 15, resp.Usage.TotalTokens)
	})

	t.Run("prepends system message from instructions", func(t *testing.T) {
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock,
			af.WithInstructions("You are helpful.", "Be concise."),
		)

		_, err := agent.Run(context.Background(), []af.Message{
			af.NewUserMessage("hi"),
		})

		require.NoError(t, err)
		msgs := mock.captured.messages
		require.Len(t, msgs, 3)
		assert.Equal(t, af.RoleSystem, msgs[0].Role)
		assert.Equal(t, "You are helpful.", msgs[0].Text())
		assert.Equal(t, af.RoleSystem, msgs[1].Role)
		assert.Equal(t, "Be concise.", msgs[1].Text())
		assert.Equal(t, af.RoleUser, msgs[2].Role)
		assert.Equal(t, "hi", msgs[2].Text())
	})

	t.Run("applies default chat options", func(t *testing.T) {
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock,
			af.WithDefaultChatOptions(af.WithTemperature(0.3), af.WithModel("gpt-4o")),
		)

		_, err := agent.Run(context.Background(), []af.Message{
			af.NewUserMessage("hi"),
		})

		require.NoError(t, err)
		assert.InDelta(t, 0.3, *mock.captured.opts.Temperature, 0.001)
		assert.Equal(t, "gpt-4o", mock.captured.opts.Model)
	})

	t.Run("run options override default chat options", func(t *testing.T) {
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock,
			af.WithDefaultChatOptions(af.WithTemperature(0.3)),
		)

		_, err := agent.Run(context.Background(), []af.Message{
			af.NewUserMessage("hi"),
		}, af.WithChatOption(af.WithTemperature(0.9)))

		require.NoError(t, err)
		assert.InDelta(t, 0.9, *mock.captured.opts.Temperature, 0.001)
	})

	t.Run("propagates client error", func(t *testing.T) {
		clientErr := errors.New("api error")
		mock := &mockChatClient{err: clientErr}
		agent := af.NewAgent(mock)

		_, err := agent.Run(context.Background(), []af.Message{
			af.NewUserMessage("hi"),
		})

		assert.ErrorIs(t, err, clientErr)
	})

	t.Run("returns error for empty messages", func(t *testing.T) {
		agent := af.NewAgent(&mockChatClient{})

		_, err := agent.Run(context.Background(), nil)

		assert.ErrorIs(t, err, af.ErrEmptyMessages)
	})

	t.Run("returns error for empty messages slice", func(t *testing.T) {
		agent := af.NewAgent(&mockChatClient{})

		_, err := agent.Run(context.Background(), []af.Message{})

		assert.ErrorIs(t, err, af.ErrEmptyMessages)
	})
}
