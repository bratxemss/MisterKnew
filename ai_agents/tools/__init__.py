# from typing import List, Dict
# import json
# import asyncio
# from langchain_core.tools import BaseTool, tool
# from thinking_process.operator import OperatorWorker
# from utils import log_return
# from typing import Annotated
#
#
#
# @tool
# @log_return
# def easy(message:str):
#     """
#     :param message: LLM answer
#     :return: LLM answer
#     """
#     return message
#
#
# @tool
# @log_return
# async def hard(agents: List[Dict], task:str, root_for_work:str):
#     """
#     Perform a hard task using a list of agent data.
#
#
#     :param agents: A list of dictionaries, each with keys:
#                    - 'job': description of what to do on english
#                    - 'name': unique name of the agent
#     :param task: main task from user
#     :param root_for_work: root directory for work in project should be child of C:\\Users\\bratx\\Desktop\\MisterKnewData
#     :return: A string describing the task and agents involved.
#     """
#     operator = OperatorWorker(task)
#     # if len(agents) > 2:
#     #     operator.create_coordinator(root_for_work)
#     # if len(agents) >= 5:
#     #     operator.create_main_data_tester(root_for_work)
#
#     for agent in agents:
#         operator.create_agent(agent.get('name'), agent.get('job'), root_for_work)
#     await operator.activate_all_agents()
#     if agents:
#         return json.dumps({
#             "status": "accepted",
#             "message": f"Task delegated to {len(agents)} agents",
#             "agents": agents
#         })
#     else:
#         return json.dumps({
#             "status": "rejected",
#             "message": f"amount of agents cant be 0",
#             "agents": agents
#         })
#
#
