from packages.core.evals import GenAIEval, AgentEvaluation, RedTeamAgent
from packages.core.agents import SimpleGenAgent  # hypothetical agent

agent = SimpleGenAgent()
eval_prompts = ["Hello", "Tell me a joke", "What's the weather?"]
gen_eval = GenAIEval()
print(gen_eval.evaluate(agent, eval_prompts))

test_cases = [{"input": "3+2", "expected_output": "5"}]
agent_eval = AgentEvaluation()
print(agent_eval.evaluate(agent, test_cases))

redteam = RedTeamAgent()
print(redteam.run_against(agent))
