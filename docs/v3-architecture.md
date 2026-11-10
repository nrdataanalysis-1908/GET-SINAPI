# GET-SINAPI V3 — arquitetura proposta

## Princípios

A V3 preserva a fundação local Python/FastAPI/SQLite da V2 e introduz evolução incremental, sem destruir o histórico ou exigir conectividade permanente para consultar os dados já carregados. A autenticação remota é separada do armazenamento analítico local.

## Componentes

### Desktop e frontend
- React + TypeScript.
- Shell desktop Windows e API local.
- Todos os painéis analíticos visíveis a qualquer sessão autenticada.
- Filtros globais em estado compartilhado e serializável.
- Gráficos com cross-filtering e mapa estadual.
- Identidade NR TECH, copyright e atalho oficial CAIXA persistentes.

### Identidade
- Supabase Auth do projeto AVANA como provedor de identidade.
- Fluxo OAuth/PKCE quando viável no desktop, com callback seguro; alternativa de fluxo de senha deve usar exclusivamente endpoint/SDK oficial de Auth e TLS.
- Backend valida JWT via mecanismo oficial; não confia em dados de perfil editáveis.
- Permissões administrativas GET-SINAPI armazenadas em configuração própria, vinculadas ao UUID Auth.
- Segredos somente em configuração segura/runtime; nunca no frontend público ou no Git.

### Coleta histórica
- Catálogo de competências separado do pipeline de processamento.
- Descoberta por fonte oficial CAIXA; sondagem mensal só é considerada evidência quando resposta e ZIP passam validação.
- Orquestrador de jobs com concorrência limitada.
- Checkpoint persistente por competência.
- Camadas Bronze (ZIP original), Staging (XLSX), Silver (registros normalizados) e Gold (agregações).
- Manifesto SHA-256, tamanho, contagens, URL, status e versão do parser.
- Retentativa isolada e reprocessamento transacional por competência.
- Idempotência baseada em estado completo validado, não apenas existência do arquivo.

### Dados e analytics
- SQLite como armazenamento embarcado local; avaliar DuckDB/Parquet para consultas analíticas extensas, sem introduzir dependência até benchmark.
- Consultas agregadas no backend, paginação e filtros validados.
- Definições métricas versionadas, com unidade, regime, competência e universo explícitos.
- Malha geográfica oficial das UFs versionada e licenciada, com chave UF/IBGE.
- Exportações reproduzem filtros e escopo do resultado consultado.

## Segurança e privacidade

- Nunca importar tabelas empresariais AVANA para o GET-SINAPI.
- Nunca copiar senha ou hash do Auth.
- Não incluir service_role/secret key em aplicativo desktop.
- Sessões curtas, renovação controlada e logout explícito.
- Autorização administrativa não baseada em `user_metadata`.
- Não registrar tokens, senhas ou cabeçalhos Authorization em logs.

## Plano de entrega incremental

1. Fundação V3: branch isolada, versionamento, documentação, identidade visual, direitos autorais e atalho CAIXA.
2. Auth: integração Supabase Auth e autorização própria do GET-SINAPI, com testes de segurança.
3. Histórico: catálogo oficial, descoberta completa, checkpoints, retomada e idempotência.
4. Analytics: contratos de filtros globais, métricas e agregações testadas.
5. Visualização geográfica: mapa por UF, heatmaps e cross-filtering.
6. Governança: auditoria visual, relatórios e rastreabilidade integral.
7. Homologação: testes de ponta a ponta, CI e pacote Windows.

Nenhuma etapa é considerada concluída apenas por compilar. Cada uma exige testes e evidência operacional.
