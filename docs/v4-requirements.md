# GET-SINAPI V4 — requisitos de produto e critérios de aceite

Versão-alvo: 4.0.0  
Branch: `v4/development`  
Produto: NR TECH — GET-SINAPI

## 1. Diretrizes gerais de interface

- Revisar todos os componentes, telas, diálogos, formulários, estados vazios, mensagens de validação e notificações.
- Remover textos instrutivos desnecessários, explicações redundantes, avisos autoexplicativos e frases com aparência de conteúdo gerado por IA.
- Não exibir orientações como “Crie a primeira conta administradora”, “As credenciais ficam armazenadas localmente com hash PBKDF2” ou textos equivalentes.
- A interface deve usar linguagem objetiva, técnica e natural. Exibir somente títulos, rótulos, dados, ações e mensagens operacionais indispensáveis.
- Não explicar ao usuário como o próprio sistema funciona, salvo quando a informação for necessária para uma decisão ou ação.
- Não criar telas, fluxos, campos ou funcionalidades que não tenham sido solicitados ou definidos neste escopo.
- Preservar identidade visual NR TECH e consistência entre módulos. Evitar excesso de espaços vazios, cartões decorativos, textos longos e elementos redundantes.
- Mensagens de erro devem identificar o problema e, quando possível, a ação corretiva; mensagens de sucesso devem ser breves.
- Não usar dados fictícios, exemplos simulados ou métricas demonstrativas na aplicação em produção.

## 2. Autenticação integrada ao AVANA Supabase

- O GET-SINAPI V4 deve autenticar os usuários pelo mesmo projeto Supabase Auth utilizado pelo AVANA: projeto `ccdkwqsrbsarhbdtzcin`.
- Reutilizar as contas existentes do Supabase Auth, permitindo login com os mesmos e-mails e senhas já cadastrados no AVANA.
- Não criar um sistema de autenticação local paralelo.
- Não implementar fluxo de “criar primeira conta administradora”, cadastro local de usuários ou armazenamento de senhas com PBKDF2.
- Não solicitar ao usuário que recrie uma conta que já existe no AVANA.
- Não copiar, exportar, consultar ou tentar recuperar senhas e hashes do Supabase Auth. O login deve ocorrer exclusivamente pelo fluxo oficial `signInWithPassword`.
- Validar no backend os JWT emitidos pelo Supabase Auth.
- Usar somente chave publicável/anon no cliente. Nunca incluir `service_role`, secret key ou credenciais administrativas no frontend, instalador ou executável.
- Não registrar senhas, tokens ou dados sensíveis em logs.
- Associar a identidade autenticada pelo UUID do Supabase a um perfil/autorização específico do GET-SINAPI, sem misturar cadastros, dados operacionais ou informações empresariais do AVANA.
- Não presumir que `public.users` contém todos os usuários: a fonte de identidade é o Supabase Auth. A autorização do GET-SINAPI deve ser resolvida por uma estrutura própria vinculada ao UUID autenticado.
- Todos os usuários autenticados podem acessar os módulos, painéis, consultas, mapas, relatórios e análises. Somente operações administrativas efetivamente restritas devem exigir autorização administrativa.
- A ausência de perfil de autorização do GET-SINAPI deve ser tratada sem criar uma conta local ou solicitar novo cadastro. Exibir mensagem objetiva e registrar o caso para provisionamento administrativo.
- Configurar URL e chave publicável por ambiente, sem segredos hardcoded.
- A integração deve funcionar tanto no ambiente de desenvolvimento quanto no executável Windows.

## 3. Catálogo — reorganização integral em uma única tela

Objetivo: concentrar consulta, indicadores, filtros, seleção e exportação na própria tela do Catálogo, com máxima área útil para a tabela.

### 3.1 Estrutura visual

1. Quatro cartões compactos no topo:
   - Total de registros.
   - Preço médio.
   - Menor preço.
   - Maior preço.
2. Barra de ações do Catálogo, com seleção e exportação, posicionada antes da área de filtros.
3. Área de filtros avançados, compacta e recolhível.
4. Tabela como elemento principal, ocupando a maior parte da área útil da tela.

### 3.2 Seleção e exportação

