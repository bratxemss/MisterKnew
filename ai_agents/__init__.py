import uuid
from typing import Sequence
from dotenv import find_dotenv, load_dotenv
from langchain_core.language_models import LanguageModelLike
from langchain_core.tools import BaseTool, tool
from langchain_core.messages import (
    AIMessage,
    ToolMessage,
    HumanMessage,
)
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from colorama import Fore, Style
import base64
from pathlib import Path

load_dotenv(find_dotenv())


@tool
def finish(message: str):
    """
    Call this function when you consider a task or dialog completed
    """
    return f"[FINISHED] {message}"

def encode_image_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

class LLMAgent:
    def __init__(self, name: str, model: LanguageModelLike, tools: Sequence[BaseTool]) -> None:
        self.name = name
        self._model = model
        self.default_tools = [finish]
        self._tools = list(tools) + self.default_tools
        self._agent = create_react_agent(
            model=model,
            tools=self._tools,
            checkpointer=InMemorySaver(),
        )
        self._config = {
            "configurable": {
                "thread_id": uuid.uuid4().hex,
                "recursion_limit": 100,
            }
        }

    def upload_file(self, file: str):
        file_uploaded_id = self._model.upload_file(file).id_
        return file_uploaded_id

    async def ainvoke(
            self,
            content: str,
            attachments: list[str] | None = None,
            temperature: float = 0.1,
            raw: bool = False,
            silent: bool = False,
    ) -> str | list:

        multimodal_content: list[dict] = [{"type": "text", "text": content}]

        if attachments:
            for file in attachments:
                path = Path(file)
                suffix = path.suffix.lower()
                try:
                    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                        image_b64 = encode_image_base64(file)
                        multimodal_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{suffix[1:]};base64,{image_b64}"
                            }
                        })
                    else:
                        # fallback: текстовая заглушка
                        multimodal_content.append({
                            "type": "text",
                            "text": f"[Unsupported attachment: {file}]"
                        })
                except Exception as e:
                    if not silent:
                        print(f"[!] Failed to attach file '{file}': {e}")

        messages = [HumanMessage(content=multimodal_content)]

        if not silent:
            print(f"\n{Fore.YELLOW}--- {self.name} ➔ INPUT ---{Style.RESET_ALL}")
            print(content)
            if attachments:
                for file in attachments:
                    print(f"[📎 Attachment]: {file}")

        final_output = None

        for step in range(50):
            input_dict = {"messages": messages}
            config = {
                **self._config,
                "configurable": {
                    **self._config.get("configurable", {}),
                    "temperature": temperature,
                }
            }

            result = await self._agent.ainvoke(input_dict, config=config)
            new_messages = result.get("messages", [])
            messages.extend(new_messages)

            ai_msg = next((m for m in reversed(new_messages) if isinstance(m, AIMessage)), None)

            if ai_msg and ai_msg.tool_calls:
                tool_messages = []

                for tool_call in ai_msg.tool_calls:
                    tool_name = tool_call.get("name")
                    tool_args = tool_call.get("args", {})
                    tool_call_id = tool_call.get("id")

                    tool = next((t for t in self._tools if t.name == tool_name), None)

                    if not tool:
                        tool_messages.append(ToolMessage(
                            tool_call_id=tool_call_id,
                            content=f"[ERROR] Tool '{tool_name}' not found."
                        ))
                        continue

                    try:
                        result = await tool.ainvoke(tool_args)
                        tool_messages.append(ToolMessage(
                            tool_call_id=tool_call_id,
                            name=tool.name,
                            content=result
                        ))
                        if tool.name == "finish":
                            final_output = result
                    except Exception as e:
                        tool_messages.append(ToolMessage(
                            tool_call_id=tool_call_id,
                            name=tool.name,
                            content=f"[ERROR] Tool execution failed: {str(e)}"
                        ))

                messages.extend(tool_messages)
            else:
                break

        if not silent:
            print(f"{Fore.CYAN}--- {self.name} ➔ OUTPUT ---{Style.RESET_ALL}")

        if raw:
            if not silent:
                for msg in messages:
                    if isinstance(msg, AIMessage):
                        print(f"[AI]: {msg.content}")
                    elif isinstance(msg, ToolMessage):
                        print(f"[Tool]: {msg.content}")
            return messages

        if final_output:
            if not silent:
                print(final_output)
            return final_output

        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                if not silent:
                    print(msg.content)
                return msg.content
            if isinstance(msg, AIMessage) and msg.content:
                if not silent:
                    print(msg.content)
                return msg.content

        if not silent:
            print("[!] No useful output found.")
        return "Ошибка: Не найдено подходящее сообщение с текстом."

    def invoke(
        self,
        content: str,
        attachments: list[str] | None = None,
        temperature: float = 0.1,
    ) -> str:
        import asyncio
        return asyncio.run(self.ainvoke(content, attachments, temperature))
