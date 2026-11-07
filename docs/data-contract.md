# GET-SINAPI — Contrato de Dados

**Versão:** 1.0  
**Estado:** proposta técnica para validação  
**Fonte primária:** arquivos oficiais do SINAPI/CAIXA

## 1. Objetivo

Definir o modelo canônico para coletar, catalogar, interpretar, validar, persistir e disponibilizar dados oficiais do SINAPI. O contrato separa dados publicados, metadados de proveniência e estruturas derivadas para consulta.

## 2. Princípios

- Preservar arquivos originais e checksums.
- Manter proveniência até arquivo, planilha e linha sempre que aplicável.
- Preservar códigos oficiais como texto, sem perder zeros à esquerda.
- Utilizar precisão decimal para valores monetários e coeficientes.
- Não converter ausência em zero.
- Não confundir preço de insumo com custo de composição.
- Não confundir regime de desoneração com modalidade de encargos sociais.
- Preservar histórico por competência, sem sobrescrita destrutiva.
- Garantir reprocessamento idempotente.
- Registrar rejeições e anomalias sem descarte silencioso.
- Não gerar dados sintéticos para completar lacunas.

## 3. Dimensões e domínios

### 3.1 Competência

Formato canônico: YYYY-MM. A competência identifica o período de referência publicado e deve permanecer distinta das datas de emissão, publicação, coleta e processamento.

### 3.2 Unidade federativa

Sigla oficial de duas letras, validada contra o conjunto das 27 UFs brasileiras.

### 3.3 Regime de desoneração

Domínio Regime:
- WITH_DESONERATION: com desoneração.
- WITHOUT_DESONERATION: sem desoneração.

Representa o regime aplicável aos encargos sociais, conforme o relatório de origem.

### 3.4 Modalidade de encargos sociais

Domínio EncargoMode:
- WITH_SOCIAL_CHARGES: com encargos sociais.
- WITHOUT_SOCIAL_CHARGES: sem encargos sociais.

É dimensão distinta do regime de desoneração. CSE representa custos sem encargos sociais; não deve ser modelado como terceiro regime de desoneração.

### 3.5 Situação do preço

Domínio PriceStatus:
- REPORTED: valor informado e diferente de zero.
- REPORTED_ZERO: valor explicitamente informado como zero.
- MISSING: célula ou informação ausente na fonte.
- NOT_RESEARCHED: item explicitamente identificado como não pesquisado.

Célula vazia, hífen, texto de não pesquisado e zero numérico não são equivalentes. A classificação deve considerar o conteúdo bruto e o contexto do layout.

### 3.6 Situação da composição

Preservar em domínio próprio os valores observados:
- COM CUSTO
- COM PREÇO
- SEM CUSTO
- SEM PREÇO

O parser deve admitir novos valores publicados, como EM ESTUDO, sem reinterpretá-los como situação de preço individual.

### 3.7 Origem do preço

Preservar os códigos publicados:
- C: coletado.
- CR: coeficiente de representatividade.

Novos códigos devem ser registrados sem perda do valor original.

## 4. Entidades canônicas

Os nomes abaixo são nomes lógicos do domínio. A representação física poderá variar entre Parquet e PostgreSQL, desde que preserve o contrato.

### 4.1 ReferencePeriod

| Campo | Tipo lógico | Regra |
|---|---|---|
| reference_period | string | Chave natural, formato YYYY-MM |
| issue_date | date, nullable | Data de emissão publicada |
| published_at | timestamp, nullable | Data de publicação, se identificada |
| created_at | timestamp | Registro no sistema |

### 4.2 SourceFile

| Campo | Tipo lógico | Regra |
|---|---|---|
| source_file_id | UUID/string | Identificador interno |
| reference_period | string | Competência |
| filename | string | Nome original |
| source_url | string, nullable | URL de origem |
| file_format | string | Formato detectado |
| file_size_bytes | integer | Tamanho em bytes |
| sha256 | string | SHA-256 do conteúdo |
| downloaded_at | timestamp | Data/hora da coleta |
| source_type | string | Família documental |
| extraction_status | string | Resultado da extração |

