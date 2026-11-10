"""Launcher Windows com armazenamento persistente e atualização SINAPI em segundo plano."""
from __future__ import annotations

import logging
import os
import socket
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST, PORT, API_PORT = "127.0.0.1", 0, 0
log = logging.getLogger("getsinapi.desktop")


def resource_path(relative: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / relative


def _has_sinapi_data(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not {"source_references", "input_prices", "compositions"} <= tables:
                return False
            return db.execute("SELECT COUNT(*) FROM source_references").fetchone()[0] > 0
    except (sqlite3.Error, OSError):
        return False


def _copy_database_safely(source: Path, target: Path) -> bool:
    if not _has_sinapi_data(source):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".sqlite3.migrating")
    try:
        with (
            sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30) as src,
            sqlite3.connect(temporary, timeout=30) as dst,
        ):
            src.backup(dst)
            integrity = dst.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise sqlite3.DatabaseError("Backup SQLite falhou no integrity_check.")
        if not _has_sinapi_data(temporary):
            return False
        os.replace(temporary, target)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def configure_storage() -> None:
    profile = Path(os.environ.get("USERPROFILE", Path.home()))
    base = Path(os.environ.get("LOCALAPPDATA", profile)) / "NRTech" / "GET-SINAPI-V3"
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)
    database = data / "getsinapi.sqlite3"
    candidates = [
        profile / "GET-SINAPI" / "data" / "getsinapi.sqlite3",
        Path.cwd() / "data" / "getsinapi.sqlite3",
        Path(__file__).resolve().parent / "data" / "getsinapi.sqlite3",
    ]
    if not _has_sinapi_data(database):
        for candidate in candidates:
            if candidate.resolve() != database.resolve() and _copy_database_safely(candidate, database):
                break
    for name in ("raw", "staging", "processed", "manifests", "logs"):
        (data / name).mkdir(parents=True, exist_ok=True)
    for key, value in {
        "GETSINAPI_DATA_DIR": data,
        "GETSINAPI_RAW_DIR": data / "raw",
        "GETSINAPI_STAGING_DIR": data / "staging",
        "GETSINAPI_PROCESSED_DIR": data / "processed",
        "GETSINAPI_MANIFEST_DIR": data / "manifests",
        "GETSINAPI_DATABASE_PATH": database,
        "GETSINAPI_ENV": "production",
    }.items():
        os.environ[key] = str(value)


class DesktopHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(resource_path("frontend/dist")), **kwargs)

    def log_message(self, fmt, *args):
        return

    def proxy(self):
        target = f"http://{HOST}:{API_PORT}{self.path}"
        body = None
        if self.command in ("POST", "PUT", "PATCH"):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in {"host", "connection", "content-length"}}
        request = urllib.request.Request(target, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in {"transfer-encoding", "connection", "content-encoding"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:
            log.exception("Falha inesperada no proxy da API local.")
            payload = ('{"detail":"API indisponível: ' + type(exc).__name__ + '"}').encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def _send(self, status: int, content_type: str, payload: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/bootstrap-status":
            state_path = Path(os.environ["GETSINAPI_DATA_DIR"]) / "logs" / "bootstrap-state.json"
            try:
                payload = state_path.read_bytes() if state_path.is_file() else (
                    b'{"status":"starting","stage":"discovery","message":"Consultando a CAIXA."}'
                )
            except OSError:
                payload = '{"status":"unavailable","message":"Estado indisponível."}'.encode()
            return self._send(200, "application/json; charset=utf-8", payload)
        if self.path == "/__legacy-bootstrap" and not _has_sinapi_data(
            Path(os.environ["GETSINAPI_DATABASE_PATH"])
        ):
            page = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>GET-SINAPI | Preparação da base</title>
            <style>
            *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;
            background:#080d14;color:#e8f4ff;font:16px Segoe UI,Arial}
            main{width:min(620px,90vw);padding:38px;border:1px solid #1d3446;border-radius:18px;
            background:#101a26;box-shadow:0 24px 80px #0008}small{color:#60e6ff;letter-spacing:2px}
            h1{font-size:25px;margin:14px 0}p{color:#a9bdce;line-height:1.6}
            .track{height:9px;background:#243445;border-radius:9px;overflow:hidden;margin:25px 0}
            #bar{height:100%;width:4%;background:#60e6ff;transition:width .4s}
            #stage{color:#60e6ff;font-size:13px;text-transform:uppercase;letter-spacing:1px}
            button{background:#60e6ff;border:0;padding:11px 18px;border-radius:8px;font-weight:700;cursor:pointer}
            </style><main><small>NR DATA ANALYSIS / GET-SINAPI</small>
            <h1>Preparando a base oficial</h1><p id="message">Verificando a competência mais recente publicada pela CAIXA.</p>
            <div class="track"><div id="bar"></div></div><div id="stage">Inicialização</div>
            <p id="reference"></p><p id="error"></p><button id="retry" hidden>Repetir atualização</button></main>
            <script>
            async function refresh(){try{const r=await fetch('/bootstrap-status',{cache:'no-store'});const s=await r.json();
            document.querySelector('#message').textContent=s.message||'Processando dados oficiais';
            document.querySelector('#stage').textContent=s.stage||s.status||'Em andamento';
            document.querySelector('#reference').textContent=s.reference?'Competência: '+s.reference:'';
            document.querySelector('#bar').style.width=(Number.isFinite(s.percent)?s.percent:8)+'%';
            document.querySelector('#error').textContent=s.error||'';
            document.querySelector('#retry').hidden=s.status!=='error';
            if(s.stage==='complete'||s.status==='updated'||s.status==='up_to_date'){location.replace('/index.html');return;}
            }catch(e){document.querySelector('#message').textContent='Aguardando serviço local...';}}
            document.querySelector('#retry').onclick=async()=>{await fetch('/bootstrap-retry',{method:'POST'});refresh();};
            refresh();setInterval(refresh,1500);
            </script></html>""".encode()
            return self._send(200, "text/html; charset=utf-8", page)
        if self.path.startswith(("/api/", "/openapi.json", "/docs")):
            return self.proxy()
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/bootstrap-retry":
            from getsinapi.bootstrap import run_bootstrap
            threading.Thread(target=lambda: run_bootstrap(force=True), daemon=True, name="sinapi-bootstrap-retry").start()
            return self._send(202, "application/json", b'{"status":"retry_started"}')
        return self.proxy()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def main() -> None:
    global PORT, API_PORT
    configure_storage()
    import uvicorn

    from getsinapi.api.main import app

    API_PORT = _free_port()
    api = uvicorn.Server(uvicorn.Config(
        app, host=HOST, port=API_PORT, log_level="warning",
        log_config=None, access_log=False,
    ))
    threading.Thread(target=api.run, daemon=True, name="sinapi-api").start()
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"http://{HOST}:{API_PORT}/api/health", timeout=1):
                break
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.2)
    else:
        raise RuntimeError("A API local não iniciou.")

    # Atualização independente do ciclo de vida do painel: não bloqueia a abertura.
    from getsinapi.bootstrap import run_bootstrap

    def update_database():
        # O serviço permanece ativo até concluir uma atualização válida.
        # Backoff progressivo evita martelar a CAIXA quando houver 403/429,
        # indisponibilidade temporária ou publicação ainda não concluída.
        retry_delay = 30
        max_retry_delay = 15 * 60
        while True:
            try:
                result = run_bootstrap()
                if result.get("status") in {"updated", "up_to_date"}:
                    retry_delay = 30
                    # Verificação periódica: novas competências são incorporadas
                    # sem exigir que o usuário feche e reabra o aplicativo.
                    time.sleep(6 * 60 * 60)
                    continue
                if result.get("status") == "already_running":
                    time.sleep(15)
                    continue
                log.warning("Bootstrap não concluiu: %s. Nova tentativa em %s segundos.",
                            result, retry_delay)
            except Exception:
                log.exception("Atualização SINAPI falhou; nova tentativa automática em %s segundos.",
                              retry_delay)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)

    threading.Thread(target=update_database, daemon=True, name="sinapi-bootstrap").start()
    server = ThreadingHTTPServer((HOST, 0), DesktopHandler)
    PORT = server.server_address[1]
    webbrowser.open(f"http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        api.should_exit = True


if __name__ == "__main__":
    main()
