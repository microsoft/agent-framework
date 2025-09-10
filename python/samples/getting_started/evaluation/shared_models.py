from azure.ai.projects.models import Message

class AgentFrameworkMessage(Message):
    type: str = "message"
