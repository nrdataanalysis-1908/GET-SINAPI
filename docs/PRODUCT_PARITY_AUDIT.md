# Auditoria de paridade — PulseSINAPI × GET-SINAPI

Data da inspeção: 2026-11-11  
Base da branch de produto: `v3/development` (commit `018e6ccf9f6947990c75830c5d40c2366120da33`).

## 1. Referência PulseSINAPI

Arquivos inspecionados:
- `frontend/src/App.jsx`
- `frontend/src/components/Dashboard.jsx`
- `frontend/src/components/InsumosTable.jsx`
- `frontend/src/components/ComposicoesTable.jsx`
- `frontend/src/components/UfCompareDashboard.jsx`
- `frontend/src/components/BudgetBuilder.jsx`
- `backend/app.py`
- `backend/db.py`
- `scrapers/sinapi_insumos.py`
- `scripts/import_historical_data.py`
- `scripts/sync_csv_to_db.py`

Experiência principal do Pulse:
- filtros globais de UF, competência e desoneração;
- Dashboard;
- Insumos com busca e paginação;
- Composições com busca e detalhamento;
- comparação entre UFs;
- montagem de orçamento.

O repositório também contém CSVs flat e SQLite. A arquitetura e a interface são uma boa referência de escopo e simplicidade, mas o código não deve ser copiado sem correção.

## 2. Falhas da implementação de referência a não reproduzir

- O backend converte preço ausente em `0.0` durante consulta/cálculo.
- O cálculo recursivo retorna zero para ciclos de composição e pode ocultar a inconsistência.
- O scraper possui fallback de UF `SP` e regime desonerado fixo em caminhos de coleta.
- O importador histórico contém listas de dados mock/sintéticos.
- A sincronização apaga tabelas antes de inserir novamente e pode deixar a base vazia/parcial se a execução falhar.
- A conversão de preço/coeficiente com exceção usa zero como fallback.
- O dashboard usa amostras fixas de códigos e UFs (SP, RJ, MG, AC) em vez de derivar todos os indicadores exclusivamente da cobertura efetiva.

Esses pontos foram encontrados nos arquivos acima e precisam ser tratados como defeitos de referência, não como requisitos.

## 3. Estado real do GET-SINAPI V3

### Interface atual
O arquivo `frontend/src/App.tsx` contém nove páginas:
- Visão executiva;
- Catálogo unificado;
- Explorador de composições;
- Comparador de preços;
- Cesta e orçamento;
- Histórico de competências;
- Relatórios e exportações;
- Integridade e auditoria;
- Gestão de acessos.

A interface está mais extensa e segmentada do que a experiência central do Pulse. A página de catálogo reúne muitos filtros e também expõe arquivo, planilha e linha de origem. A rastreabilidade é valiosa, mas não precisa dominar a navegação cotidiana.

### API atual
`src/getsinapi/api/main.py` já possui:
- health e referências;
- resumo e analytics;
- consulta de insumos;
- consulta de composições e componentes;
- cálculo de custo de composição;
- cálculo de orçamento;
- catálogo avançado;
- exportação CSV/JSON;
- comparação de preços entre UFs.

A API já cobre boa parte das operações desejadas. O trabalho principal é simplificar a experiência, validar contratos e corrigir lacunas de integração, não reescrever tudo.

### Atualização
A V3 não apresenta na barra superior a ação de atualização que o usuário espera. A V4 acrescenta:
- botão `Atualizar base`;
- POST `/bootstrap-retry`;
- leitura periódica de `/bootstrap-status`;
- apresentação de mensagem, competência e percentual.

A implementação da atualização da V4 é candidata a reaproveitamento seletivo, depois de validar compatibilidade com a branch de produto e o pipeline histórico da V3.

## 4. Produto-alvo simplificado

Navegação principal recomendada:
1. Dashboard.
2. Insumos.
3. Composições.
4. Comparar preços.
5. Orçamento.
6. Histórico e atualização.

Ações transversais:
- filtros globais: UF, competência e regime;
- exportação CSV/Excel (PDF após validação);
- atualização da base;
- indicador discreto do estado da API/base.

A auditoria técnica e a linhagem continuam no banco, nos logs e nos manifestos. Não precisam de uma página de primeiro nível no fluxo cotidiano. A gestão de usuários também não deve ocupar a navegação do produto básico; manter somente se houver requisito real de múltiplos usuários locais.

## 5. Matriz de decisão

| Recurso | Estado atual | Decisão |
|---|---|---|
| Dashboard | V3 existente | Simplificar para indicadores úteis e derivados da base real |
| Busca de insumos | Catálogo avançado existente | Manter e simplificar filtros iniciais |
| Composições e coeficientes | Endpoints existentes | Manter; validar detalhamento e custo |
| Comparação por UF | Endpoint e página existentes | Manter; permitir seleção dinâmica de UFs disponíveis |
| Orçamento | Motor e página existentes | Manter; validar ausências, ciclos e memória de cálculo |
| Histórico | Página existente | Integrar à seleção global de competência |
| Exportação | CSV/JSON na API; UI menciona XLSX/PDF | Homologar cada formato antes de anunciá-lo |
| Atualização | Ação presente na V4 | Reaproveitar seletivamente após validação |
| Auditoria/linhagem | V3 possui metadados e manifestos | Preservar internamente; reduzir protagonismo visual |
| Usuários locais | V3/V4 possuem autenticação local | Reavaliar; não ampliar sem necessidade |
| Cloud/Supabase | Não necessário para a experiência offline | Fora do escopo básico |

## 6. Regras de integridade que diferenciam o GET-SINAPI

- Nunca inserir dados mock/sintéticos em produção.
- Nunca substituir ausência ou falha de parsing por zero.
- Preservar explicitamente zero publicado versus preço ausente.
- Não inferir UF, competência ou regime.
- Não mascarar registros inválidos: exibir estado e motivo.
- Não apagar histórico antes de uma atualização.
- Executar importação idempotente, transacional e recuperável.
- Permitir rastrear cada registro à publicação, arquivo e competência de origem.

## 7. Próximas etapas de implementação

1. Ajustar a interface da branch de produto para seis áreas principais, sem apagar endpoints úteis.
2. Incorporar a ação de atualização da V4 de forma compatível com o bootstrap histórico V3.
3. Homologar a API e o motor de orçamento com dados oficiais, principalmente estados de preço ausente, zero e componentes sem preço.
4. Validar exportações realmente implementadas.
5. Executar CI, build Windows e testes funcionais; só então gerar release/EXE.

## 8. Proteção de versões

Esta auditoria e a implementação de paridade ocorrem somente em `product/pulse-parity`. Nenhuma alteração é feita em `main`, V1, V2, V3 ou V4. Merge ou substituição de versão depende de autorização posterior.
