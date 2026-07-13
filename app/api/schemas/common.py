from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Matches the /api/health shape already used across this portfolio, so the compose
    healthcheck and render.yaml healthCheckPath carry over unchanged."""

    status: str
    database: bool
    model_loaded: bool
    embedding_model: str
    corpus_chunks: int
