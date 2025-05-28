import requests
from langchain_openai import ChatOpenAI
from langchain_core.outputs import LLMResult

import config

def get_openaicompatible_llm(model_name: str, api_key: str, base_url: str, temperature: float = 0.1, max_tokens: int = 1024):
    """
    Retourne une instance LLM ChatOpenAI de LangChain configurée pour OpenRouter.
    """
    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        default_headers={
            "HTTP-Referer": "http://localhost", # Adapter si déployé
            "X-Title": "Agent Juridique Tunisien" # Nom de votre application
        }
    )

def get_llm(model_name: str = None, temperature: float = 0.1, max_tokens: int = 1024):
    """
    Fonction factory pour obtenir une instance LLM (utilise OpenRouter par défaut).
    """
    model_to_use = model_name or config.AGENT_LLM_MODEL # Default to agent model
    return get_openaicompatible_llm(
        model_name=model_to_use,
        api_key=config.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
        max_tokens=max_tokens
    )

def direct_query_openrouter_llm(context: str, question: str, model: str = None):
    """Interroge directement le LLM via l'API OpenRouter (moins flexible)"""
    if not model:
        model = config.AGENT_LLM_MODEL # Default to French agent model
    
    prompt = f"""
    En vous basant sur les extraits juridiques suivants, répondez à la question en français.
    Si les extraits ne contiennent pas d'information pertinente pour répondre, indiquez-le clairement.
    
    Extraits juridiques:
    {context}
    
    Question: {question}
    """
    
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost", 
        "X-Title": "Agent Juridique Tunisien (Requête Directe)"
    }
    
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    response = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                          headers=headers, json=data, timeout=config.AGENT_REQUEST_TIMEOUT)
    
    response.raise_for_status()
    
    res_json = response.json()
    if "choices" not in res_json or not res_json["choices"]:
        raise Exception(f"Réponse API inattendue: {res_json}")
    
    return res_json["choices"][0]["message"]["content"].strip()