- Disponibilizar seleção individual por linha.
- Disponibilizar seleção de todos os registros da página.
- Disponibilizar seleção de todos os resultados correspondentes aos filtros, inclusive registros que não estejam na página visível.
- Exibir a quantidade de registros selecionados.
- Disponibilizar exportação CSV, XLSX, PDF e JSON na própria tela do Catálogo.
- Exportar o conjunto selecionado quando houver seleção explícita; na ausência de seleção, permitir exportar o resultado integral dos filtros aplicados.
- A exportação deve respeitar filtros, ordenação e escopo selecionado, sem limitar o resultado às linhas renderizadas ou à página atual.
- Não criar uma página separada de exportações para operações que pertencem ao Catálogo.
- Evitar duplicidade de comandos de exportação em diferentes áreas da interface.

### 3.3 Filtros e indicadores

- Filtros compactos, organizados e recolhíveis.
- Filtros devem operar sobre os dados reais disponíveis na base.
- Os quatro indicadores devem ser recalculados conforme os filtros aplicados.
- Indicadores, tabela, contagem de resultados e exportações devem refletir o mesmo conjunto filtrado.
- Preço médio, mínimo e máximo devem considerar somente registros válidos e comparáveis, respeitando unidade, competência, UF, regime e demais dimensões aplicáveis.
- Não somar preços unitários heterogêneos como se fossem valores totais.
- Preservar paginação, ordenação e desempenho em grandes volumes.
- A tabela deve ter rolagem própria quando necessário, sem obrigar o usuário a percorrer longas áreas de filtros ou cartões.
- Reduzir margens, espaçamentos e alturas desnecessárias. Priorizar densidade informacional e legibilidade.

## 4. Revisão dos componentes e navegação

- Revisar a aplicação inteira, não apenas o Catálogo: login, sidebar, topbar, dashboard, módulos de dados, tabelas, formulários, modais, diálogos, configurações, relatórios, auditoria e estados vazios.
- Remover textos de onboarding, instruções genéricas e chamadas que apenas repetem o título ou a função evidente de um botão.
- Não adicionar cadastro de usuários como recurso visível sem requisito funcional aprovado.
- Não criar opções administrativas fictícias ou telas sem operação real.
- A navegação deve refletir as funções efetivamente disponíveis e evitar módulos duplicados.
- Preservar o acesso ao portal oficial SINAPI/CAIXA e a identificação institucional NR TECH.
- Manter responsividade e compatibilidade com o executável Windows.

## 5. Regras de dados e continuidade

- Manter o isolamento dos dados do GET-SINAPI em relação aos dados empresariais do AVANA.
- Reutilizar do AVANA somente o serviço de identidade/autenticação Supabase Auth, não suas tabelas operacionais.
- Preservar histórico, integridade, manifestos, checksums, rastreabilidade e processamento incremental das bases SINAPI.
- Não baixar novamente competências já validadas, salvo evidência de corrupção, alteração ou necessidade de reprocessamento.
- Não substituir dados reais por fixtures ou dados de demonstração em builds de produção.

## 6. Critérios de aceite

1. Não existe fluxo de criação de primeira conta administradora local.
2. Não existe cadastro/autenticação local paralelo nem persistência local de senha com PBKDF2.
3. Uma conta já existente no AVANA autentica no GET-SINAPI pelo Supabase Auth.
4. O backend valida os JWT e a autorização do GET-SINAPI é vinculada ao UUID autenticado.
5. Nenhuma chave privilegiada ou segredo é distribuído no frontend ou executável.
6. Usuários autenticados acessam todos os módulos funcionais; operações administrativas permanecem protegidas.
7. O Catálogo apresenta os quatro indicadores no topo, ações de seleção/exportação antes dos filtros, filtros compactos e tabela ampliada.
8. Seleção de todos os resultados filtrados inclui registros fora da página atual.
9. CSV, XLSX, PDF e JSON exportam o escopo correto, sem limitação às linhas visíveis.
10. Indicadores, tabela, contagem e exportação permanecem coerentes após qualquer combinação de filtros.
11. Todas as telas e componentes foram revisados para remover textos instrutivos artificiais, redundâncias e fluxos não solicitados.
12. Testes automatizados cobrem autenticação, autorização, filtros, seleção global e exportações.
13. Build e executável Windows são testados antes de considerar a V4 homologada.

## 7. Controle de escopo

- Implementar estas mudanças exclusivamente em `v4/development`.
- Não alterar V1, V2, V3 ou `main`.
- Não abrir PR, fazer merge ou publicar release sem autorização.
- Registrar no projeto o que foi implementado e o que permanece pendente; não marcar requisito como concluído sem teste correspondente.
