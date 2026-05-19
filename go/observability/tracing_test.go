package observability_test

import (
	"context"
	"testing"

	af "github.com/microsoft/agent-framework/go"
	"github.com/microsoft/agent-framework/go/observability"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

type mockChatClient struct {
	response *af.ChatResponse
	err      error
}

func (m *mockChatClient) GetResponse(_ context.Context, _ []af.Message, _ ...af.ChatOption) (*af.ChatResponse, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.response, nil
}

func setupTracer() (*sdktrace.TracerProvider, *tracetest.InMemoryExporter) {
	exporter := tracetest.NewInMemoryExporter()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	return tp, exporter
}

func spanAttrMap(span tracetest.SpanStub) map[string]string {
	m := make(map[string]string)
	for _, attr := range span.Attributes {
		m[string(attr.Key)] = attr.Value.Emit()
	}
	return m
}

func TestTracingAgentMiddleware(t *testing.T) {
	t.Run("creates a span for agent run", func(t *testing.T) {
		tp, exporter := setupTracer()
		defer tp.Shutdown(context.Background())

		mw := observability.NewTracingAgentMiddleware(tp)
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
				Usage:    &af.UsageDetails{InputTokens: 10, OutputTokens: 5, TotalTokens: 15},
			},
		}
		agent := af.NewAgent(mock, af.WithName("TestBot"), af.WithAgentMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)

		spans := exporter.GetSpans()
		require.Len(t, spans, 1)
		assert.Equal(t, "agent.run", spans[0].Name)
		attrs := spanAttrMap(spans[0])
		assert.Equal(t, "TestBot", attrs["gen_ai.agent.name"])
	})

	t.Run("records error on span when agent fails", func(t *testing.T) {
		tp, exporter := setupTracer()
		defer tp.Shutdown(context.Background())

		mw := observability.NewTracingAgentMiddleware(tp)
		mock := &mockChatClient{err: assert.AnError}
		agent := af.NewAgent(mock, af.WithAgentMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		assert.Error(t, err)

		spans := exporter.GetSpans()
		require.Len(t, spans, 1)
		assert.NotEmpty(t, spans[0].Events)
	})
}

func TestTracingChatMiddleware(t *testing.T) {
	t.Run("creates a span for chat client call", func(t *testing.T) {
		tp, exporter := setupTracer()
		defer tp.Shutdown(context.Background())

		mw := observability.NewTracingChatMiddleware(tp)
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
				Usage:    &af.UsageDetails{InputTokens: 10, OutputTokens: 5, TotalTokens: 15},
			},
		}
		agent := af.NewAgent(mock, af.WithChatMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)

		spans := exporter.GetSpans()
		require.Len(t, spans, 1)
		assert.Equal(t, "chat.get_response", spans[0].Name)
		attrs := spanAttrMap(spans[0])
		assert.Equal(t, "10", attrs["gen_ai.usage.input_tokens"])
		assert.Equal(t, "5", attrs["gen_ai.usage.output_tokens"])
	})
}