O checksum identifica o conteúdo, não substitui nome ou competência. Arquivos diferentes podem pertencer à mesma competência.

### 4.3 InputItem

| Campo | Tipo lógico | Regra |
|---|---|---|
| input_code | string | Código oficial |
| description | string | Descrição publicada |
| unit | string | Unidade publicada |
| classification | string, nullable | Classificação publicada |
| reference_period | string | Competência da observação cadastral |
| source_file_id | UUID/string | Proveniência |

Mudanças de descrição, unidade ou classificação devem ser preservadas por competência.

### 4.4 InputPrice

| Campo | Tipo lógico | Regra |
|---|---|---|
| input_code | string | Referência ao insumo |
| reference_period | string | Competência |
| uf | char(2) | UF |
| report_type | enum/string | ISD, ICD ou ISE |
| price | decimal, nullable | Valor publicado |
| price_status | enum | Situação do preço |
| price_origin | string, nullable | C ou CR, quando publicado |
| source_file_id | UUID/string | Arquivo de origem |
| source_sheet | string | Aba de origem |
| source_row | integer | Linha de origem |

Mapeamento:
- ISD: preços de insumos com encargos sociais sem desoneração.
- ICD: preços de insumos com encargos sociais com desoneração.
- ISE: preços de insumos sem encargos sociais.

Chave de negócio proposta: input_code, reference_period, uf, report_type. A implementação deve verificar duplicidades reais antes de impor unicidade física.

### 4.5 Composition

| Campo | Tipo lógico | Regra |
|---|---|---|
| composition_code | string | Código oficial |
| reference_period | string | Competência |
| description | string | Descrição publicada |
| unit | string | Unidade publicada |
| group_code | string, nullable | Grupo publicado |
| composition_status | string, nullable | Situação publicada |
| source_file_id | UUID/string | Proveniência |

Chave de negócio proposta: composition_code e reference_period.

### 4.6 CompositionItem

| Campo | Tipo lógico | Regra |
|---|---|---|
| composition_code | string | Composição pai |
| reference_period | string | Competência |
| item_code | string | Código do elemento |
| item_type | string | Tipo publicado, por exemplo COMPOSICAO ou INSUMO |
| description | string | Descrição publicada |
| unit | string, nullable | Unidade |
| coefficient | decimal, nullable | Coeficiente publicado |
| source_file_id | UUID/string | Proveniência |
| source_sheet | string | Aba |
| source_row | integer | Linha |

A composição pode conter insumos ou outras composições. A ordem dos itens e códigos repetidos devem ser preservados; a chave física deverá incluir identificador de linha ou ordem de origem.

### 4.7 CompositionCost

| Campo | Tipo lógico | Regra |
|---|---|---|
| composition_code | string | Código da composição |
| reference_period | string | Competência |
| uf | char(2) | UF |
| regime | enum | Regime de desoneração |
| encargo_mode | enum | Modalidade de encargos |
| total_cost | decimal, nullable | Custo publicado |
| percentage_as | decimal, nullable | Percentual atribuído a São Paulo, quando publicado |
| cost_status | string, nullable | Situação publicada |
| source_file_id | UUID/string | Arquivo de origem |
| source_sheet | string | Aba |
| source_row | integer | Linha |

Mapeamento:
- CSD: custos de composições sem desoneração.
- CCD: custos de composições com desoneração.
- CSE: custos de composições sem encargos sociais.

O campo percentage_as preserva a semântica publicada. Não representa percentual de encargos nem preço.

### 4.8 LaborCost

| Campo | Tipo lógico | Regra |
|---|---|---|
| composition_code | string | Código da composição |
| reference_period | string | Competência |
| uf | char(2) | UF |
| encargo_mode | enum | Modalidade publicada na aba |
| value | decimal, nullable | Valor publicado |
| source_file_id | UUID/string | Proveniência |
| source_sheet | string | Aba |
| source_row | integer | Linha |

