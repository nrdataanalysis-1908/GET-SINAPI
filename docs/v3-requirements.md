# GET-SINAPI V3 — requisitos e critérios de aceite

Versão-alvo: 3.0.0  
Branch de desenvolvimento: `v3/development`  
Produto: NR TECH — GET-SINAPI

## Regras de preservação

- Manter integralmente a V1 e a V2 em suas respectivas branches; a V3 evolui em branch isolada.
- Preservar a autoria e a identidade do produto: `© NR TECH · GET-SINAPI. Todos os direitos reservados.` em todas as telas e nos relatórios/exportações.
- Manter atalho permanente para o portal oficial do SINAPI na CAIXA: https://www.caixa.gov.br/poder-publico/modernizacao-gestao/sinapi/Paginas/default.aspx.
- Não remover módulos existentes sem decisão expressa do responsável pelo produto.
- Não incluir credenciais, tokens ou segredos no repositório.
- Não misturar dados empresariais do AVANA com os dados SINAPI.

## 1. Autenticação e acesso

- Reutilizar a autenticação existente do projeto Supabase AVANA (`ccdkwqsrbsarhbdtzcin`) para permitir que as contas existentes usem os mesmos e-mails e senhas.
- Senhas não são recuperáveis nem devem ser copiadas do Supabase Auth; autenticar pelo serviço Auth existente.
- Nunca exportar hashes, ler senhas, duplicar credenciais em arquivo local ou persistir senha em logs.
- Usar chave publicável/anon no cliente e validar JWT no backend; jamais expor service_role/secret key.
- A autorização administrativa do GET-SINAPI deve ser própria e segura, sem confiar em `user_metadata` editável.
- Todos os usuários autenticados podem visualizar todos os painéis, mapas, relatórios e análises. Gestão de contas/configurações administrativas permanece restrita.
- Configuração por ambiente, sem segredos hardcoded.

## 2. Ingestão histórica integral e incremental

- Descobrir todas as competências efetivamente publicadas pela CAIXA, desde a primeira competência comprovadamente disponível até a mais recente.
- A data inicial do acervo não deve ser presumida: precisa ser demonstrada por catálogo oficial, índice oficial ou sondagem validada de URLs mensais.
- Na primeira execução de uma instalação, executar a carga histórica completa.
- Manter checkpoint individual por competência e estados: descoberta, download, validação, extração, normalização, carga, concluída e falha.
- Registrar URL/fonte, nome, tamanho, SHA-256, timestamps, contagens, versão do parser e erro.
- Não baixar novamente artefatos válidos e já carregados. Revalidar somente quando houver evidência de alteração, corrupção, ausência ou necessidade de correção.
- Retomar falhas por competência, sem reiniciar toda a série.
- Retry com backoff, concorrência limitada, timeouts, cancelamento seguro e persistência do progresso.
- Preservar competências já carregadas; carga por competência deve ser transacional e idempotente.
- Tratar competências ausentes na fonte como lacunas verificadas, não como falhas infinitas.
- Suportar streaming/lotes para reduzir consumo de memória em históricos extensos.

## 3. Analytics e painéis

- Todos os painéis ficam disponíveis a todos os usuários autenticados.
- Filtros globais devem cruzar KPIs, gráficos, mapa, tabelas, drill-down e exportações.
- Dimensões: período/competência, UF, região, código, descrição, unidade, tipo de registro, regime, modalidade de encargos, tabela, situação e faixa de preço.
- Métricas: cobertura, contagem, preços unitários, mínimos/máximos/medianas, variação temporal e comparações regionais, sempre com semântica estatística explícita.
- Não somar preços unitários heterogêneos como se fossem custo total. Orçamentos devem usar quantidades e composições coerentes.
- Gráficos interativos com cross-filtering e drill-down, usando apenas dados efetivamente carregados.
- Mapa do Brasil por UF e heatmaps regionais com geometria oficial e agregações rastreáveis.
- Exibir competência, regime, unidade, população/amostra e fonte de cada indicador relevante.

## 4. Governança, autoria e relatórios

- Auditoria de integridade com SHA-256 e manifesto por artefato.
- Linhagem até competência, arquivo, planilha, aba, linha e versão do parser.
- Exportações CSV, XLSX, PDF e JSON com filtros aplicados, data de geração, fonte, competência, critérios e identificação NR TECH.
- Rodapé de autoria e direitos autorais em todas as telas; autoria também em relatórios e documentos gerados.
- Atalho CAIXA acessível no menu/topbar e no fluxo de atualização.

## 5. Critérios de aceite

1. Teste de primeira instalação demonstra descoberta e processamento de todas as competências publicadas e verificáveis.
2. Segunda execução não baixa novamente competências íntegras e completas.
3. Falha simulada em uma competência retoma somente aquela competência.
4. Arquivo com checksum divergente é isolado e reprocessado sem apagar outras competências.
5. Todos os usuários autenticados acessam todos os painéis; rotas administrativas continuam protegidas.
6. Login Supabase aceita conta AVANA existente sem copiar ou armazenar senha fora do fluxo Auth.
7. Filtros globais produzem os mesmos recortes em KPIs, gráficos, mapas, tabelas e exportações.
8. Indicadores financeiros têm unidade, regime e população definidos; nenhum dado fictício em produção.
9. Mapa associa corretamente cada UF e não apresenta agregados sem amostra.
10. Copyright NR TECH e link CAIXA aparecem na interface e nos relatórios.
11. CI, testes automatizados e empacotamento Windows passam antes de declarar release homologada.

## Estado de implementação

Este documento define o escopo e os critérios de aceite. A criação da branch e os primeiros ajustes de identidade/versionamento não significam que autenticação Supabase, carga histórica integral, mapas ou analytics globais já estejam concluídos. Cada frente deve ser implementada e validada antes de ser marcada como pronta.
