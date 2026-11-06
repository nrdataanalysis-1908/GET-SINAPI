# GET-SINAPI

Pipeline de coleta, validação, normalização e disponibilização dos dados públicos do SINAPI/CAIXA.

Projeto privado da NR Data Analysis para uso técnico e operacional na Avana Engenharia.

## Objetivo

Construir uma base histórica confiável de insumos e composições SINAPI, com rastreabilidade por competência, UF e regime de encargos (desonerado/não desonerado). O PulseSINAPI é a referência funcional pública; o GET-SINAPI terá implementação própria, validações adicionais e separação entre dados brutos, tratados e camada de consulta.

## Escopo funcional

1. Descobrir e obter pacotes oficiais publicados pela CAIXA.
2. Armazenar arquivos originais sem adulteração, com metadados e checksum.
3. Extrair ZIP/XLS/XLSX com segurança.
4. Identificar layouts e cabeçalhos variáveis.
5. Normalizar insumos, composições, coeficientes, preços, UF, competência e regime.
6. Validar integridade, duplicidades, valores e cobertura.
7. Consolidar histórico sem sobrescrever a origem.
8. Persistir em banco relacional e disponibilizar consultas via API.
9. Automatizar execução, testes, logs e relatórios de qualidade.

## Princípios de engenharia

- Fonte oficial como autoridade; nenhum dado fictício ou fallback sintético em produção.
- Idempotência: reprocessar o mesmo pacote não duplica registros.
- Rastreabilidade: cada registro tratado aponta para arquivo, competência e execução.
- Integridade: downloads validados por tamanho, assinatura ZIP e SHA-256.
- Resiliência: timeout, retry com backoff e respeito aos limites do servidor.
- Segurança: extração protegida contra path traversal; segredos somente em variáveis de ambiente.
- Separação Bronze/Silver/Gold e contratos de dados versionados.

## Arquitetura planejada

- .github/workflows: CI e, posteriormente, pipeline agendado.
- config: configuração por ambiente.
- data/raw: pacotes oficiais imutáveis, não versionados.
- data/staging: extração temporária, não versionada.
- data/processed: dados normalizados, não versionados.
- data/manifests: manifestos e metadados.
- docs: arquitetura, fontes e contratos.
- src/getsinapi: coletores, extratores, processadores, storage, API e observabilidade.
- tests: testes unitários e de integração.

## Coleta inicial

O pacote XLSX mensal pode ser obtido por competência explícita:

    getsinapi download --reference 2026-09

O coletor valida o formato ZIP, calcula SHA-256, grava o arquivo original em data/raw e cria um manifesto em data/manifests. A competência é informada explicitamente; não presumimos que o mês corrente já esteja publicado.

Atenção: a CAIXA publicou nota sobre valores de preços/custos zerados excepcionalmente desde a referência 2025-10. O parser deverá manter essa condição distinta de preço real igual a zero.

## Estado do projeto

Etapa 1 — fundação técnica: estrutura do pacote, configuração, documentação arquitetural e CI inicial.

A extração segura e o catálogo inicial de planilhas XLSX já estão implementados. O catálogo registra arquivos, abas, dimensões e SHA-256; a interpretação semântica das colunas ainda será desenvolvida e validada com arquivos oficiais reais.\n\nAs etapas seguintes serão implementadas progressivamente: catálogo de fontes oficiais, coletor, extração, normalização, persistência histórica, API e automação agendada.

## Desenvolvimento

Requer Python 3.11 ou superior.

Comandos PowerShell:

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev]"
    pytest
    getsinapi --version
    getsinapi extract --archive data/raw/SINAPI-2026-09-formato-xlsx.zip --reference 2026-09

## Referência técnica

- PulseSINAPI: https://github.com/PulseDataLabs/PulseSINAPI
- Portal SINAPI/CAIXA: https://www.caixa.gov.br/

Código do GET-SINAPI sob MIT. Arquivos e dados de terceiros permanecem sujeitos às respectivas condições de uso e atribuição.
