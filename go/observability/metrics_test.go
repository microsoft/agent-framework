package observability_test

import (
	"context"
	"testing"

	af "github.com/microsoft/agent-framework/go"
	"github.com/microsoft/agent-framework/go/observability"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

func setupMeter() (*sdkmetric.MeterProvider, *sdkmetric.ManualReader) {
	reader := sdkmetric.NewManualReader()
	mp := sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader))
	return mp, reader
}

func collectMetrics(t *testing.T, reader *sdkmetric.ManualReader) metricdata.ResourceMetrics {
	t.Helper()
	var rm metricdata.ResourceMetrics
	err := reader.Collect(context.Background(), &rm)
	require.NoError(t, err)
	return rm
}

func findMetric(rm metricdata.ResourceMetrics, name string) *metricdata.Metrics {
	for _, sm := range rm.ScopeMetrics {
		for i := range sm.Metrics {
			if sm.Metrics[i].Name == name {
				return &sm.Metrics[i]
			}
		}
	}
	return nil
}

func TestMetricsChatMiddleware(t *testing.T) {
	t.Run("records duration and token usage", func(t *testing.T) {
		mp, reader := setupMeter()
		defer mp.Shutdown(context.Background())

		mw := observability.NewMetricsChatMiddleware(mp)
		mock := &mockChatClient{
			response: &af.ChatResponse{
				Messages: []af.Message{af.NewTextMessage(af.RoleAssistant, "ok")},
				Usage:    &af.UsageDetails{InputTokens: 10, OutputTokens: 5, TotalTokens: 15},
			},
		}
		agent := af.NewAgent(mock, af.WithChatMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		require.NoError(t, err)

		rm := collectMetrics(t, reader)
		assert.NotNil(t, findMetric(rm, "gen_ai.client.operation.duration"), "duration metric should be recorded")
		assert.NotNil(t, findMetric(rm, "gen_ai.client.token.usage"), "token usage metric should be recorded")
	})

	t.Run("records error count on failure", func(t *testing.T) {
		mp, reader := setupMeter()
		defer mp.Shutdown(context.Background())

		mw := observability.NewMetricsChatMiddleware(mp)
		mock := &mockChatClient{err: assert.AnError}
		agent := af.NewAgent(mock, af.WithChatMiddleware(mw))
		_, err := agent.Run(context.Background(), []af.Message{af.NewUserMessage("hi")})
		assert.Error(t, err)

		rm := collectMetrics(t, reader)
		assert.NotNil(t, findMetric(rm, "gen_ai.client.error.count"), "error count metric should be recorded")
	})
}
