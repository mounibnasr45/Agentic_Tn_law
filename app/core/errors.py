"""Domain exceptions and their HTTP mapping.

The domain raises meaningful exceptions; the API boundary decides what they mean over
HTTP. The domain must not import fastapi — a service that can only be called from a web
handler cannot be called from the CLI, a worker, or a test.

BUG 3 is why this exists. The old agent caught Exception and returned str(e) AS the
assistant's answer, so an upstream timeout was rendered to the user as legal advice with
a 200 OK. A failure must never be indistinguishable from an answer.
"""
from fastapi import HTTPException, status


class DomainError(Exception):
    """Base class. Every subclass maps to exactly one HTTP status."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Erreur interne."


class EmailAlreadyRegistered(DomainError):
    status_code = status.HTTP_409_CONFLICT
    detail = "Cette adresse email est déjà utilisée."

    def __init__(self, email: str) -> None:
        super().__init__(email)


class InvalidCredentials(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    # Deliberately does not say WHICH is wrong. "Unknown email" tells an attacker which
    # addresses are registered.
    detail = "Email ou mot de passe incorrect."


class AccountDisabled(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "Ce compte est désactivé."


class InvalidRefreshToken(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Jeton de rafraîchissement invalide ou expiré."


class TokenReplayDetected(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Session révoquée pour raison de sécurité. Veuillez vous reconnecter."


class NotAuthenticated(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Authentification requise."


class ConversationNotFound(DomainError):
    # 404 for BOTH "does not exist" and "belongs to someone else". Distinguishing them
    # would tell an attacker which conversation ids are real.
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Conversation introuvable."


class CorpusNotReady(DomainError):
    # 503, not 500: the service is fine, the corpus simply has not been ingested yet.
    # A load balancer should back off and retry, not page someone.
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "Le corpus juridique n'est pas indexé."


class UpstreamLLMError(DomainError):
    # 502, not 500: the failure is in a service we depend on, not in us. Collapsing both
    # into 500 makes "is it my bug or theirs?" unanswerable from the metrics.
    status_code = status.HTTP_502_BAD_GATEWAY
    detail = "Le service de génération est indisponible."


def to_http_exception(error: DomainError) -> HTTPException:
    unauthorized = error.status_code == status.HTTP_401_UNAUTHORIZED
    headers = {"WWW-Authenticate": "Bearer"} if unauthorized else None
    return HTTPException(status_code=error.status_code, detail=error.detail, headers=headers)
