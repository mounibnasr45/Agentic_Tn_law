# src/agent.py
import sys

# Deterministic import strategy for LangChain agents
try:
    # Try the modern path (LangChain 0.2/0.3+)
    from langchain.agents.react.agent import create_react_agent
    from langchain.agents.agent import AgentExecutor
    USE_LEGACY_AGENT = False
except ImportError:
    try:
        # Try the intermediate path (LangChain 0.1.x)
        from langchain.agents import create_react_agent, AgentExecutor
        USE_LEGACY_AGENT = False
    except ImportError:
        # Fallback to legacy path (LangChain < 0.1.0)
        from langchain.agents import initialize_agent, AgentType, AgentExecutor
        USE_LEGACY_AGENT = True
        print("WARNING: Using legacy initialize_agent due to import failures.")

from langchain.memory import ConversationBufferWindowMemory
from langchain.tools.render import render_text_description 

from src.llm_interface import get_llm
from src.tools import get_all_tools
from src.retriever import HybridRetriever
from src.prompts import CONVERSATIONAL_REACT_PROMPT 
import config
from typing import Dict, Any

class LegalAgentFR:
    def __init__(self, retriever: HybridRetriever):
        self.llm = get_llm(model_name=config.AGENT_LLM_MODEL)
        self.tools = get_all_tools(retriever) 
        
        self.agent_prompt = CONVERSATIONAL_REACT_PROMPT 

        # 2. Create the agent instance
        if not USE_LEGACY_AGENT:
            # Modern approach
            agent_instance = create_react_agent(
                llm=self.llm,
                tools=self.tools, 
                prompt=self.agent_prompt 
            )
            
            self.memory = ConversationBufferWindowMemory(
                k=5,
                memory_key="chat_history",
                return_messages=True
            )

            self.agent_executor = AgentExecutor(
                agent=agent_instance,
                tools=self.tools,
                verbose=True,
                max_iterations=config.AGENT_MAX_ITERATIONS,
                handle_parsing_errors=True,
                memory=self.memory
            )
        else:
            # Legacy approach (fallback)
            self.memory = ConversationBufferWindowMemory(
                k=5,
                memory_key="chat_history",
                return_messages=True
            )
            
            self.agent_executor = initialize_agent(
                tools=self.tools,
                llm=self.llm,
                agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION, # Or ZERO_SHOT_REACT_DESCRIPTION
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