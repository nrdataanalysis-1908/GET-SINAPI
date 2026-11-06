"""Interface de linha de comando do GET-SINAPI."""
import argparse

from getsinapi import __version__
from getsinapi.config import Settings


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="getsinapi",
        description="Pipeline de coleta e estruturação de dados SINAPI/CAIXA.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "command", nargs="?", choices=("check-config",), default="check-config"
    )
    args = parser.parse_args()

    if args.command == "check-config":
        settings = Settings.from_env()
        settings.create_data_directories()
        print(f"Configuração válida | ambiente={settings.environment}")
        print(f"Diretório de dados: {settings.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
