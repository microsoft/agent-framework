from agent import agent
from agent_framework.devui import serve


serve(
	entities=[agent],
	auto_open=True,
	auth_enabled=True,
	instrumentation_enabled=True,
	mode="developer",
)
