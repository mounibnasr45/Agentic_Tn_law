from typing import Any

from langchain.agents.agent import AgentExecutor
from langchain.agents.react.agent import create_react_agent
from langchain.memory import ConversationBufferWindowMemory

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm_interface import get_llm
from app.prompts import CONVERSATIONAL_REACT_PROMPT
from app.retriever import HybridRetriever
from app.tools import get_all_tools

log = get_logger(__name__)

# A three-level try/except import cascade used to sit here, deciding the agent's
# construction strategy at import time based on whichever LangChain version happened
# to be installed. requirements.txt pins langchain>=0.3, so the modern path is the
# only reachable one and the legacy branches were dead code that made this module's
# behaviour depend on the environment. Removed.


class LegalAgentFR:
    """ReAct agent over the legal corpus.

    Three known bugs live in this class. They are NOT fixed here: P1 is a structural
    refactor and behaviour must not change in the same commit as a move. All three
    share one root cause — AgentExecutor + per-object memory + a string-returning tool
    — and are fixed together in P5 by moving to LangGraph.

      BUG 2  `memory` is an attribute of this object, and the object is cached
             process-wide by @st.cache_resource in the frontend. Conversation history
             is therefore a property of the PROCESS, not of a user or a request, so
             concurrent visitors share one buffer and can read each other's history.
      BUG 3  run() catches Exception and returns str(e) AS the assistant's answer,
             making a failure indistinguishable from a legal opinion.
      BUG 4  `sources` is a hardcoded placeholder. Real citations never escape the
             tool, which flattens them into a truncated string.
    """

    def __init__(self, retriever: HybridRetriever):
        settings = get_settings()

        self.llm = get_llm(model_name=settings.agent_llm_model)
        self.tools = get_all_tools(retriever)

        # BUG 2 lives on this line: per-object memory on a process-global object.
        self.memory = ConversationBufferWindowMemory(
            k=5, memory_key="chat_history", return_messages=True
        )

        self.agent_executor = AgentExecutor(
            agent=create_react_agent(
                llm=self.llm, tools=self.tools, prompt=CONVERSATIONAL_REACT_PROMPT
            ),
            tools=self.tools,
            verbose=settings.agent_verbose,
            max_iterations=settings.agent_max_iterations,
            handle_parsing_errors=True,
            memory=self.memory,
        )

        log.info("agent_initialised", tool_count=len(self.tools))

    def run(self, query: str) -> dict[str, Any]:
        try:
            response = self.agent_executor.invoke({"input": query})
            return {"answer": response.get("output", ""), "sources": None}
        except Exception as exc:
            # BUG 3. Preserved deliberately for P1 (no behaviour change), but the
            # failure is now logged with a stack trace instead of a bare print, so it
            # is at least visible. P5 re-raises and the API maps it to 502/503/504.
            log.exception("agent_execution_failed_returning_error_as_answer", bug="3")
            return {
                "answer": f"Une erreur est survenue lors du traitement de votre requête : {exc}",
                "sources": None,
            }
