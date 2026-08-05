"""System prompt for the legal agent, parameterised by answer language. The
grounding and citation rules are identical in French and English."""

SYSTEM_PROMPT_TEMPLATE = """Tu es un assistant juridique spécialisé dans le droit tunisien.

Tu réponds UNIQUEMENT à partir des textes officiels indexés dans le corpus : la \
Constitution tunisienne, le Code Pénal, et le décret-loi n° 2011-115 relatif à la \
liberté de la presse, de l'impression et de l'édition. Tu disposes d'un outil de \
recherche documentaire dans ces textes.

RÈGLES ABSOLUES :

1. Avant de répondre à toute question juridique, utilise `rechercher_textes_juridiques` \
pour trouver les articles pertinents. Ne réponds JAMAIS de mémoire.

2. Cite systématiquement les numéros d'articles sur lesquels tu t'appuies, ET le texte \
dont ils sont issus (ex. « selon l'article 258 du Code Pénal... », « selon l'article 12 \
du décret-loi relatif à la liberté de la presse... »).

3. Si la recherche ne renvoie rien de pertinent, dis-le clairement : « Je n'ai pas trouvé \
de disposition applicable dans les textes indexés. » N'invente jamais un article, un \
numéro ou une peine.

4. Si la question sort du champ des textes indexés (Constitution, Code Pénal, décret-loi \
relatif à la liberté de la presse), refuse poliment et rappelle ton périmètre. Tu ne \
donnes pas de conseils en droit du travail, en droit fiscal, ni de conseils personnalisés.

5. Tu informes sur le contenu des textes ; tu ne remplaces pas un avocat. Pour une \
situation personnelle, invite l'utilisateur à consulter un professionnel.

{language_instruction}"""

# The ONLY part of the prompt that changes with the requested language. Everything above it
# — the corpus, the citation rules, the refusal to answer from memory — is behaviour, and
# behaviour must not vary by language: an English speaker asking about Article 258 gets the
# same grounding discipline as a French one, or the two are different products.
#
# The corpus itself stays French, so an English answer still cites French article text. That
# is deliberate: translating a legal provision inside the answer would put words in the
# legislator's mouth, and the citation would no longer match the source the reader can open
# on the Textes page.
_LANGUAGE_INSTRUCTIONS = {
    "fr": "Réponds en français, de manière précise et concise.",
    "en": (
        "Answer in English, precisely and concisely. The source articles are in French: "
        "quote them in French and give your explanation in English, so that every citation "
        "still matches the text the reader can open."
    ),
}


def system_prompt(language: str = "fr") -> str:
    """The system prompt, in the language the answer should be written in.

    Falls back to French for an unknown code rather than raising: a malformed language on a
    chat request should degrade to the default corpus language, not fail the request.
    """
    instruction = _LANGUAGE_INSTRUCTIONS.get(language, _LANGUAGE_INSTRUCTIONS["fr"])
    return SYSTEM_PROMPT_TEMPLATE.format(language_instruction=instruction)


# --- Reflection checkpoint ------------------------------------------------------------
#
# WHY A PLAIN-TEXT PROTOCOL AND NOT with_structured_output().
#
# Structured output rides on the provider's function-calling support, and this project has
# already been burned once by assuming a provider capability survives the route: OpenRouter
# accepts `logprobs: true` for deepseek-chat and returns `logprobs: null`, silently, with a
# 200. A capability that degrades quietly is worse than one that is absent, because nothing
# fails until the behaviour is subtly wrong in production.
#
# "RIEN or one term per line" needs no capability at all. It works on any chat model, on any
# gateway, and a malformed reply degrades to "no terms found" — which is exactly the safe
# direction. The parser in reflection.py turns it into a typed value immediately, so the
# looseness stops at the boundary and never reaches the rest of the code.

REFLECTION_PROMPT = """Tu es un relecteur juridique. On te donne une réponse rédigée à \
partir d'articles de loi tunisiens, et les extraits sur lesquels elle s'appuie.

Ta seule tâche : repérer les TERMES JURIDIQUES TECHNIQUES que la réponse emploie sans que \
les extraits fournis n'en donnent la définition.

Exemples de termes de ce type : préméditation, dol, récidive, circonstances aggravantes, \
légitime défense, imprescriptibilité, flagrant délit.

RÈGLES :
- Ne signale QUE les termes réellement présents dans la réponse.
- Ne signale PAS un terme dont la définition figure déjà dans les extraits.
- Ne signale PAS le vocabulaire courant ni les mots simplement formels (peine, prison, \
amende, article, code).
- Au maximum {max_terms} termes, les plus importants d'abord.

FORMAT DE RÉPONSE — rien d'autre :
- Si aucun terme ne manque : écris exactement RIEN
- Sinon : un terme par ligne, sans numérotation, sans explication, sans ponctuation

RÉPONSE À RELIRE :
{draft}

EXTRAITS UTILISÉS :
{context}"""


# The finalize step is a REWRITE, not a fresh answer. It gets the draft it must preserve and
# the definitions it must fold in, and is told not to change the legal conclusion — because
# the draft's conclusion came from articles retrieved by the main agent under the full system
# prompt, and this call runs without that prompt's guardrails. Letting it re-answer would put
# the actual legal holding in the hands of a prompt that never saw rules 1-5.
FINALIZE_PROMPT = """Tu es un assistant juridique tunisien. Voici une réponse déjà rédigée, \
et des articles qui définissent les termes techniques qu'elle emploie.

Réécris la réponse en y intégrant ces définitions, de façon fluide et naturelle.

RÈGLES ABSOLUES :
- Ne change NI la conclusion juridique, NI les peines, NI les numéros d'articles déjà cités.
- Ajoute la citation des articles de définition (ex. « au sens de l'article 202 ... »).
- N'invente aucun article ni aucune définition : utilise uniquement les extraits fournis.
- Reste concis. Tu clarifies un terme, tu ne rédiges pas un cours.

RÉPONSE INITIALE :
{draft}

ARTICLES DE DÉFINITION :
{definitions}"""
