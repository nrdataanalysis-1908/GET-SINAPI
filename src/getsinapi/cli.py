"""Interface de linha de comando do GET-SINAPI."""

from __future__ import annotations

import argparse
import os
import platform
import sys
from pathlib import Path

from getsinapi import __version__
from getsinapi.config import Settings


CYAN = "\033[96m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _enable_ansi() -> bool:
    """Habilita cores ANSI no terminal, com fallback seguro."""
    if not sys.stdout.isatty():
        return False
    if platform.system() != "Windows":
        return True
    try:
        import ctypes
        import msvcrt

        handle = msvcrt.get_osfhandle(sys.stdout.fileno())
        mode = ctypes.c_uint()
        kernel32 = ctypes.windll.kernel32
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError, ValueError):
        return False


ANSI_ENABLED = _enable_ansi()


def _paint(value: str, color: str) -> str:
    return f"{color}{value}{RESET}" if ANSI_ENABLED else value


def _show_header() -> None:
    print()
    print(_paint("╔══════════════════════════════════════════════════════════════════╗", CYAN))
    print(_paint("║                       GET-SINAPI  |  CAIXA                       ║", CYAN))
    print(_paint("║              PLATAFORMA DE DADOS E EXPORTAÇÃO SINAPI             ║", BLUE))
    print(_paint("║                         NR TECH  •  v" + __version__.ljust(23) + "║", CYAN))
    print(_paint("╚══════════════════════════════════════════════════════════════════╝", CYAN))
    print("  FONTE OFICIAL : CAIXA ECONÔMICA FEDERAL")
    print("  OPERAÇÃO      : Exportação local | Excel e CSV")
    print(_paint("  © 2026 Nadison Roberto | NR TECH — Software sob licença MIT.", BLUE))


def _parse_multi_selection(answer: str, total: int) -> list[int] | None:
    """Converte números separados por vírgula em índices; None representa 'todas'."""
    value = answer.strip().upper()
    if not value or value == "A":
        return None
    tokens = [item.strip() for item in value.split(",")]
    if any(not token.isdigit() for token in tokens):
        raise ValueError("Use números separados por vírgula ou A para todas.")
    indexes = [int(token) for token in tokens]
    if any(index < 1 or index > total for index in indexes):
        raise ValueError(f"Seleção fora do intervalo. Informe valores de 1 a {total}.")
    return list(dict.fromkeys(indexes))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="getsinapi",
        description="Coleta, consulta e exporta dados SINAPI/CAIXA.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("check-config", help="Valida as configurações locais.")
    commands.add_parser("export", help="Abre o menu interativo de exportação em lote.")

    download = commands.add_parser("download", help="Baixa o pacote XLSX mensal oficial da CAIXA.")
    download.add_argument("--reference", required=True, help="Competência no formato AAAA-MM")

    extract = commands.add_parser("extract", help="Extrai ZIP e cataloga planilhas XLSX.")
    extract.add_argument("--archive", required=True, type=Path, help="Caminho do ZIP já baixado.")
    extract.add_argument("--reference", required=True, help="Competência no formato AAAA-MM")

    parse = commands.add_parser("parse", help="Normaliza preços e composições para Silver.")
    parse.add_argument("--workbook", required=True, type=Path, help="XLSX oficial de referência.")
    parse.add_argument("--reference", required=True, help="Competência no formato AAAA-MM")

    load = commands.add_parser("load", help="Carrega os artefatos Silver no SQLite.")
    load.add_argument("--reference", required=True, help="Competência no formato AAAA-MM")
    return parser


def _ask_choice(prompt: str, options: dict[str, str], default: str | None = None) -> str:
    while True:
        suffix = f" [padrão {default}]" if default else ""
        answer = input(f"{prompt}{suffix}: ").strip() or (default or "")
        if answer in options:
            return answer
        print("Opção inválida. Escolha uma das opções exibidas.")


