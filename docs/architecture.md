# Arquitetura e decisões técnicas

## Diretrizes do produto

O GET-SINAPI será desenvolvido como uma plataforma independente para coleta, estruturação, validação e consulta de dados oficiais do SINAPI.

A implementação seguirá contratos de dados explícitos, rastreabilidade de ponta a ponta e separação entre processamento, persistência, API e interface.

## Melhorias obrigatórias

1. Não gerar dados sintéticos quando a coleta falhar. A falha deve ser explícita e auditável.
2. Não fixar UF, competência ou regime no parser.
3. Validar caminhos internos de ZIP contra path traversal antes da extração.
4. Não usar extração indiscriminada de arquivos compactados.
5. Não versionar cookies, credenciais, bancos locais ou arquivos brutos.
6. Não descartar histórico durante sincronizações; usar chaves naturais e operações idempotentes.
7. Não presumir que HTTP 200 significa ZIP válido.
8. Registrar URL, timestamp, SHA-256, tamanho, competência e resultado do processamento.
9. Separar testes unitários dos testes que dependem da rede.
10. Tratar indisponibilidade e rate limit com timeout, retry exponencial e respeito a Retry-After.

## Camadas de dados

- Bronze: pacotes originais, imutáveis e identificados por checksum.
- Staging: extração temporária isolada por execução.
- Silver: entidades normalizadas e validadas.
- Gold: tabelas e visões orientadas a consulta e orçamento.
- API: contratos explícitos para filtros por UF, competência e regime.
- Observabilidade: logs, manifestos de execução, métricas e relatório de qualidade.

## Entidades centrais

- Insumo: código, descrição e unidade.
- PrecoInsumo: insumo, UF, competência, regime e preço.
- Composicao: código, descrição e unidade.
- ComposicaoItem: composição, item constituinte, tipo e coeficiente.
- FonteArquivo: URL, nome, competência, checksum, tamanho e data de coleta.
- ExecucaoPipeline: início/fim, etapa, status, contagens e erros.

## Sequência de implementação

1. Fundação do pacote, configuração, testes e CI.
2. Catálogo versionado de fontes oficiais e descoberta dos pacotes.
3. Coletor HTTP resiliente com validação ZIP, checksum e manifesto.
4. Extração segura e identificação de planilhas.
5. Parsers independentes para insumos e composições, com layouts versionados.
6. Validação, deduplicação e consolidação histórica.
7. Persistência relacional e migrações.
8. API de consulta e cálculo de composições/orçamentos.
9. Dashboard e automação agendada.
10. Testes de ponta a ponta com arquivos oficiais reais.

## Critério de qualidade

Nenhuma competência será marcada como concluída apenas porque o processo terminou sem exceção. Validaremos arquivos esperados, planilhas encontradas, registros lidos/rejeitados, duplicidades, UFs, regimes e integridade referencial. Dados ausentes nunca serão preenchidos com valores inventados.


## 7. Fonte oficial e ressalva de preços

A página oficial da CAIXA informa que, a partir de 2025, os relatórios mensais são distribuídos em dois ZIPs: XLSX e PDF. O ZIP XLSX reúne relatórios de famílias e coeficientes, manutenções, percentual de mão de obra e relatórios de insumos/composições para todas as UFs. O ZIP PDF reúne relatórios analíticos, custos de composições e preços de insumos.

O padrão de URL para o pacote XLSX mensal da CAIXA é:
https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/SINAPI-AAAA-MM-formato-xlsx.zip

A URL deve ser tratada como padrão técnico observado e validada em cada execução; não se deve presumir que toda competência esteja publicada.

A nota oficial consultada registra que, a partir da referência outubro/2025, preços de insumos e custos de composições seriam excepcionalmente divulgados zerados em razão da indisponibilidade mensal dos dados de preços do IBGE. Como essa nota pode ser sucedida por atualizações posteriores, a vigência deve ser verificada por competência nas notas oficiais e no próprio pacote. O pipeline deve preservar preço informado como zero, preço ausente e preço indisponível como estados distintos; nunca inferir preço de mercado a partir de zero.
