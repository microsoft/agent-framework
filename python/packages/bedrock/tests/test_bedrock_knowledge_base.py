"""Tests for Bedrock Knowledge Base tool and context provider."""

from unittest.mock import MagicMock


class TestBedrockKnowledgeBaseTool:
    def test_run_returns_results(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": "Doc"}, "location": {"s3Location": {"uri": "s3://b/d"}}, "score": 0.9},
            ]
        }
        mock_client.agentic_retrieve_stream.side_effect = Exception("not available")
        tool = BedrockKnowledgeBaseTool(knowledge_base_id="TEST123")
        tool._client = mock_client
        import asyncio

        results = asyncio.run(tool.run(query="test"))
        assert len(results) == 1
        assert results[0]["content"] == "Doc"

    def test_managed_config_default(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {"retrievalResults": []}
        mock_client.agentic_retrieve_stream.side_effect = Exception("not available")
        tool = BedrockKnowledgeBaseTool(knowledge_base_id="TEST123")
        tool._client = mock_client
        import asyncio

        asyncio.run(tool.run(query="test"))
        call_kwargs = mock_client.retrieve.call_args.kwargs
        assert "managedSearchConfiguration" in call_kwargs["retrievalConfiguration"]

    def test_get_tool_definition(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        tool = BedrockKnowledgeBaseTool(knowledge_base_id="TEST123")
        defn = tool.get_tool_definition()
        assert defn["name"] == "bedrock_knowledge_base"
        assert "query" in defn["parameters"]["properties"]


class TestBedrockKnowledgeBaseProvider:
    def test_init(self):
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        provider = BedrockKnowledgeBaseProvider(
            source_id="test-kb",
            knowledge_base_id="TEST123",
            region_name="us-west-2",
        )
        assert provider.source_id == "test-kb"
        assert provider.knowledge_base_id == "TEST123"

    def test_retrieve_returns_passages(self):
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": "Context doc"}, "location": {"s3Location": {"uri": "s3://b/c"}}, "score": 0.9},
            ]
        }
        provider = BedrockKnowledgeBaseProvider(knowledge_base_id="TEST123")
        provider._client = mock_client
        import asyncio

        passages = asyncio.run(provider._retrieve("test query"))
        assert len(passages) == 1
        assert passages[0]["content"] == "Context doc"
