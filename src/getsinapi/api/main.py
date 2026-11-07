"""Aplicação FastAPI do GET-SINAPI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="GET-SINAPI API",
    description="API de consulta e observabilidade dos dados oficiais do SINAPI.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["Sistema"], summary="Verifica a disponibilidade da API")
def health_check() -> dict[str, str]:
    """Retorna o estado do serviço HTTP, sem simular estado do pipeline ou do banco."""
    return {"status": "ok", "service": "get-sinapi-api", "version": app.version}
