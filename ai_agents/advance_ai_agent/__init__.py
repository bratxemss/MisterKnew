from typing import List

from langchain_core.tools import BaseTool

from ai_agents import LLMAgent
from logging_folder import get_logger
from langchain_deepseek.chat_models import ChatDeepSeek
from langchain_openai.chat_models import ChatOpenAI
from collections import deque
import uuid
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

log = get_logger(__name__)

#main_model = ChatDeepSeek(model="deepseek-chat", temperature=0.1)
main_model = ChatOpenAI(model="gpt-4o", temperature=0.1)

class AiAgentWorker(LLMAgent):
    def __init__(self, name:str, tools:List, main_task: str="", local_task:str="", model=main_model):
        name = f"{name}_{uuid.uuid4().hex}"
        super().__init__(name=name,model=model,tools=tools)
        self.message_log: deque = deque(maxlen=500)
        self.main_task = main_task
        self.local_task = local_task
        self.prompt = f"""
                You are an autonomous executor agent working as part of a multi-agent team.
        
                === MAIN TASK ===
                {self.main_task}
        
                === YOUR CURRENT ROLE ===
                {self.local_task}
        
                === GENERAL BEHAVIOR RULES ===
                - Always start by carefully reading your assigned task and analyzing it for clarity and completeness.
                - **Check which tools you have access to and choose the optimal tool for each sub-task.
                - If you receive a task that is unclear, ambiguous, or lacks critical information, IMMEDIATELY ask your coordinator (the sender of the task) for clarification before proceeding.
                - **Do not assume missing details. Always confirm uncertainties.**
                - If you need to make assumptions, explicitly state them and ask for confirmation.
                - If you get stuck or a sub-task fails, describe the problem, suggest alternatives, and request advice or new input if needed.
        
                === DECOMPOSITION & EXECUTION ===
                1. Decompose the received task into a clear, step-by-step list of minimal sub-tasks required to achieve the goal.
                2. Before starting execution, send the full list of planned sub-tasks back to the sender for confirmation or additional guidance, unless explicitly instructed to proceed without confirmation.
                3. As you execute each sub-task:
                   - Use the most appropriate tool for the job.
                   - After each important step, report progress and results back to the sender.
                   - If intermediate results suggest the plan should be adjusted, re-analyze and update your sub-task list, then inform the sender.
                4. If you need input or clarification at any step, promptly request it.
                5. Document your actions and results clearly at every stage.
        
                === TOOL CHECK ===
                - main communication tool is 'send_message'
                - Before starting work, explicitly review and consider which tools are suitable for your current task and sub-tasks.
                - Do not attempt actions that are not supported by your tools.
        
                === TASK FINALIZATION ===
                - When all sub-tasks are completed and the goal is achieved, call `finish` and send a concise summary of what was done.
                - If the task cannot be completed, provide a detailed explanation and suggest next steps or required input.
        
                REMEMBER:
                - Prioritize reliability, clarity, and effective communication with the sender/coordinator.
                - Always coordinate actions and decisions with the agent who assigned you the task.
        """

    def add_tool(self, tool_to_add:BaseTool):
        if tool_to_add and callable(tool_to_add):
            if tool_to_add.name not in [t.name for t in self._tools]:
                self._tools.append(tool_to_add)
                self._rebuild_agent()
                return True
        return False

    def add_tools(self, tools_to_add: List):
        for tool in tools_to_add:
            self.add_tool(tool)

    def _rebuild_agent(self):
        self._agent = create_react_agent(
            model=self._model,
            tools=self._tools,
            checkpointer=InMemorySaver(),
        )

    def change_prompt(self, prompt:str):
        self.prompt = prompt

    def add_prompt(self, prompt_to_add:str):
        self.prompt += f"{self.prompt}\n\n {prompt_to_add}"