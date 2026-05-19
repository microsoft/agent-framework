package observability

import (
	"context"
	"time"

	af "github.com/microsoft/agent-framework/go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

func NewMetricsChatMiddleware(mp metric.MeterProvider) af.ChatMiddleware {
	meter := mp.Meter("agentframework")
	duration, _ := meter.Float64Histogram("gen_ai.client.operation.duration",
		metric.WithUnit("s"),
		metric.WithDescription("Duration of chat client operations"),
	)
	tokenUsage, _ := meter.Int64Counter("gen_ai.client.token.usage",
		metric.WithDescription("Token usage by type"),
	)
	errorCount, _ := meter.Int64Counter("gen_ai.client.error.count",
		metric.WithDescription("Count of chat client errors"),
	)

	return af.ChatMiddlewareFunc(func(ctx context.Context, cc *af.ChatContext, next af.ChatHandler) error {
		start := time.Now()
		var attrs []attribute.KeyValue
		if cc.Options != nil && cc.Options.Model != "" {
			attrs = append(attrs, attribute.String("gen_ai.request.model", cc.Options.Model))
		}

		err := next(ctx, cc)
		elapsed := time.Since(start).Seconds()
		duration.Record(ctx, elapsed, metric.WithAttributes(attrs...))

		if err != nil {
			errorCount.Add(ctx, 1, metric.WithAttributes(attrs...))
			return err
		}

		if cc.Response != nil && cc.Response.Usage != nil {
			tokenUsage.Add(ctx, int64(cc.Response.Usage.InputTokens),
				metric.WithAttributes(append(attrs, attribute.String("gen_ai.token.type", "input"))...),
			)
			tokenUsage.Add(ctx, int64(cc.Response.Usage.OutputTokens),
				metric.WithAttributes(append(attrs, attribute.String("gen_ai.token.type", "output"))...),
			)
		}
		return nil
	})
}
