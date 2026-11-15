<div align="center">

<img src="assets/gets-inapi-hero.svg" alt="GET-SINAPI — plataforma privada para consulta e análise de custos SINAPI" width="100%">

# GET-SINAPI

### PLATAFORMA DESKTOP · CONSULTA SINAPI · ENGENHARIA DE CUSTOS

Aplicação privada para Windows que transforma publicações oficiais da CAIXA/SINAPI em consultas, análises, comparações e orçamentos rastreáveis.

![Python](https://img.shields.io/badge/Python-3.11%2B-1677C8?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-087BCE?style=for-the-badge&logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-21B8D5?style=for-the-badge&logo=sqlite&logoColor=white)
![Windows](https://img.shields.io/badge/Platform-Windows-1677C8?style=for-the-badge&logo=windows&logoColor=white)

**Dados oficiais. Processamento local. Decisões de engenharia com rastreabilidade.**

</div>

---

## Visão geral

O GET-SINAPI é um aplicativo desktop privado para Windows. Ele reúne uma interface React, uma API local FastAPI, processamento Python e persistência SQLite. O launcher inicia os serviços na própria máquina e abre a plataforma no navegador padrão; o usuário não precisa iniciar manualmente os servidores.

O produto utiliza o PulseSINAPI como referência de experiência funcional, mas mantém pipeline e regras próprias para ingestão, qualidade, cálculo e rastreabilidade dos dados oficiais.

> **Distribuição atual:** executável Windows privado. A aplicação não é um serviço web público nem possui autenticação centralizada na nuvem.

## Funcionalidades disponíveis na aplicação

- Dashboard com indicadores derivados da base efetivamente carregada.
- Consulta de insumos com pesquisa, filtros e paginação.
- Consulta de composições e detalhamento de componentes e coeficientes.
- Comparação de preços por UF e competência, conforme cobertura disponível.
- Cesta de orçamento e cálculo de totais.
- Histórico das competências presentes na base local.
- Relatórios e exportações disponibilizados pela versão atual.
- Atualização da base com acompanhamento de estado e progresso.
- Integridade, auditoria e informações de origem dos dados.
- Gestão local de contas de acesso.

A disponibilidade de resultados depende das competências e dos arquivos oficiais efetivamente baixados, processados e validados. O sistema não deve apresentar dados ausentes como se fossem preços iguais a zero.

## Capturas e arquitetura

<p align="center">
  <img src="assets/gets-inapi-architecture.svg" alt="Arquitetura local do GET-SINAPI: launcher Windows, React, FastAPI, Python e SQLite" width="100%">
</p>

A arquitetura é inteiramente local na distribuição atual:

| Componente | Tecnologia | Responsabilidade |
|---|---|---|
| Aplicação desktop | Python / PyInstaller | Inicialização e encerramento dos serviços |
| Interface | React + Vite + TypeScript | Navegação, filtros, tabelas e visualizações |
| API | FastAPI | Consultas, autenticação local e operações |
| Processamento | Python | Coleta, validação, normalização e cálculos |
| Persistência | SQLite | Dados SINAPI e informações locais |
| Autenticação | PBKDF2 + sessão local | Login e controle de contas neste computador |

## Autenticação local

O primeiro acesso permite configurar a conta administradora. O identificador pode ser o e-mail do usuário, acompanhado de uma senha com no mínimo 12 caracteres.

- O primeiro usuário cadastrado recebe o perfil de administrador.
- O administrador pode cadastrar outras contas locais pela área de gestão de acessos.
- As senhas não são armazenadas em texto puro: o backend deriva o hash com PBKDF2-HMAC-SHA256 e salt individual.
- A sessão local tem duração de até oito horas.
- Os registros de autenticação são mantidos no arquivo `security/users.json`, dentro do diretório de dados da aplicação.

**Limite importante:** as contas são locais e pertencem ao diretório de dados daquele computador. Cadastrar usuários em uma instalação não cria automaticamente contas nas instalações dos demais engenheiros. Ainda não há login centralizado, revogação remota, sincronização de contas ou compartilhamento central de orçamentos.

## Armazenamento e diretório de dados

A aplicação utiliza SQLite local. O diretório de dados pode ser definido por configuração de ambiente; na distribuição desktop, o launcher prepara o ambiente de execução e mantém logs locais.

Não compartilhe o arquivo de banco ou o diretório de autenticação contendo dados operacionais sem avaliar previamente as implicações de segurança e consistência. Para vários engenheiros trabalharem com a mesma base e os mesmos orçamentos, será necessária uma camada de sincronização central — não faz parte do modelo atual.

## Instalação e utilização

1. Baixe o pacote Windows disponibilizado na área de Releases ou no artefato de build autorizado.
2. Extraia o ZIP em uma pasta local.
3. Execute `GET-SINAPI-V3.exe`.
4. No primeiro acesso, configure o usuário administrador e a senha.
5. Nos acessos seguintes, entre com as credenciais locais.

O launcher inicia a API e o frontend localmente, aguarda os serviços responderem e então abre a interface no navegador padrão.

## Desenvolvimento local

Requisitos: Python 3.11+ e Node.js 20+.

### Backend

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
$env:GETSINAPI_DATABASE_PATH = "data/getsinapi.sqlite3"
uvicorn getsinapi.api.main:app --reload
```

API local: `http://127.0.0.1:8000`  
Health check: `http://127.0.0.1:8000/api/health`  
Documentação OpenAPI: `http://127.0.0.1:8000/docs`

### Frontend

Em outro terminal:

```powershell
cd frontend
npm install
npm run dev
```

Frontend de desenvolvimento: `http://localhost:5173`. O Vite encaminha as chamadas `/api` para a API local.

### Qualidade e testes

```powershell
ruff check .
pytest -v
```

O workflow Windows também compila o frontend, empacota a aplicação com PyInstaller e executa um smoke test da interface e do endpoint de saúde antes de publicar o artefato.

## Pipeline e integridade dos dados

| Camada | Responsabilidade |
|---|---|
| Bronze | Preservação dos pacotes oficiais recebidos |
| Staging | Extração controlada e inventário dos arquivos |
| Silver | Normalização, tipagem e validação |
| Gold | Estruturas consolidadas para consulta e análise |
| Aplicação | Consulta, comparação, cálculo e orçamento |

Princípios:

- Publicações oficiais da CAIXA como fonte de referência.
- Nenhum dado sintético em produção.
- Distinção entre zero publicado, valor ausente e falha de extração.
- Preservação de competência, UF, regime e origem.
- Valores monetários e coeficientes tratados com precisão decimal.
- Atualizações incrementais e idempotentes, preservando o histórico válido.
- Rastreabilidade até publicação, arquivo e referência de origem, conforme metadados disponíveis.

## Cobertura e limitações conhecidas

- A cobertura histórica depende dos pacotes efetivamente publicados, coletados e processados.
- Os layouts legados anteriores a 2025 exigem tratamento específico; não se deve presumir cobertura histórica integral.
- O armazenamento é SQLite local.
- A autenticação é local, sem provedor externo.
- Não há sincronização de dados ou orçamentos entre computadores.
- A distribuição atual é desktop Windows; uma versão web hospedada não faz parte do escopo vigente.

## Stack tecnológica

Python · React · TypeScript · Vite · FastAPI · SQLite · SQLAlchemy · Pandas · Pytest · Ruff · PyInstaller · GitHub Actions.

## Licença e dados de terceiros

O código-fonte é distribuído sob a licença MIT, conforme o arquivo [LICENSE](LICENSE). Essa licença não altera os direitos, termos de uso ou atribuição aplicáveis às publicações, marcas e dados de terceiros, incluindo os dados oficiais do SINAPI.

---

<div align="center">

**GET-SINAPI**  
NR TECH · Engenharia de Dados e Custos

*Precisão na origem. Consistência no processamento. Confiança na consulta.*

</div>
