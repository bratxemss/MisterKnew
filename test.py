import asyncio
from ai_agents.advance_ai_agent import AiAgentWorker
from ai_agents_operator import Operator
from ai_agents.tools.win_tools import *
from ai_agents.tools.web_tools import *
from langchain_openai.chat_models import ChatOpenAI
from utils.llm_utils import run_once_agent

async def main():
    system_prompt = (
        "what on the image?"
    )

    main_model = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    worker = AiAgentWorker("MisterKnew", tools=[], model=main_model)

    worker.add_prompt(system_prompt)
    answer = await run_once_agent(model=main_model,command=system_prompt,tools=[],attachments=['img.png'],name='img_worker_1',silent=False)
    return answer

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(" Завершено пользователем")