A distinção entre abas com e sem desoneração deve ser preservada explicitamente.

### 4.9 TechnicalCoefficient

| Campo | Tipo lógico | Regra |
|---|---|---|
| family_code | string | Código da família |
| item_code | string | Código do item |
| reference_period | string | Competência |
| uf | char(2) | UF |
| coefficient | decimal, nullable | Coeficiente publicado |
| category | string | REPRESENTATIVO ou REPRESENTADO |
| source_file_id | UUID/string | Proveniência |
| source_sheet | string | Aba |
| source_row | integer | Linha |

### 4.10 MaintenanceEvent

| Campo | Tipo lógico | Regra |
|---|---|---|
| reference_period | string | Competência |
| event_type | string | Tipo literal publicado |
| item_code | string, nullable | Código relacionado |
| description | string, nullable | Descrição publicada |
| source_file_id | UUID/string | Proveniência |
| source_sheet | string | Aba |
| source_row | integer | Linha |

### 4.11 PipelineExecution

| Campo | Tipo lógico | Regra |
|---|---|---|
| execution_id | UUID/string | Identificador |
| reference_period | string | Competência |
| stage | string | Etapa executada |
| started_at | timestamp | Início |
| finished_at | timestamp, nullable | Término |
| status | string | Resultado |
| records_read | integer | Registros lidos |
| records_accepted | integer | Registros aceitos |
| records_rejected | integer | Registros rejeitados |
| error_details | JSON/string, nullable | Erros e ocorrências |

## 5. Proveniência e rastreabilidade

Toda entidade derivada deverá manter vínculo com a fonte. Para registros tabulares, a proveniência mínima é arquivo, aba e linha. Transformações que combinem múltiplas fontes devem permitir recuperar todas as origens relevantes.

Manifestos devem registrar competência, arquivos, checksums, versões de layout/parser, contagens e resultado de validação.

## 6. Camadas de dados

- Bronze: arquivos oficiais originais, imutáveis e identificados por checksum.
- Staging: extração isolada por competência e execução.
- Silver: entidades normalizadas, tipadas, validadas e rastreáveis.
- Gold: conjuntos consolidados e visões orientadas a consulta e análise.

Formatos previstos:
- JSON para manifestos e metadados de execução.
- Parquet para conjuntos analíticos.
- PostgreSQL para persistência relacional e consultas.
- API para disponibilização controlada.

A escolha do formato não altera a semântica do contrato.

## 7. Contrato de consulta e disponibilização

A plataforma deverá evoluir para disponibilizar:
- Consulta de insumos por código, descrição e classificação.
- Consulta de preços por UF, competência, origem e modalidade.
- Comparação histórica de preços e custos.
- Consulta de composições e elementos constituintes.
- Consulta de custos publicados por UF e regime.
- Consulta de mão de obra e coeficientes técnicos.
- Consulta de eventos de manutenção.
- Exportação de conjuntos em formatos estruturados.
- Consulta de proveniência, integridade e qualidade dos dados.

Cálculos derivados, simulações e estimativas deverão ser identificados como resultados do GET-SINAPI, nunca apresentados como valores oficiais publicados.

## 8. Critérios de aceite

1. Parsers produzem registros compatíveis com as entidades.
2. Layouts oficiais são cobertos por testes automatizados.
3. Valores ausentes, zeros e estados textuais são distinguidos.
4. Regime e modalidade de encargos são representados separadamente.
5. Chaves e duplicidades são verificadas com dados reais.
6. Proveniência pode ser recuperada para cada registro.
7. Reprocessamento é idempotente.
8. Manifestos registram contagens, rejeições e versões.
9. Dados consolidados podem ser consultados e exportados.

## 9. Governança de mudanças

Esta é a versão inicial do contrato canônico. Mudanças de domínio, semântica, chaves ou tipos deverão ser registradas com justificativa, impacto sobre dados históricos e atualização dos testes.
