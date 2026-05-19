package observability_test

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"testing"

	af "github.com/microsoft/agent-framework/go"
	"github.com/microsoft/agent-framework/go/observability"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func parseLogLines(t *testing.T, data []byte) []map[string]any {
	t.Helper()
	var lines []map[string]any
	for _, line := range bytes.Split(data, []byte("\n")) {
		if len(line) == 0 {
			continue
		}
		var m map[string]any
		require.NoError(t, json.Unmarshal(line, &m))
		lines = append(lines, m)
	}
	return lines
}

func TestLoggingAgentMiddleware(t *testing.T) {
	t.Run("logs agent run at info level", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo}))

		mw := observability.NewLoggingAgentMiddleware(logger)
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
				Usage:    &af.UsageDetails{InputTokens: 10, OutputTokens: 5, TotalTokens: 15},
			},
		}
		agent := af.NewAgent(mock, af.WithName("TestBot"), af.WithAgentMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)

		lines := parseLogLines(t, buf.Bytes())
		require.GreaterOrEqual(t, len(lines), 1)

		found := false
		for _, line := range lines {
			if msg, ok := line["msg"].(string); ok && msg == "agent run completed" {
				found = true
				assert.Equal(t, "TestBot", line["agent.name"])
				assert.Equal(t, "INFO", line["level"])
				break
			}
		}
		assert.True(t, found, "expected 'agent run completed' log line")
	})

	t.Run("logs error at error level", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo}))

		mw := observability.NewLoggingAgentMiddleware(logger)
		mock := &mockChatClient{err: assert.AnError}
		agent := af.NewAgent(mock, af.WithName("FailBot"), af.WithAgentMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		assert.Error(t, err)

		lines := parseLogLines(t, buf.Bytes())
		found := false
		for _, line := range lines {
			if msg, ok := line["msg"].(string); ok && msg == "agent run failed" {
				found = true
				assert.Equal(t, "ERROR", line["level"])
				assert.Equal(t, "FailBot", line["agent.name"])
				break
			}
		}
		assert.True(t, found, "expected 'agent run failed' log line")
	})
}