def _export_menu(settings: Settings) -> int:
    from getsinapi.exporter import available_references, export_catalog

    desktop_data = Path(os.getenv("LOCALAPPDATA", Path.home())) / "NRTech" / "GET-SINAPI-V3" / "data"
    candidates = [
        Path(os.getenv("GETSINAPI_DATABASE_PATH", "")) if os.getenv("GETSINAPI_DATABASE_PATH") else None,
        desktop_data / "getsinapi.sqlite3",
        settings.data_dir / "getsinapi.sqlite3",
    ]
    database = next((path for path in candidates if path and path.is_file()),
                    desktop_data / "getsinapi.sqlite3" if os.name == "nt" else settings.data_dir / "getsinapi.sqlite3")
    if not database.is_file():
        print(f"Banco SINAPI não encontrado: {database}")
        print("Inicialize a base com os comandos download, extract, parse e load.")
        return 2

    _show_header()
    print(_paint("\n01  |  MODO DE EXPORTAÇÃO", BLUE))
    print("-" * 68)
    print("  [1] Exportar tudo — insumos, composições e componentes")
    print("  [2] Personalizar categorias")
    mode = _ask_choice("Selecione", {"1": "Tudo", "2": "Personalizado"}, "1")

    categories = ["INSUMO", "COMPOSICAO", "COMPONENTE"]
    if mode == "2":
        print(_paint("\n02  |  CATEGORIAS", BLUE))
        print("  [1] Insumos       [2] Composições       [3] Componentes")
        selected = input("Categorias (ex.: 1,3): ").strip()
        mapping = {"1": "INSUMO", "2": "COMPOSICAO", "3": "COMPONENTE"}
        try:
            indexes = _parse_multi_selection(selected, 3)
            categories = list(mapping.values()) if indexes is None else [
                mapping[str(index)] for index in indexes
            ]
        except ValueError as exc:
            print(_paint(f"Seleção inválida: {exc}", YELLOW))
            return 2

    refs = available_references(database)
    if not refs:
        print("A base SQLite não possui competências carregadas.")
        return 2
    print(_paint("\n03  |  COMPETÊNCIAS DISPONÍVEIS", BLUE))
    for index, reference in enumerate(refs, start=1):
        print(_paint(f"  [{index:>2}] {reference}", CYAN))
    print(_paint("  [ A] Todas as competências", BLUE))
    reference_choice = input("Competências (ex.: 1,2,5 ou A) [A]: ").strip().upper() or "A"
    try:
        indexes = _parse_multi_selection(reference_choice, len(refs))
        references = None if indexes is None else [refs[index - 1] for index in indexes]
    except ValueError as exc:
        print(_paint(f"Competência inválida: {exc}", YELLOW))
        return 2

    uf = input("\nUF (duas letras) ou ENTER para todas: ").strip().upper() or None
    if uf and (len(uf) != 2 or not uf.isalpha()):
        print("UF inválida.")
        return 2

    regime_choice = _ask_choice(
        "Regime: 1 todos | 2 desonerado | 3 não desonerado",
        {"1": "all", "2": "desonerado", "3": "nao_desonerado"},
        "1",
    )
    regime = None if regime_choice == "1" else regime_choice

    encargo_choice = _ask_choice(
        "Encargos: 1 todos | 2 com encargos | 3 sem encargos",
        {"1": "all", "2": "com_encargos", "3": "sem_encargos"},
        "1",
    )
    encargo_mode = None if encargo_choice == "1" else encargo_choice

    search = input("Pesquisar por código/descrição (ENTER para sem filtro): ").strip() or None
    file_format = _ask_choice(
        "Formato: 1 Excel (.xlsx) | 2 CSV | 3 Excel + CSV",
        {"1": "xlsx", "2": "csv", "3": "both"},
        "1",
    )
    default_output = database.parent / "exports"
    output_text = input(f"Pasta de destino [{default_output}]: ").strip()
    output_dir = Path(output_text).expanduser() if output_text else default_output

    print(_paint("\n04  |  PROCESSAMENTO", BLUE))
    print("Iniciando extração da base local...")
    generated = export_catalog(
        database,
        output_dir,
        file_format=file_format,
        references=references,
        uf=uf,
        categories=categories,
        regime=regime,
        encargo_mode=encargo_mode,
        search=search,
    )
    print(_paint(f"\nSTATUS: EXPORTAÇÃO CONCLUÍDA | ARQUIVOS: {len(generated)}", CYAN))
    for path in generated:
        print(f"  • {path}")
    print(_paint("\\nGET-SINAPI | CAIXA — NR TECH", BLUE))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.from_env()

    if args.command in (None, "export"):
        settings.create_data_directories()
        return _export_menu(settings)

    if args.command == "check-config":
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

    if args.command == "parse":
        from getsinapi.pipeline.normalize import normalize_reference_workbook
        result = normalize_reference_workbook(args.workbook, reference=args.reference, settings=settings)
        print(f"Competência: {result['reference']}")
        print(f"Preços: {result['counts']['input_prices']:,}")
        print(f"Composições: {result['counts']['compositions']:,}")
        print(f"Itens de composição: {result['counts']['composition_items']:,}")
        print(f"Advertências: {result['warning_count']:,}")
        print(f"Manifesto: {result['manifest_path']}")
        return 0

    if args.command == "load":
        from getsinapi.storage.sqlite import load_silver_reference
        result = load_silver_reference(settings.processed_dir, reference=args.reference)
        print(f"Competência carregada: {result['reference']}")
        print(f"Preços: {result['input_prices']:,}")
        print(f"Composições: {result['compositions']:,}")
        print(f"Itens: {result['composition_items']:,}")
        print(f"Banco: {result['database_path']}")
        return 0

    parser.error("Comando não reconhecido.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
