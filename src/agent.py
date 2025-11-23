# src/agent.py
try:
    from langchain.agents import create_react_agent, AgentExecutor
except ImportError:
    from langchain.agents import AgentExecutor
    from langchain.agents.react.agent import create_react_agent

from langchain.memory import ConversationBufferWindowMemory
from langchain.tools.render import render_text_description # Import this

from src.llm_interface import get_llm
from src.tools import get_all_tools
from src.retriever import HybridRetriever
from src.prompts import CONVERSATIONAL_REACT_PROMPT # This is your base prompt template
import config
from typing import Dict, Any

class LegalAgentFR:
    def __init__(self, retriever: HybridRetriever):
        self.llm = get_llm(model_name=config.AGENT_LLM_MODEL)
        self.tools = get_all_tools(retriever) # List of Tool objects
        
        # 1. Prepare the prompt with tool information
        # The CONVERSATIONAL_REACT_PROMPT already has a placeholder for tool_names.
        # Let's ensure the prompt is formatted with the actual tool names and descriptions
        # if create_react_agent doesn't do it automatically with CONVERSATIONAL_REACT_PROMPT.

        # The create_react_agent function *should* handle injecting tool names and descriptions
        # if the prompt has the correct placeholders.
        # The error "Prompt missing required variables: {'tools'}" suggests that the
        # CONVERSATIONAL_REACT_PROMPT, when passed to create_react_agent, isn't being
        # fully resolved with the 'tools' variable by the function itself.

        # Let's ensure the base prompt template (REACT_AGENT_SYSTEM_PROMPT)
        # also has a placeholder for the full tool descriptions if needed, or simplify.
        # The default ReAct prompt in LangChain often has a section like:
        # "You have access to the following tools:\n{tools}\n\nUse the following format:..."

        # Our current REACT_AGENT_SYSTEM_PROMPT in src/prompts.py has:
        # "Action: L'outil à utiliser, parmi [{tool_names}]."
        # It does *not* have a placeholder for the full {tools} descriptions.
        # This is likely the core issue.

        # We need to modify REACT_AGENT_SYSTEM_PROMPT in src/prompts.py

        self.agent_prompt = CONVERSATIONAL_REACT_PROMPT # This is a ChatPromptTemplate

        # 2. Create the agent instance
        agent_instance = create_react_agent(
            llm=self.llm,
            tools=self.tools, # Pass the list of Tool objects
            prompt=self.agent_prompt # Pass the ChatPromptTemplate
        )

        # Initialize memory
        self.memory = ConversationBufferWindowMemory(
            k=5,
            memory_key="chat_history",
            return_messages=True
        )

        # Create the Agent Executor
        self.agent_executor = AgentExecutor(
            agent=agent_instance,
            tools=self.tools,
            verbose=True,
            max_iterations=config.AGENT_MAX_ITERATIONS,
            handle_parsing_errors=True,
            memory=self.memory
        )
        
        print(f"Agent Juridique (LegalAgentFR) initialisé en français avec {len(self.tools)} outils.")

    def run(self, query: str) -> Dict[str, Any]:
        print(f"\nL'agent (LegalAgentFR) a reçu la requête: '{query}'")
        try:
            response = self.agent_executor.invoke({"input": query})
            answer = response.get("output", "Aucune sortie spécifique trouvée de l'agent.")
            return {"answer": answer, "sources": "Les sources devraient être incluses dans la réponse de l'agent si applicable."}
        
        except Exception as e:
            print(f"Erreur durant l'exécution de l'agent (LegalAgentFR): {e}")
            error_message = f"Une erreur est survenue lors du traitement de votre requête : {str(e)}"
            return {"answer": error_message, "sources": []}