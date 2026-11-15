# GET-SINAPI — Paridade funcional com PulseSINAPI

## Objetivo

Entregar um aplicativo privado para Windows com a experiência funcional essencial do PulseSINAPI, preservando a ingestão oficial da CAIXA e corrigindo problemas de qualidade de dados identificados na implementação de referência.

O PulseSINAPI é referência de produto e experiência, não fonte de verdade nem dependência obrigatória de execução.

## Experiência final

1. Dashboard: resumo da base, competências disponíveis, UFs e estado da última atualização.
2. Insumos: pesquisa por código/descrição e filtros por UF, competência e regime.
3. Composições: pesquisa, custo publicado e detalhamento dos componentes e coeficientes.
4. Comparação: comparação de preços entre UFs e entre competências.
5. Orçamento: seleção de UF, competência e regime; inclusão de insumos/composições, quantidades e cálculo de totais.
6. Exportação: CSV e Excel para consultas e orçamentos; PDF quando o fluxo estiver validado.
7. Atualização: ação explícita para buscar, validar e incorporar novas publicações sem apagar o histórico.

## Regras inegociáveis de dados

- A publicação oficial da CAIXA é a fonte de verdade.
- Não gerar dados fictícios, sintéticos ou de demonstração no banco de produção.
- Não preencher preço, coeficiente, UF, regime ou competência com valores presumidos.
- Preservar zero publicado, valor ausente, não pesquisado, não aplicável e erro de extração como estados distintos.
- Cada lote deve preservar competência, UF, arquivo de origem, checksum e data de processamento.
- Atualizações devem ser idempotentes e transacionais; falhas não podem apagar dados históricos válidos.
- Dados de terceiros podem ser usados apenas como referência ou auditoria, nunca como substituição silenciosa da fonte oficial.

## Arquitetura-alvo

- Interface: React, com navegação lateral e páginas objetivas.
- Serviço local: FastAPI.
- Persistência: SQLite.
- Coleta e processamento: Python, reaproveitando o pipeline oficial já desenvolvido.
- Distribuição: aplicativo/EXE Windows, operando localmente e sem exigir serviço externo para consultas.
- API: endpoints locais documentados para integração futura.

## Fora do escopo inicial

- Autenticação multiusuário/Supabase sem necessidade operacional comprovada.
- Painéis analíticos avançados que não ajudem diretamente a consultar, comparar ou orçar.
- Infraestrutura cloud obrigatória.
- Módulos experimentais ou redundantes.
- Reescrita do coletor apenas para imitar a implementação interna do Pulse.

## Plano de execução

### Fase 1 — Auditoria e inventário
- Mapear telas, endpoints, tabelas e fluxos atuais da V3.
- Mapear a experiência essencial do Pulse.
- Classificar cada recurso como manter, simplificar, corrigir ou retirar da interface.
- Identificar funcionalidades existentes que ainda não estão integradas ou homologadas.

### Fase 2 — Paridade da interface
- Organizar navegação em Dashboard, Insumos, Composições, Comparação, Orçamento e Atualização.
- Reutilizar componentes existentes quando forem estáveis.
- Remover exposição de ferramentas internas de engenharia de dados da navegação principal.

### Fase 3 — Dados e consultas
- Homologar ingestão por competência e UF.
- Validar preços, regimes, coeficientes e ausência de dados.
- Garantir paginação, filtros e resultados consistentes.
- Validar cálculo de composições e orçamento contra os relatórios oficiais.

### Fase 4 — Distribuição e aceite
- Gerar EXE Windows.
- Testar instalação, inicialização, atualização, persistência e operação offline.
- Testar exportações.
- Homologar amostras com arquivos oficiais da CAIXA.

## Critérios de aceite

- O usuário consegue pesquisar insumos e composições sem manipular planilhas.
- O usuário consegue detalhar coeficientes e consultar preços por UF/competência/regime.
- O usuário consegue comparar valores e montar orçamento reproduzível.
- O usuário consegue exportar os resultados.
- A atualização preserva histórico e informa falhas sem mascarar dados.
- A interface não apresenta como disponível um dado que não foi efetivamente carregado e validado.
- O aplicativo funciona localmente após instalação, sem depender de PulseSINAPI ou SINPRES.

## Política de mudança

Esta branch parte da V3 para preservar o trabalho existente. V1, V2, V3, V4 e main permanecem intactas. Nenhum merge será feito sem autorização expressa.
