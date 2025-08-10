import uuid
import asyncio
from typing import Optional, Sequence

from langchain_core.language_models import LanguageModelLike
from langchain_core.tools import BaseTool

from ai_agents import LLMAgent

async def run_once_agent(
    model: LanguageModelLike,
    command: str,
    tools: Optional[Sequence[BaseTool]] = None,
    attachments: Optional[list[str]] = None,
    name: Optional[str] = None,
    temperature: float = 0.1,
    silent: bool = False,
) -> str:
    """
    Creates a one-time agent, runs it for one command, and deletes it.

    :param model: LLM (for example, ChatOpenAI(...))
    :param command: text command
    :param tools: list of tools (by default only `finish`)
    :param attachments: list of file paths (text or images)
    :param name: agent name (if not specified - generated)
    :param temperature: generation temperature
    :param silent: output suppression
    :return: response string from agent
    """
    agent_name = name or f"OneShotAgent_{uuid.uuid4().hex[:8]}"
    agent = LLMAgent(name=agent_name, model=model, tools=tools or [])

    result = await agent.ainvoke(
        content=command,
        attachments=attachments,
        temperature=temperature,
        silent=silent,
    )

    del agent
    return result