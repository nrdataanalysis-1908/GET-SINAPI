"""Endpoints de leitura para dados SINAPI persistidos localmente."""

from __future__ import annotations

import os
import sqlite3
import csv
import io
import json
import hashlib
import secrets
import threading
import time
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from getsinapi import __version__
from getsinapi.domain import CompositionStatus, EncargoMode, PriceStatus, Regime
from getsinapi.extractors.compositions import CompositionItemRecord, CompositionRecord
from getsinapi.extractors.price_tables import InputPriceRecord
from getsinapi.services.costing import BudgetItem, CompositionCostCalculator

app = FastAPI(
    title="GET-SINAPI API",
    description="API de consulta dos dados históricos oficiais do SINAPI.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)


_AUTH_SESSIONS: dict[str, tuple[str, float]] = {}
_AUTH_LOCK = threading.RLock()
_AUTH_COOKIE = "getsinapi_session"


def _auth_path() -> Path:
    base = Path(os.getenv("GETSINAPI_DATA_DIR", _database_path().parent))
    return base / "security" / "users.json"


def _read_auth() -> dict[str, Any]:
    path = _auth_path()
    if not path.is_file():
        return {"users": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"users": []}
    except (OSError, ValueError, TypeError):
        return {"users": []}


def _password_digest(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000).hex()


def _new_session(username: str, response: Response) -> None:
    token = secrets.token_urlsafe(40)
    with _AUTH_LOCK:
        _AUTH_SESSIONS[token] = (username, time.time() + 8 * 60 * 60)
    response.set_cookie(_AUTH_COOKIE, token, httponly=True, samesite="strict",
                        secure=False, max_age=8 * 60 * 60, path="/")


def _session_user(request: Request) -> str | None:
    token = request.cookies.get(_AUTH_COOKIE)
    if not token:
        return None
    with _AUTH_LOCK:
        session = _AUTH_SESSIONS.get(token)
        if not session:
            return None
        if session[1] <= time.time():
            _AUTH_SESSIONS.pop(token, None)
            return None
        return session[0]


@app.middleware("http")
async def require_local_auth(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in {
        "/api/health", "/api/auth/status", "/api/auth/setup",
        "/api/auth/login", "/api/auth/logout"
    }:
        if _read_auth().get("users") and not _session_user(request):
            return JSONResponse(status_code=401, content={"detail": "Sessão expirada ou não autenticada."})
    return await call_next(request)


@app.get("/api/auth/status", tags=["Autenticação"])
def auth_status(request: Request) -> dict[str, Any]:
    users = _read_auth().get("users", [])
    username = _session_user(request)
    return {"configured": bool(users), "authenticated": bool(username), "username": username}


@app.post("/api/auth/setup", tags=["Autenticação"])
def auth_setup(payload: AuthRequest, response: Response) -> dict[str, str]:
    with _AUTH_LOCK:
        path = _auth_path()
        current = _read_auth()
        if current.get("users"):
            raise HTTPException(status_code=409, detail="A configuração inicial já foi concluída.")
        username = payload.username.strip().lower()
        if not username:
            raise HTTPException(status_code=422, detail="Informe um usuário válido.")
        salt = secrets.token_bytes(24)
        user = {"username": username, "salt": salt.hex(),
                "password_hash": _password_digest(payload.password, salt),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"users": [user]}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        _new_session(username, response)
    return {"status": "configured", "username": username}


@app.post("/api/auth/login", tags=["Autenticação"])
def auth_login(payload: AuthRequest, response: Response) -> dict[str, str]:
    username = payload.username.strip().lower()
    users = _read_auth().get("users", [])
    user = next((item for item in users if item.get("username") == username), None)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")
    try:
        salt = bytes.fromhex(user["salt"])
        expected = str(user["password_hash"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=500, detail="Cadastro local de autenticação inválido.")
    if not secrets.compare_digest(_password_digest(payload.password, salt), expected):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")
    _new_session(username, response)
    return {"status": "authenticated", "username": username}


@app.post("/api/auth/logout", tags=["Autenticação"])
def auth_logout(request: Request, response: Response) -> dict[str, str]:
    token = request.cookies.get(_AUTH_COOKIE)
    if token:
        with _AUTH_LOCK:
            _AUTH_SESSIONS.pop(token, None)
    response.delete_cookie(_AUTH_COOKIE, path="/")
    return {"status": "logged_out"}


class BudgetLineRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    item_type: str = Field(pattern="^(INSUMO|COMPOSICAO)$")
    quantity: Decimal = Field(ge=0)


class BudgetRequest(BaseModel):
    reference: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    uf: str = Field(min_length=2, max_length=2)
    regime: Regime | None = Regime.NAO_DESONERADO
    encargo_mode: EncargoMode = EncargoMode.COM_ENCARGOS
    items: list[BudgetLineRequest] = Field(min_length=1, max_length=500)


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
        with closing(_connect()) as connection, connection:
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


def _escape_like(value: str) -> str:
    """Escape SQLite LIKE metacharacters so search terms remain literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
        clauses.append("(code LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
        term = f"%{_escape_like(search.strip())}%"
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
        """SELECT item_code, item_type, description, unit, coefficient, status, source_row
           FROM composition_items
           WHERE reference = ? AND composition_code = ?
           ORDER BY source_row""",
        (reference, code),
    )

def _cost_calculator(
    *, reference: str, uf: str, regime: Regime | None, encargo_mode: EncargoMode
) -> CompositionCostCalculator:
    price_rows = _rows(
        """SELECT reference, code, description, unit, uf, regime, encargo_mode,
                  price, status, price_origin, source_file, source_sheet, source_row
           FROM input_prices
           WHERE reference = ? AND uf = ? AND regime IS ? AND encargo_mode = ?""",
        (reference, uf.upper(), regime.value if regime else None, encargo_mode.value),
    )
    composition_rows = _rows(
        """SELECT reference, code, description, unit, status,
                  source_file, source_sheet, source_row
           FROM compositions WHERE reference = ?""",
        (reference,),
    )
    item_rows = _rows(
        """SELECT reference, composition_code, item_code, item_type,
                  description, unit, coefficient, status, source_file, source_sheet, source_row
           FROM composition_items WHERE reference = ? ORDER BY source_row""",
        (reference,),
    )
    prices = [
        InputPriceRecord(
            **{
                **row,
                "regime": Regime(row["regime"]) if row["regime"] else None,
                "encargo_mode": EncargoMode(row["encargo_mode"]),
                "price": Decimal(row["price"]) if row["price"] is not None else None,
                "status": PriceStatus(row["status"]),
            }
        )
        for row in price_rows
    ]
    compositions = [
        CompositionRecord(
            **{
                **row,
                "status": CompositionStatus(row["status"]) if row["status"] else None,
            }
        )
        for row in composition_rows
    ]
    item_records = [
        CompositionItemRecord(
            **{
                **row,
                "coefficient": Decimal(row["coefficient"]),
                "status": CompositionStatus(row["status"]) if row["status"] else None,
            }
        )
        for row in item_rows
    ]
    return CompositionCostCalculator(
        prices=prices,
        compositions=compositions,
        composition_items=item_records,
        reference=reference,
        uf=uf,
        regime=regime,
        encargo_mode=encargo_mode,
    )


@app.get(
    "/api/composicoes/{code}/custo",
    tags=["Orçamento"],
    summary="Calcula o custo unitário recursivo de uma composição",
)
def composition_cost(
    code: str,
    reference: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    uf: Annotated[str, Query(min_length=2, max_length=2)],
    regime: Annotated[Regime | None, Query()] = None,
    encargo_mode: Annotated[EncargoMode, Query()] = EncargoMode.COM_ENCARGOS,
) -> dict[str, Any]:
    effective_regime = (
        None if encargo_mode == EncargoMode.SEM_ENCARGOS
        else regime or Regime.NAO_DESONERADO
    )
    calculator = _cost_calculator(
        reference=reference, uf=uf, regime=effective_regime, encargo_mode=encargo_mode
    )
    return jsonable_encoder(calculator.calculate_composition(code))


@app.post(
    "/api/budget",
    tags=["Orçamento"],
    summary="Calcula orçamento com insumos e composições SINAPI",
)
def calculate_budget(request: BudgetRequest) -> dict[str, Any]:
    effective_regime = (
        None if request.encargo_mode == EncargoMode.SEM_ENCARGOS
        else request.regime or Regime.NAO_DESONERADO
    )
    calculator = _cost_calculator(
        reference=request.reference,
        uf=request.uf,
        regime=effective_regime,
        encargo_mode=request.encargo_mode,
    )
    items = [
        BudgetItem(code=item.code, item_type=item.item_type, quantity=item.quantity)
        for item in request.items
    ]
    return jsonable_encoder(calculator.calculate_budget(items))



@app.get("/api/catalog", tags=["Catálogo"], summary="Catálogo unificado e paginado de todos os registros SINAPI")
def catalog(
    search: str | None = Query(None, min_length=2, max_length=120),
    uf: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    record_type: str | None = Query(None, pattern="^(INSUMO|COMPOSICAO|COMPONENTE)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Lista preços, composições e componentes em uma grade única, sem limitar competência."""
    cte = """
        WITH catalog AS (
            SELECT reference, 'INSUMO' AS record_type, code,
                   description, unit, uf, regime, encargo_mode, table_type,
                   price AS value, 'PREÇO' AS value_type,
                   NULL AS composition_code, status, source_file, source_sheet, source_row
            FROM input_prices
            UNION ALL
            SELECT reference, 'COMPOSICAO', code, description, unit,
                   NULL, NULL, NULL, 'Analítico', NULL, NULL,
                   NULL, status, source_file, source_sheet, source_row
            FROM compositions
            UNION ALL
            SELECT reference, 'COMPONENTE', item_code, description, unit,
                   NULL, NULL, NULL, 'Analítico', coefficient, 'COEFICIENTE',
                   composition_code, status, source_file, source_sheet, source_row
            FROM composition_items
        )
    """
    clauses: list[str] = []
    parameters: list[Any] = []
    if uf:
        # Composições e componentes são nacionais; permanecem visíveis junto aos preços da UF.
        clauses.append("(uf = ? OR uf IS NULL)")
        parameters.append(uf.upper())
    if record_type:
        clauses.append("record_type = ?")
        parameters.append(record_type)
    if search:
        term = f"%{_escape_like(search.strip())}%"
        clauses.append(
            "(code LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
            "OR composition_code LIKE ? ESCAPE '\\' OR source_file LIKE ? ESCAPE '\\' "
            "OR source_sheet LIKE ? ESCAPE '\\')"
        )
        parameters.extend((term, term, term, term, term))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        with closing(_connect()) as connection, connection:
            total = int(connection.execute(
                cte + " SELECT COUNT(*) FROM catalog" + where, tuple(parameters)
            ).fetchone()[0])
            rows = [dict(row) for row in connection.execute(
                cte + " SELECT * FROM catalog" + where
                + " ORDER BY reference DESC, record_type, code, uf LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            ).fetchall()]
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            raise HTTPException(
                status_code=503, detail="Banco SINAPI ainda não foi inicializado."
            ) from exc
        raise
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/api/analytics", tags=["Análises"], summary="Agregados reais para o painel analítico")
def analytics(reference: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")) -> dict[str, Any]:
    """Retorna séries e agregações calculadas diretamente da base SINAPI."""
    with closing(_connect()) as connection, connection:
        refs = [dict(row) for row in connection.execute(
            "SELECT reference, source_file, loaded_at FROM source_references ORDER BY reference"
        ).fetchall()]
        selected = reference or (refs[-1]["reference"] if refs else None)
        if not selected:
            return {"reference": None, "references": refs, "totals": {
                "input_prices": 0, "compositions": 0, "composition_items": 0,
                "states": 0, "unavailable_prices": 0
            }, "by_state": [], "by_reference": [], "by_table": [], "status": []}
        totals = connection.execute(
            """SELECT
                (SELECT COUNT(*) FROM input_prices WHERE reference = ?) input_prices,
                (SELECT COUNT(*) FROM compositions WHERE reference = ?) compositions,
                (SELECT COUNT(*) FROM composition_items WHERE reference = ?) composition_items,
                (SELECT COUNT(DISTINCT uf) FROM input_prices WHERE reference = ?) states,
                (SELECT COUNT(*) FROM input_prices WHERE reference = ?
                 AND status IN ('missing','not_researched')) unavailable_prices""",
            (selected, selected, selected, selected, selected)
        ).fetchone()
        by_state = [dict(row) for row in connection.execute(
            """SELECT uf, COUNT(*) observations,
                      COUNT(CASE WHEN price IS NOT NULL AND TRIM(price) <> '' THEN 1 END) priced,
                      ROUND(AVG(CASE WHEN price IS NOT NULL AND TRIM(price) <> ''
                                THEN CAST(REPLACE(price, ',', '.') AS REAL) END), 4) average_price
               FROM input_prices WHERE reference = ?
               GROUP BY uf ORDER BY uf""", (selected,)
        ).fetchall()]
        by_table = [dict(row) for row in connection.execute(
            """SELECT table_type, COUNT(*) observations,
                      COUNT(CASE WHEN price IS NOT NULL AND TRIM(price) <> '' THEN 1 END) priced
               FROM input_prices WHERE reference = ? GROUP BY table_type ORDER BY table_type""",
            (selected,)
        ).fetchall()]
        status = [dict(row) for row in connection.execute(
            """SELECT status, COUNT(*) quantity FROM input_prices
               WHERE reference = ? GROUP BY status ORDER BY quantity DESC""", (selected,)
        ).fetchall()]
        by_reference = [dict(row) for row in connection.execute(
            """SELECT r.reference,
                      (SELECT COUNT(*) FROM input_prices p WHERE p.reference=r.reference) input_prices,
                      (SELECT COUNT(*) FROM compositions c WHERE c.reference=r.reference) compositions,
                      (SELECT COUNT(DISTINCT uf) FROM input_prices p WHERE p.reference=r.reference) states
               FROM source_references r ORDER BY r.reference""").fetchall()]
        return {
            "reference": selected, "references": refs, "totals": dict(totals),
            "by_state": by_state, "by_reference": by_reference,
            "by_table": by_table, "status": status
        }




@app.get("/api/catalog/advanced", tags=["Catálogo"], summary="Consulta avançada com filtros combináveis")
def catalog_advanced(
    search: str | None = Query(None, min_length=2, max_length=120),
    reference: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    uf: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    record_type: str | None = Query(None, pattern="^(INSUMO|COMPOSICAO|COMPONENTE)$"),
    regime: str | None = Query(None, pattern="^(desonerado|nao_desonerado)$"),
    table_type: str | None = Query(None, max_length=80),
    min_value: float | None = Query(None),
    max_value: float | None = Query(None),
    priced_only: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    cte = """
      WITH catalog AS (
        SELECT reference,'INSUMO' record_type,code,description,unit,uf,regime,
          encargo_mode,table_type,price value,'PREÇO' value_type,NULL composition_code,
          status,source_file,source_sheet,source_row FROM input_prices
        UNION ALL
        SELECT reference,'COMPOSICAO',code,description,unit,NULL,NULL,NULL,'Analítico',
          NULL,NULL,NULL,status,source_file,source_sheet,source_row FROM compositions
        UNION ALL
        SELECT reference,'COMPONENTE',item_code,description,unit,NULL,NULL,NULL,'Analítico',
          coefficient,'COEFICIENTE',composition_code,status,source_file,source_sheet,source_row
          FROM composition_items
      )
    """
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (("reference", reference), ("record_type", record_type),
                          ("regime", regime), ("table_type", table_type)):
        if value:
            clauses.append(column + " = ?")
            params.append(value)
    if uf:
        clauses.append("(uf = ? OR uf IS NULL)")
        params.append(uf.upper())
    if search:
        term = "%" + _escape_like(search.strip()) + "%"
        clauses.append("(code LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR composition_code LIKE ? ESCAPE '\\' OR source_file LIKE ? ESCAPE '\\')")
        params.extend((term, term, term, term))
    if min_value is not None:
        clauses.append("CAST(REPLACE(value, ',', '.') AS REAL) >= ?")
        params.append(min_value)
    if max_value is not None:
        clauses.append("CAST(REPLACE(value, ',', '.') AS REAL) <= ?")
        params.append(max_value)
    if priced_only is True:
        clauses.append("value IS NOT NULL")
    elif priced_only is False:
        clauses.append("value IS NULL")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    try:
        with closing(_connect()) as connection, connection:
            total = int(connection.execute(cte + " SELECT COUNT(*) FROM catalog" + where, tuple(params)).fetchone()[0])
            rows = [dict(row) for row in connection.execute(
                cte + " SELECT * FROM catalog" + where +
                " ORDER BY reference DESC, record_type, code, uf LIMIT ? OFFSET ?",
                (*params, limit, offset)).fetchall()]
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            raise HTTPException(status_code=503, detail="Banco SINAPI ainda não foi inicializado.") from exc
        raise
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/api/catalog/export", tags=["Relatórios"], summary="Exporta o catálogo filtrado em CSV ou JSON")
def export_catalog(
    format: str = Query("csv", pattern="^(csv|json)$"),
    search: str | None = Query(None, min_length=2, max_length=120),
    reference: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    uf: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    record_type: str | None = Query(None, pattern="^(INSUMO|COMPOSICAO|COMPONENTE)$"),
    regime: str | None = Query(None, pattern="^(desonerado|nao_desonerado)$"),
    table_type: str | None = Query(None, max_length=80),
    min_value: float | None = Query(None),
    max_value: float | None = Query(None),
    priced_only: bool | None = Query(None),
) -> StreamingResponse:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        result = catalog_advanced(search, reference, uf, record_type, regime, table_type,
                                  min_value, max_value, priced_only, 500, offset)
        rows.extend(result["items"])
        offset += 500
        if offset >= result["total"] or not result["items"]:
            break
    if format == "json":
        payload = json.dumps({"total": len(rows), "items": rows}, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(iter([payload]), media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=get-sinapi-catalogo.json"})
    output = io.StringIO(newline="")
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    payload = ("\ufeff" + output.getvalue()).encode("utf-8")
    return StreamingResponse(iter([payload]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=get-sinapi-catalogo.csv"})


@app.get("/api/compare/prices", tags=["Análises"], summary="Compara preço de insumo entre UFs")
def compare_prices(
    code: str = Query(..., min_length=1, max_length=40),
    reference: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    regime: str = Query("nao_desonerado", pattern="^(desonerado|nao_desonerado)$"),
    encargo_mode: str = Query("com_encargos", pattern="^(com_encargos|sem_encargos)$"),
) -> list[dict[str, Any]]:
    return _rows(
        """SELECT code,description,unit,uf,regime,encargo_mode,table_type,price,status,price_origin
           FROM input_prices WHERE reference=? AND code=? AND regime=? AND encargo_mode=?
           ORDER BY uf,table_type""",
        (reference, code, regime, encargo_mode))


@app.get("/api/insumos/count", tags=["Insumos"], summary="Total de resultados do catálogo de insumos")
def count_input_prices(
    reference: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    uf: str = Query(..., min_length=2, max_length=2),
    regime: str | None = Query(None, pattern="^(desonerado|nao_desonerado)$"),
    encargo_mode: str = Query("com_encargos", pattern="^(com_encargos|sem_encargos)$"),
    search: str | None = Query(None, min_length=2, max_length=120),
) -> dict[str, int]:
    clauses = ["reference = ?", "uf = ?", "encargo_mode = ?"]
    parameters: list[Any] = [reference, uf.upper(), encargo_mode]
    if regime is not None:
        clauses.append("regime = ?")
        parameters.append(regime)
    if search:
        clauses.append("(code LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
        term = f"%{_escape_like(search.strip())}%"
        parameters.extend((term, term))
    rows = _rows(f"SELECT COUNT(*) AS total FROM input_prices WHERE {' AND '.join(clauses)}", tuple(parameters))
    return {"total": int(rows[0]["total"])}


@app.get("/api/composicoes/count", tags=["Composições"], summary="Total de resultados do catálogo de composições")
def count_compositions(
    reference: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    search: str | None = Query(None, min_length=2, max_length=120),
) -> dict[str, int]:
    clauses = ["reference = ?"]
    parameters: list[Any] = [reference]
    if search:
        clauses.append("(code LIKE ? OR description LIKE ?)")
        term = f"%{search.strip()}%"
        parameters.extend((term, term))
    rows = _rows(f"SELECT COUNT(*) AS total FROM compositions WHERE {' AND '.join(clauses)}", tuple(parameters))
    return {"total": int(rows[0]["total"])}
