from ai_agents.advance_ai_agent import AiAgentWorker
from typing import List
from langchain_core.tools import BaseTool, tool
from logging_folder import get_logger

log = get_logger(__name__)

class Communicator:
    def __init__(self, agent:AiAgentWorker, visible_agents:List[AiAgentWorker]):
        self.agent = agent
        self.visible_agents = visible_agents
        self._register_tools()

    def add_visible_agent(self, agent:AiAgentWorker):
        self.visible_agents.append(agent)

    def remove_visible_agent(self, agent_to_remove:AiAgentWorker):
        self.visible_agents.remove(agent_to_remove)

    def remove_visible_agent_by_name(self, agent_to_remove_name:str):
        agent_to_remove = [agent for agent in self.visible_agents if agent.name == agent_to_remove_name][0]
        self.remove_visible_agent(agent_to_remove)

    def _register_tools(self):
        existing_tool_names = {tool.name for tool in self.agent._tools}

        get_tool = self.make_get_known_agents_tool()
        if get_tool.name not in existing_tool_names:
            self.agent.add_tool(get_tool)

        send_tool = self.make_send_message_tool()
        if send_tool.name not in existing_tool_names:
            self.agent.add_tool(send_tool)

    def make_get_known_agents_tool(self) -> BaseTool:
        @tool
        def get_known_agents() -> str:
            """
            Returns a comma-separated list of known agents, excluding the current agent.

            Returns:
                A string listing known agent names or an error message.
            """
            try:
                known = [str(name.name) for name in self.visible_agents]
                return ", ".join(known) if known else "No known agents."
            except Exception as e:
                return f"get_known_agents error: {str(e)}"

        return get_known_agents

    def make_send_message_tool(self) -> BaseTool:
        @tool
        async def send_message(to: str, type: str, message: str) -> str:
            """
            Sends a message from the current agent to another agent.

            Args:
                to: The name of the agent to send the message to.
                message: The message content.
                type: The type oc message TASK/QUESTION/RESULT

            Returns:
                Response from the receiving agent or error message.
            """
            try:
                from_agent = self.agent
                to_agent = [agent for agent in self.visible_agents if to == agent.name][0]
                if from_agent == to_agent:
                    return f"[{from_agent}] Skipped self-message."

                log.info(f"[{type}]{from_agent.name} → {to_agent.name}: {message}")

                response = await to_agent.ainvoke(
                    f"Сообщение: [{type}]{from_agent}: {message}", silent=True
                )

                log.info(f"response [{to_agent.name}] → {from_agent.name}: {response}")

                return f"[{to_agent.name}] → {from_agent.name}:\n{response}"
            except Exception as e:
                return f"send_message error: {str(e)}"

        return send_message
