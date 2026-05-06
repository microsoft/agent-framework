package agentframework_test

import (
	"context"
	"errors"
	"testing"

	af "github.com/microsoft/agent-framework/go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestAgentMiddlewareChain(t *testing.T) {
	t.Run("single middleware wraps agent run", func(t *testing.T) {
		var order []string
		mw := af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
			order = append(order, "before")
			err := next(ctx, ac)
			order = append(order, "after")
			return err
		})
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock, af.WithAgentMiddleware(mw))
		resp, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.Equal(t, "ok", resp.Messages[0].Text())
		assert.Equal(t, []string{"before", "after"}, order)
	})

	t.Run("middleware chain executes in order", func(t *testing.T) {
		var order []string
		mw1 := af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
			order = append(order, "mw1-before")
			err := next(ctx, ac)
			order = append(order, "mw1-after")
			return err
		})
		mw2 := af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
			order = append(order, "mw2-before")
			err := next(ctx, ac)
			order = append(order, "mw2-after")
			return err
		})
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock, af.WithAgentMiddleware(mw1, mw2))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.Equal(t, []string{"mw1-before", "mw2-before", "mw2-after", "mw1-after"}, order)
	})

	t.Run("middleware can short-circuit by not calling next", func(t *testing.T) {
		mw := af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
			ac.Response = &af.AgentResponse{
				ChatResponse: af.ChatResponse{
					Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "cached")},
				},
				AgentID: ac.Agent.ID(),
			}
			return nil
		})
		mock := &mockChatClient{}
		agent := af.NewAgent(mock, af.WithAgentMiddleware(mw))
		resp, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.Equal(t, "cached", resp.Messages[0].Text())
	})

	t.Run("middleware can return error to stop chain", func(t *testing.T) {
		expectedErr := errors.New("middleware error")
		mw := af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
			return expectedErr
		})
		mock := &mockChatClient{}
		agent := af.NewAgent(mock, af.WithAgentMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		assert.ErrorIs(t, err, expectedErr)
	})

	t.Run("middleware reads agent context", func(t *testing.T) {
		var capturedName string
		var capturedMsgCount int
		mw := af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
			capturedName = ac.Agent.Name()
			capturedMsgCount = len(ac.Messages)
			return next(ctx, ac)
		})
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock, af.WithName("TestBot"), af.WithAgentMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.Equal(t, "TestBot", capturedName)
		assert.Equal(t, 1, capturedMsgCount)
	})

	t.Run("no middleware — agent works normally", func(t *testing.T) {
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock)
		resp, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.Equal(t, "ok", resp.Messages[0].Text())
	})
}

func TestChatMiddlewareChain(t *testing.T) {
	t.Run("chat middleware wraps client call", func(t *testing.T) {
		var order []string
		chatMw := af.ChatMiddlewareFunc(func(ctx context.Context, cc *af.ChatContext, next af.ChatHandler) error {
			order = append(order, "chat-before")
			err := next(ctx, cc)
			order = append(order, "chat-after")
			return err
		})
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock, af.WithChatMiddleware(chatMw))
		resp, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.Equal(t, "ok", resp.Messages[0].Text())
		assert.Equal(t, []string{"chat-before", "chat-after"}, order)
	})

	t.Run("chat middleware can modify options before call", func(t *testing.T) {
		chatMw := af.ChatMiddlewareFunc(func(ctx context.Context, cc *af.ChatContext, next af.ChatHandler) error {
			temp := 0.42
			cc.Options.Temperature = &temp
			return next(ctx, cc)
		})
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock, af.WithChatMiddleware(chatMw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.InDelta(t, 0.42, *mock.captured.opts.Temperature, 0.001)
	})

	t.Run("chat middleware can read response after call", func(t *testing.T) {
		var capturedResponseID string
		chatMw := af.ChatMiddlewareFunc(func(ctx context.Context, cc *af.ChatContext, next af.ChatHandler) error {
			err := next(ctx, cc)
			if cc.Response != nil {
				capturedResponseID = cc.Response.ResponseID
			}
			return err
		})
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages:   []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
				ResponseID: "resp-42",
			},
		}
		agent := af.NewAgent(mock, af.WithChatMiddleware(chatMw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.Equal(t, "resp-42", capturedResponseID)
	})

	t.Run("agent and chat middleware compose", func(t *testing.T) {
		var order []string
		agentMw := af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
			order = append(order, "agent-before")
			err := next(ctx, ac)
			order = append(order, "agent-after")
			return err
		})
		chatMw := af.ChatMiddlewareFunc(func(ctx context.Context, cc *af.ChatContext, next af.ChatHandler) error {
			order = append(order, "chat-before")
			err := next(ctx, cc)
			order = append(order, "chat-after")
			return err
		})
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
			},
		}
		agent := af.NewAgent(mock,
			af.WithAgentMiddleware(agentMw),
			af.WithChatMiddleware(chatMw),
		)
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)
		assert.Equal(t, []string{"agent-before", "chat-before", "chat-after", "agent-after"}, order)
	})
}
