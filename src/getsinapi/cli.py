"""Interface de linha de comando do GET-SINAPI."""
import argparse
from pathlib import Path

from getsinapi import __version__
from getsinapi.config import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="getsinapi",
        description="Pipeline de coleta e estruturação de dados SINAPI/CAIXA.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("check-config", help="Valida as configurações locais.")
    download = commands.add_parser("download", help="Baixa o pacote XLSX mensal oficial da CAIXA.")
    download.add_argument("--reference", required=True, help="Competência no formato AAAA-MM.")

    extract = commands.add_parser("extract", help="Extrai ZIP e cataloga planilhas XLSX.")
    extract.add_argument("--archive", required=True, type=Path, help="Caminho do ZIP já baixado.")
    extract.add_argument("--reference", required=True, help="Competência no formato AAAA-MM.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.from_env()

    if args.command in (None, "check-config"):
        settings.create_data_directories()
        print(f"Configuração válida | ambiente={settings.environment}")
        print(f"Diretório de dados: {settings.data_dir}")
        return 0

    if args.command == "download":
        from getsinapi.collectors.caixa import download_monthly_xlsx

        artifact = download_monthly_xlsx(args.reference, settings=settings)
        print(f"Download validado: {artifact.path}")
        print(f"SHA-256: {artifact.sha256}")
        print(f"Tamanho: {artifact.size_bytes} bytes")
        return 0

    if args.command == "extract":
        from getsinapi.extractors.workbooks import extract_and_catalog

        result = extract_and_catalog(args.archive, args.reference, settings=settings)
        print(f"Arquivos extraídos: {len(result['files'])}")
        print(f"Planilhas catalogadas: {len(result['workbooks'])}")
        print(f"Catálogo: {result['catalog_path']}")
        for workbook in result["workbooks"]:
            print(f"- {workbook['file']} | abas: {len(workbook['sheets'])}")
        return 0

    parser.error("Comando não reconhecido.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
