import asyncio

from ai_agents.advance_ai_agent import AiAgentWorker
from communicator import Communicator
from typing import List, Dict
from langchain_core.tools import tool
from utils import log_return
from logging_folder import get_logger
log = get_logger(__name__)

prefixes_for_manager = [
    "manager",
    "supervisor",
    "controller",
    "coordinator",
    "director",
    "operator",
    "monitor",
    "overseer",
    "observer",
    "lead",
    "orchestrator",
    "moderator",
    "governor",
    "handler",
    "dispatcher",
    "facilitator",
    "executor",
    "planner",
    "strategist",
    "watcher",
    "conductor",
    "chief",
    "inspector",
    "scheduler",
    "initiator",
    "misterknew",
]

class Operator:
    def __init__(self, agents_list:List[AiAgentWorker]):
        self.raw_agent_list:List[AiAgentWorker]= agents_list

        self.worker_agents:List[AiAgentWorker] = []
        self.manager_agents:List[AiAgentWorker] = []

        self.manager_communications = {}
        self.worker_communications = {}

        self.active_agents:List[AiAgentWorker] = []
        self.passive_agents = self.raw_agent_list.copy()

        self.__rebuild_lists()

    def __rebuild_lists(self):
        try:
            self.__sorting()
            self.__communicate_configure()
        except Exception as ex:
            log.error(f"Error while rebuilding operator: {ex}")

    def __sorting(self):
        for agent in self.raw_agent_list:
            for key_word in prefixes_for_manager:
                if key_word.lower() in agent.name.lower():
                    self.manager_agents.append(agent)
                    continue
            else:
                self.worker_agents.append(agent)

    def __communicate_configure(self):
        for agent in self.manager_agents:
            temporary_manager_agents_list = self.manager_agents.copy()
            temporary_manager_agents_list.remove(agent)
            communicator = Communicator(agent, self.worker_agents + temporary_manager_agents_list)
            self.manager_communications[agent] = communicator
        for agent in self.worker_agents:
            communicator = Communicator(agent, self.manager_agents)
            self.worker_communications[agent] = communicator

    def add_agent(self, agent:AiAgentWorker):
        try:
            self.raw_agent_list.append(agent)
            self.passive_agents.append(agent)
            self.__rebuild_lists()
            return True
        except Exception as ex:
            log.error(f"Error in adding agent:{agent.name} to operator. Error: {ex}")
            return False

    def remove_agent(self, agent:AiAgentWorker):
        try:
            self.raw_agent_list.remove(agent)
            if agent in self.manager_agents:
                self.manager_agents.remove(agent)
            elif agent in self.worker_agents:
                self.worker_agents.remove(agent)

            if agent in self.manager_communications:
                self.manager_communications.pop(agent)
            elif agent in self.worker_communications:
                self.worker_communications.pop(agent)
            self.__rebuild_lists()
            return True
        except Exception as ex:
            log.error(f"Error in removing agent:{agent.name} from operator. Error: {ex}")
            return False

    def remove_agent_by_name(self, agent_name:str):
        agent_to_remove = [agent for agent in self.raw_agent_list if agent.name == agent_name][0]
        if agent_to_remove:
            return self.remove_agent(agent_to_remove)

    async def activate_agent(self, agent:AiAgentWorker, attachments:List[str]=None):
        try:
            if agent in self.active_agents:
                return log.info(f"agent:{agent.name} already active")
            if agent not in self.passive_agents:
                return log.error(f"agent:{agent.name} not exist in Operator")
            if await agent.ainvoke(content=agent.prompt, silent=True, attachments=attachments):
                self.passive_agents.remove(agent)
                self.active_agents.append(agent)
                return True
            else:
                return False
        except Exception as ex:
            log.error(f"agent:{agent.name} cant be activate. Error:{ex}")
            return False

    async def active_agent_by_name(self, agent_name:str):
        agent_to_add = [agent for agent in self.raw_agent_list if agent.name == agent_name][0]
        if agent_to_add:
            return await self.activate_agent(agent_to_add)

    async def activate_all(self, attachments:Dict[AiAgentWorker, List[str]]=None):
        try:
            tasks = []
            for agent in self.passive_agents:
                if not attachments:
                    attachments = {}
                tasks.append(agent.ainvoke(content=agent.prompt, silent=True, attachments=attachments.get(agent)))
                self.active_agents.append(agent)
                log.info(f'agent: {agent.name} activation')
            self.passive_agents.clear()
            await asyncio.gather(*tasks)
            return True
        except Exception as ex:
            log.error(f"Cant activate all agents: Error:{ex}")
            return False

    def make_create_agents_for_work(self):
        @tool
        @log_return
        async def create_agents_for_work(agents: List[Dict], main_task:str):
            """
            :param main_task: main task from user
            :param agents: List which contains dicts where 'name' - name of agent, 'task' - task of agent, 'job' - job of agent: system_worker/web_worker/manager
            :return:
            """
            try:
                list_of_agents = []
                for agent in agents:
                    name = agent.get('name')
                    task = agent.get('task')
                    job = agent.get('job')
                    tools = []
                    if not name or not task or not job:
                        return "Error: wrong format of agent dict! Example of agent: {'name': 'example', 'task': 'do example'},'job': 'system_worker'|'web_worker'|'manager'"
                    if job:
                        if job == 'manager':
                            tools = self.manager_agents[0]._tools
                        elif job == "system_worker":
                            for agent in self.worker_agents:
                                if agent.name.startswith('os') or agent.name.startswith('system'):
                                    tools = agent._tools
                                    break
                        elif job == "web_worker":
                            for agent in self.worker_agents:
                                if agent.name.startswith('web') or agent.name.startswith('interner') or agent.name.startswith('browser'):
                                    tools = agent._tools
                                    break
                    new_agent = AiAgentWorker(name,tools,main_task=main_task,local_task=task)
                    list_of_agents.append(new_agent)
                for agent in list_of_agents:
                    self.add_agent(agent)
                await self.activate_all()
                return "agents was successfully added, use 'get_known_agents' for get list of them"
            except Exception as ex:
                return f"Error while creating agents:{ex}"
        return create_agents_for_work