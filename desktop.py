"""Launcher desktop Windows para a prévia GET-SINAPI."""
from __future__ import annotations
import os, sys, threading, time, urllib.error, urllib.request, webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST, PORT, API_PORT = "127.0.0.1", 8765, 8766

def resource_path(relative: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / relative

def configure_storage() -> None:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NRDataAnalysis" / "GET-SINAPI"
    data = base / "data"
    for name in ("raw", "staging", "processed", "manifests"):
        (data / name).mkdir(parents=True, exist_ok=True)
    for key, value in {
        "GETSINAPI_DATA_DIR": data, "GETSINAPI_RAW_DIR": data / "raw",
        "GETSINAPI_STAGING_DIR": data / "staging", "GETSINAPI_PROCESSED_DIR": data / "processed",
        "GETSINAPI_MANIFEST_DIR": data / "manifests",
        "GETSINAPI_DATABASE_PATH": data / "getsinapi.sqlite3",
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
            payload = ('{"detail":"API indisponível: ' + type(exc).__name__ + '"}').encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    def do_GET(self):
        if self.path.startswith(("/api/", "/openapi.json", "/docs")):
            return self.proxy()
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()
    def do_POST(self):
        return self.proxy()

def main() -> None:
    configure_storage()
    import uvicorn
    from getsinapi.api.main import app
    api = uvicorn.Server(uvicorn.Config(
        app, host=HOST, port=API_PORT, log_level="warning",
        log_config=None, access_log=False,
    ))
    threading.Thread(target=api.run, daemon=True).start()
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://{HOST}:{API_PORT}/api/health", timeout=1).close()
            break
        except Exception:
            time.sleep(0.2)
    else:
        raise RuntimeError("A API local não iniciou.")
    server = ThreadingHTTPServer((HOST, PORT), DesktopHandler)
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
