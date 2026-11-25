<div align="center">

<img src="assets/gets-inapi-hero.svg" alt="GET-SINAPI — private platform for SINAPI cost research and analysis" width="100%">

# GET-SINAPI

### DESKTOP PLATFORM · SINAPI RESEARCH · COST ENGINEERING

A Windows application that turns official CAIXA/SINAPI publications into traceable queries, analyses, comparisons, and budgets. The project also provides a Python command-line tool for batch exports.

![Python](https://img.shields.io/badge/Python-3.11%2B-1677C8?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/Interface-React%20%2B%20Vite-087BCE?style=for-the-badge&logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-21B8D5?style=for-the-badge&logo=sqlite&logoColor=white)
![Windows](https://img.shields.io/badge/System-Windows-1677C8?style=for-the-badge&logo=windows&logoColor=white)
[![PyPI version](https://img.shields.io/pypi/v/get-sinapi?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/get-sinapi/)

**Official data. Local processing. Traceable engineering decisions.**

[PyPI](https://pypi.org/project/get-sinapi/) · [Releases](https://github.com/nrdataanalysis-1908/GET-SINAPI/releases) · [Source code](https://github.com/nrdataanalysis-1908/GET-SINAPI)

</div>

---

## Current version — 3.1.3

Version 3.1.3 is published on PyPI and includes improvements to the command-line export experience:

- Optimized export from the local SQLite database, removing unnecessary global sorting.
- Progress reporting while records are processed in batches.
- Export to Excel (.xlsx), CSV, or both.
- Consolidated views and separate files/sheets by category.
- Interactive menu for selecting reference periods, state, regime, labor-cost settings, and search criteria.

Install/update:

```powershell
py -3.13 -m pip install --user --upgrade get-sinapi
getsinapi --version
getsinapi
```

Python distribution documentation: [GET-SINAPI on PyPI](https://pypi.org/project/get-sinapi/).

## Overview

GET-SINAPI combines a Windows desktop application and a Python command-line tool. The desktop application integrates a React interface, a local FastAPI service, Python processing, and SQLite persistence. The launcher starts the services on the same machine and opens the platform in the default browser; users do not need to start the servers manually.

The product uses PulseSINAPI as a functional UX reference while maintaining its own pipeline and rules for ingestion, quality, calculation, and traceability of official data.

> **Distribution:** the desktop application is distributed as a Windows executable. The command-line export tool is provided separately as a Python package on PyPI. Publishing the Python package does not turn the desktop application into a public web service.

## Available application features

- Dashboard with indicators derived from the database actually loaded.
- Input-cost queries with search, filters, and pagination.
- Composition queries and component/coefficient details.
- Price comparison by state and reference period, subject to available coverage.
- Budget basket and total calculations.
- History of reference periods present in the local database.
- Reports and exports provided by the current version.
- Database updates with state and progress tracking.
- Integrity, audit, and data-origin information.
- Local access-account management.

Result availability depends on the reference periods and official files actually downloaded, processed, and validated. Missing data must never be presented as zero-valued prices.

## Screenshots and architecture

<p align="center">
  <img src="assets/gets-inapi-architecture.svg" alt="GET-SINAPI local architecture: Windows launcher, React, FastAPI, Python, and SQLite" width="100%">
</p>

The desktop distribution architecture is entirely local:

| Component | Technology | Responsibility |
|---|---|---|
| Desktop application | Python / PyInstaller | Service startup and shutdown |
| Interface | React + Vite + TypeScript | Navigation, filters, tables, and visualizations |
| API | FastAPI | Queries, local authentication, and operations |
| Processing | Python | Collection, validation, normalization, and calculations |
| Persistence | SQLite | SINAPI data and local information |
| Authentication | PBKDF2 + local session | Login and account management on this computer |

## Local authentication

The first access allows the administrator account to be configured. The identifier may be the user's email address, together with a password of at least 12 characters.

- The first registered user receives the administrator role.
- The administrator can register other local accounts through access management.
- Passwords are not stored in plain text: the backend derives hashes with PBKDF2-HMAC-SHA256 and an individual salt.
- Local sessions last up to eight hours.
- Authentication records are stored in `security/users.json`, inside the application's data directory.

**Important limitation:** accounts are local and belong to that computer's data directory. Registering users in one installation does not automatically create accounts in other engineers' installations. Centralized login, remote revocation, account synchronization, and centralized budget sharing are not yet available.

## Storage and data directory

The application uses a local SQLite database. The data directory can be configured through environment settings; in the desktop distribution, the launcher prepares the runtime environment and maintains local logs.

Do not share the database file or authentication directory containing operational data without first assessing security and consistency implications. Multiple engineers working with the same database and budgets will require a centralized synchronization layer, which is not part of the current model.

## Desktop application installation

1. Download the Windows package from [Releases](https://github.com/nrdataanalysis-1908/GET-SINAPI/releases) or an authorized build artifact.
2. Extract the ZIP file to a local folder.
3. Run `GET-SINAPI-V3.exe`.
4. On first access, configure the administrator account and password.
5. On subsequent accesses, sign in with the local credentials.

The launcher starts the API and frontend locally, waits for the services to respond, and then opens the interface in the default browser.

## Command-line batch export

The Python package `get-sinapi` provides the terminal interface through the `getsinapi` command. The interactive menu allows users to select:

- All categories or only inputs, compositions, and components.
- A specific reference period or all loaded periods.
- A specific state or all available states.
- Tax relief regime and labor-cost settings.
- Search by code or description.
- Excel (.xlsx), CSV, or both output formats.

A full export generates a consolidated view of the selected records and individual files/sheets by category. In Excel, the consolidated view and each category use separate sheets; in CSV, a consolidated file and category-specific files are generated. CSV files use UTF-8 with BOM and semicolon delimiters for easier opening in Excel under Brazilian regional settings.

### Installation and execution

Version 3.1.3 is available on PyPI:

```powershell
py -3.13 -m pip install --user --upgrade get-sinapi
getsinapi
```

To open the export workflow directly:

```powershell
getsinapi export
```

The command reads the already-loaded local SQLite database; it does not download official packages again for every export. In the desktop installation, it uses the same data directory configured by the launcher. In standalone installations, set `GETSINAPI_DATABASE_PATH` to the correct `getsinapi.sqlite3` file. The terminal feature does not replace or modify the Windows executable.

### Export behavior

- Data is read in batches to control memory consumption.
- The terminal reports the number of records processed while files are generated.
- Export uses the local SQLite database and respects the selected filters.
- Files are saved to the user's Downloads folder.

## Local development

Requirements: Python 3.11+ and Node.js 20+.

### Application service

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
$env:GETSINAPI_DATABASE_PATH = "data/getsinapi.sqlite3"
uvicorn getsinapi.api.main:app --reload
```

Local API: `http://127.0.0.1:8000`  
Health check: `http://127.0.0.1:8000/api/health`  
OpenAPI documentation: `http://127.0.0.1:8000/docs`

### Interface

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Development frontend: `http://localhost:5173`. Vite forwards `/api` requests to the local API.

### Quality and tests

```powershell
ruff check .
pytest -v
```

The Windows workflow builds the frontend, packages the application with PyInstaller, and runs a UI and health-endpoint smoke test before publishing the artifact.

## Data pipeline and integrity

| Layer | Responsibility |
|---|---|
| Bronze | Preservation of received official packages |
| Staging | Controlled extraction and file inventory |
| Silver | Normalization, typing, and validation |
| Gold | Consolidated structures for queries and analysis |
| Application | Querying, comparison, calculation, and budgeting |

Principles:

- Official CAIXA publications as the reference source.
- No synthetic data in production.
- Distinguish published zero, missing value, and extraction failure.
- Preserve reference period, state, regime, and origin.
- Monetary values and coefficients handled with decimal precision.
- Incremental and idempotent updates that preserve valid history.
- Traceability back to publication, file, and source reference, according to available metadata.

## Coverage and known limitations

- Historical coverage depends on packages actually published, collected, and processed.
- Legacy layouts before 2025 require specific handling; full historical coverage must not be assumed.
- The desktop application's storage is local SQLite.
- Authentication is local, with no external provider.
- Data and budgets are not synchronized between computers.
- The current desktop distribution is for Windows; a hosted web version is outside the current scope.

## Technology stack

Python · React · TypeScript · Vite · FastAPI · SQLite · SQLAlchemy · Pandas · Pytest · Ruff · PyInstaller · GitHub Actions.

## License and third-party data

The source code is distributed under the MIT license, as described in [LICENSE](LICENSE). This license does not change the rights, terms of use, or attribution requirements applicable to third-party publications, trademarks, and data, including official SINAPI data.

---

<div align="center">

**GET-SINAPI**  
NR TECH · Data and Cost Engineering

*Accuracy at the source. Consistency in processing. Confidence in every query.*

</div>
