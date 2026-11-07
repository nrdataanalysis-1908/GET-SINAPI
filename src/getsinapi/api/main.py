"""Endpoints de leitura para dados SINAPI persistidos localmente."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="GET-SINAPI API",
    description="API de consulta dos dados históricos oficiais do SINAPI.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _database_path() -> Path:
    return Path(os.getenv("GETSINAPI_DATABASE_PATH", "data/getsinapi.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _database_path()
    if not path.is_file():
        raise HTTPException(
            status_code=503,
            detail="Banco SINAPI não encontrado. Execute a normalização e a carga da competência.",
        )
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _rows(sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        with _connect() as connection:
            return [dict(row) for row in connection.execute(sql, parameters).fetchall()]
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            raise HTTPException(
                status_code=503,
                detail="Banco ainda não inicializado. Execute getsinapi load.",
            ) from exc
        raise


@app.get("/api/health", tags=["Sistema"], summary="Verifica a disponibilidade da API")
def health_check() -> dict[str, str]:
    """Verifica o serviço HTTP sem simular conectividade com o banco."""
    return {"status": "ok", "service": "get-sinapi-api", "version": app.version}


@app.get("/api/references", tags=["Dados"], summary="Lista competências disponíveis")
def list_references() -> list[dict[str, Any]]:
    return _rows(
        """SELECT reference, source_file, loaded_at
           FROM source_references ORDER BY reference DESC"""
    )


@app.get("/api/summary", tags=["Dados"], summary="Resumo de uma competência")
def summary(reference: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")) -> dict[str, Any]:
    rows = _rows(
        """SELECT
             (SELECT COUNT(*) FROM input_prices WHERE reference = ?) AS input_prices,
             (SELECT COUNT(*) FROM compositions WHERE reference = ?) AS compositions,
             (SELECT COUNT(*) FROM composition_items WHERE reference = ?) AS composition_items,
             (SELECT COUNT(DISTINCT uf) FROM input_prices WHERE reference = ?) AS states,
             (SELECT COUNT(*) FROM input_prices
                WHERE reference = ? AND status IN ('missing', 'not_researched')) AS unavailable_prices""",
        (reference, reference, reference, reference, reference),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Competência não encontrada.")
    return {"reference": reference, **rows[0]}


@app.get("/api/insumos", tags=["Insumos"], summary="Consulta preços de insumos")
def list_input_prices(
    reference: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    uf: str = Query(..., min_length=2, max_length=2),
    regime: str | None = Query(None, pattern="^(desonerado|nao_desonerado)$"),
    encargo_mode: str = Query("com_encargos", pattern="^(com_encargos|sem_encargos)$"),
    search: str | None = Query(None, min_length=2, max_length=120),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    clauses = ["reference = ?", "uf = ?", "encargo_mode = ?"]
    parameters: list[Any] = [reference, uf.upper(), encargo_mode]
    if regime is not None:
        clauses.append("regime = ?")
        parameters.append(regime)
    if search:
        clauses.append("(code LIKE ? OR description LIKE ?)")
        term = f"%{search.strip()}%"
        parameters.extend((term, term))
    parameters.extend((limit, offset))
    return _rows(
        f"""SELECT code, description, unit, uf, regime, encargo_mode,
                   table_type, price, status, price_origin
            FROM input_prices WHERE {' AND '.join(clauses)}
            ORDER BY code LIMIT ? OFFSET ?""",
        tuple(parameters),
    )


@app.get("/api/composicoes", tags=["Composições"], summary="Consulta composições")
def list_compositions(
    reference: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    search: str | None = Query(None, min_length=2, max_length=120),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    clauses = ["reference = ?"]
    parameters: list[Any] = [reference]
    if search:
        clauses.append("(code LIKE ? OR description LIKE ?)")
        term = f"%{search.strip()}%"
        parameters.extend((term, term))
    parameters.extend((limit, offset))
    return _rows(
        f"""SELECT code, description, unit, status
            FROM compositions WHERE {' AND '.join(clauses)}
            ORDER BY code LIMIT ? OFFSET ?""",
        tuple(parameters),
    )


@app.get(
    "/api/composicoes/{code}/itens",
    tags=["Composições"],
    summary="Lista os componentes de uma composição",
)
def composition_items(
    code: str,
    reference: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> list[dict[str, Any]]:
    return _rows(
        """SELECT item_code, item_type, description, unit, coefficient, source_row
           FROM composition_items
           WHERE reference = ? AND composition_code = ?
           ORDER BY source_row""",
        (reference, code),
    )
