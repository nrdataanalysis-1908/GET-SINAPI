import { FormEvent, useEffect, useState } from "react";
import {
  Activity, Boxes, ChartColumn, CircleHelp, Database, Gauge, Layers3,
  Search, Settings2, ShieldCheck, Calculator, Plus, Trash2, MapPin, ChevronRight,
} from "lucide-react";

type ApiState = "checking" | "online" | "offline";
type Page = "overview" | "insumos" | "composicoes" | "orcamento";
type Reference = { reference: string; source_file: string; loaded_at: string };
type Summary = {
  reference: string; input_prices: number; compositions: number;
  composition_items: number; states: number; unavailable_prices: number;
};
type InputPrice = {
  code: string; description: string; unit: string; uf: string;
  regime: string | null; encargo_mode: string; table_type: string;
  price: string | null; status: string; price_origin: string | null;
};
type Composition = { code: string; description: string; unit: string; status: string | null };
type CostResult = {
  composition_code: string; total: number | null; status: string;
  issues: string[]; lines: Array<{ item_code: string; description: string; coefficient: number; unit_price: number | null; total: number | null; status: string }>;
};
type BudgetRow = { code: string; item_type: "INSUMO" | "COMPOSICAO"; quantity: string };
type BudgetResult = { total: number | null; status: string; issues: string[]; lines: Array<{ code: string; item_type: string; quantity: number; unit_cost: number | null; total: number | null; status: string }> };
type Analytics = { reference: string | null; references: Reference[]; totals: Summary; by_state: Array<{uf:string;observations:number;priced:number}>; by_reference: Array<{reference:string;input_prices:number;compositions:number;states:number}>; by_table: Array<{table_type:string;observations:number;priced:number}>; status: Array<{status:string;quantity:number}> };
const PAGE_SIZE = 50;
function Bars({items, labelKey, valueKey}:{items:Array<Record<string,any>>;labelKey:string;valueKey:string}) {
  const max = Math.max(1,...items.map(x=>Number(x[valueKey]||0)));
  return <div className="chart-bars">{items.map((item,i)=><div className="chart-bar-row" key={String(item[labelKey])+i}><span>{String(item[labelKey])}</span><div className="chart-track"><i style={{width:(Number(item[valueKey]||0)/max*100)+"%"}}/></div><b>{number(Number(item[valueKey]||0))}</b></div>)}</div>;
}
function Trend({items}:{items:Array<{reference:string;input_prices:number}>}) {
 const max=Math.max(1,...items.map(x=>x.input_prices));
 const pts=items.map((x,i)=>({x:24+(items.length<2?0:i*252/(items.length-1)),y:112-x.input_prices/max*88}));
 const path=pts.map((p,i)=>(i?"L":"M")+p.x+","+p.y).join(" ");
 return <div className="trend-wrap"><svg viewBox="0 0 300 140" role="img" aria-label="Observações de preços por competência"><path d="M24 112H276" stroke="#294158" strokeWidth="1"/><path d={path} fill="none" stroke="#60e6ff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>{pts.map((p,i)=><circle key={i} cx={p.x} cy={p.y} r="4" fill="#60e6ff"/> )}</svg><div className="trend-labels">{items.map(x=><span key={x.reference}>{x.reference}</span>)}</div></div>;
}

const navigation: Array<{ id: Page; label: string; icon: typeof Gauge }> = [
  { id: "overview", label: "Visão geral", icon: Gauge },
  { id: "insumos", label: "Insumos", icon: Boxes },
  { id: "composicoes", label: "Composições", icon: Layers3 },
  { id: "orcamento", label: "Orçamento", icon: Calculator },
];

const money = (value: number | string | null | undefined) =>
  value === null || value === undefined ? "—" : Number(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const number = (value: number | undefined) => (value ?? 0).toLocaleString("pt-BR");

function App() {
  const [page, setPage] = useState<Page>("overview");
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [references, setReferences] = useState<Reference[]>([]);
  const [reference, setReference] = useState("");
  const [uf, setUf] = useState("MG");
  const [regime, setRegime] = useState("nao_desonerado");
  const [encargoMode, setEncargoMode] = useState("com_encargos");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [priceTotal, setPriceTotal] = useState(0);
  const [compositionTotal, setCompositionTotal] = useState(0);
  const [pageIndex, setPageIndex] = useState(0);
  const [search, setSearch] = useState("");
  const [prices, setPrices] = useState<InputPrice[]>([]);
  const [compositions, setCompositions] = useState<Composition[]>([]);
  const [selectedCost, setSelectedCost] = useState<CostResult | null>(null);
  const [budgetRows, setBudgetRows] = useState<BudgetRow[]>([{ code: "", item_type: "COMPOSICAO", quantity: "1" }]);
  const [budgetResult, setBudgetResult] = useState<BudgetResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastCheck, setLastCheck] = useState("Aguardando verificação");

  const apiLabel = apiState === "online" ? "API operacional" : apiState === "offline" ? "API desconectada" : "Verificando API";

  async function request<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail ?? "Não foi possível consultar a API.");
    return payload as T;
  }

  async function loadAnalytics(ref = reference) {
    if (!ref) return;
    try { setAnalytics(await request<Analytics>(`/api/analytics?reference=${encodeURIComponent(ref)}`)); }
    catch { setAnalytics(null); }
  }

  async function loadSummary(ref = reference) {
    if (!ref) return;
    try {
      const data = await request<Summary>(`/api/summary?reference=${encodeURIComponent(ref)}`);
      setSummary(data);
      void loadAnalytics(ref);
      setError("");
    } catch (cause) {
      setSummary(null);
      setError(cause instanceof Error ? cause.message : "Falha ao consultar resumo.");
    }
  }

  useEffect(() => {
    let active = true;
    async function initialize() {
      try {
        const health = await request<{ status: string }>("/api/health");
        if (!active) return;
        setApiState(health.status === "ok" ? "online" : "offline");
        setLastCheck(new Date().toLocaleTimeString("pt-BR"));
        try {
          const refs = await request<Reference[]>("/api/references");
          if (!active) return;
          setReferences(refs);
          if (refs.length) setReference(refs[0].reference);
        } catch (cause) {
          if (!active) return;
          setError(cause instanceof Error ? cause.message : "Banco histórico ainda não inicializado.");
        }
      } catch (cause) {
        if (!active) return;
        setApiState("offline");
        setError(cause instanceof Error ? cause.message : "API indisponível.");
        setLastCheck(new Date().toLocaleTimeString("pt-BR"));
      }
    }
    void initialize();
    return () => { active = false; };
  }, []);

  useEffect(() => { if (reference) void loadSummary(reference); }, [reference]);

  async function searchPrices(event?: FormEvent, nextPage = 0) {
    event?.preventDefault();
    if (!reference) return;
    setBusy(true); setError("");
    try {
      const params = new URLSearchParams({
        reference, uf, encargo_mode: encargoMode, limit: String(PAGE_SIZE), offset: String(nextPage * PAGE_SIZE),
      });
      if (encargoMode !== "sem_encargos") params.set("regime", regime);
      if (search.trim()) params.set("search", search.trim());
      const [rows,count] = await Promise.all([
        request<InputPrice[]>(`/api/insumos?${params.toString()}`),
        request<{total:number}>(`/api/insumos/count?${params.toString()}`)
      ]);
      setPrices(rows); setPriceTotal(count.total); setPageIndex(nextPage);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao pesquisar insumos.");
    } finally { setBusy(false); }
  }

  async function searchCompositions(event?: FormEvent, nextPage = 0) {
    event?.preventDefault();
    if (!reference) return;
    setBusy(true); setError("");
    try {
      const params = new URLSearchParams({ reference, limit: String(PAGE_SIZE), offset: String(nextPage * PAGE_SIZE) });
      if (search.trim()) params.set("search", search.trim());
      const [rows,count] = await Promise.all([
        request<Composition[]>(`/api/composicoes?${params.toString()}`),
        request<{total:number}>(`/api/composicoes/count?${params.toString()}`)
      ]);
      setCompositions(rows); setCompositionTotal(count.total); setPageIndex(nextPage);
      setSelectedCost(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao pesquisar composições.");
    } finally { setBusy(false); }
  }

  async function calculateComposition(code: string) {
    setBusy(true); setError("");
    try {
      const params = new URLSearchParams({ reference, uf, encargo_mode: encargoMode });
      if (encargoMode !== "sem_encargos") params.set("regime", regime);
      setSelectedCost(await request<CostResult>(`/api/composicoes/${encodeURIComponent(code)}/custo?${params.toString()}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha no cálculo da composição.");
    } finally { setBusy(false); }
  }

  async function calculateBudget(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setBudgetResult(null);
    try {
      const items = budgetRows.filter((row) => row.code.trim() && Number(row.quantity) >= 0)
        .map((row) => ({ ...row, quantity: row.quantity }));
      if (!items.length) throw new Error("Informe ao menos um código e uma quantidade.");
      const result = await request<BudgetResult>("/api/budget", {
        method: "POST",
        body: JSON.stringify({
          reference, uf, regime: encargoMode === "sem_encargos" ? null : regime,
          encargo_mode: encargoMode, items,
        }),
      });
      setBudgetResult(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao calcular orçamento.");
    } finally { setBusy(false); }
  }

  function updateBudgetRow(index: number, field: keyof BudgetRow, value: string) {
    setBudgetRows((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row));
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark"><Activity size={23} /></div>
          <div><span className="brand-name">GET-SINAPI</span><span className="brand-subtitle">NR DATA ANALYSIS</span></div>
        </div>
        <div className="workspace-label">PLATAFORMA</div>
        <nav className="navigation" aria-label="Navegação principal">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button className={page === id ? "nav-item active" : "nav-item"} key={id} type="button" onClick={() => { setPage(id); setError(""); }}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {page === id && <span className="nav-indicator" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-status"><span className="status-dot" /><span>Ambiente de desenvolvimento</span></div>
          <button className="nav-item muted" type="button" disabled><Settings2 size={18} /><span>Configurações</span></button>
          <div className="sidebar-version">GET-SINAPI <span>v0.1.0</span></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">Plataforma <span>/</span> <strong>{navigation.find((item) => item.id === page)?.label}</strong></div>
          <div className="topbar-right"><span className="environment-tag">LOCAL / DEV</span><button className="icon-button" aria-label="Ajuda" type="button"><CircleHelp size={18} /></button></div>
        </header>

        <section className="page-heading">
          <div><div className="eyebrow">CENTRAL DE INTELIGÊNCIA DE CUSTOS</div><h1>{navigation.find((item) => item.id === page)?.label}</h1><p>Dados oficiais SINAPI para pesquisa, análise comparativa e composição de orçamentos.</p></div>
          <div className="reference-controls">
            <label>COMPETÊNCIA<select value={reference} onChange={(event) => setReference(event.target.value)}><option value="">Selecione</option>{references.map((item) => <option key={item.reference} value={item.reference}>{item.reference}</option>)}</select></label>
            <label>UF<select value={uf} onChange={(event) => setUf(event.target.value)}>{["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"].map((state) => <option key={state}>{state}</option>)}</select></label>
          </div>
        </section>

        {error && <div className="alert-error" role="alert">{error}</div>}
        {!references.length && <section className="system-banner"><div className="banner-icon"><Database size={21} /></div><div className="banner-copy"><strong>Nenhuma competência carregada</strong><span>Execute o pipeline de download, extração, normalização e carga para habilitar as consultas.</span></div><span className="development-pill">AGUARDANDO DADOS</span></section>}

        {page === "overview" && <>
          <section className="metrics-grid" aria-label="Indicadores SINAPI">
            <article className="metric-card"><div className="metric-top"><span>Observações de preços</span><Boxes size={18} /></div><div className="metric-value">{summary ? number(summary.input_prices) : "—"}</div><div className="metric-foot">Insumos × UFs × tabelas</div></article>
            <article className="metric-card"><div className="metric-top"><span>Composições</span><Layers3 size={18} /></div><div className="metric-value">{summary ? number(summary.compositions) : "—"}</div><div className="metric-foot">Composições analíticas</div></article>
            <article className="metric-card"><div className="metric-top"><span>Estados cobertos</span><MapPin size={18} /></div><div className="metric-value">{summary ? number(summary.states) : "—"}</div><div className="metric-foot">UFs com observações</div></article>
            <article className="metric-card"><div className="metric-top"><span>Preços indisponíveis</span><ShieldCheck size={18} /></div><div className="metric-value">{summary ? number(summary.unavailable_prices) : "—"}</div><div className="metric-foot">Ausentes ou não pesquisados</div></article>
          </section>
          <div className="analytics-grid">
            <section className="panel"><div className="panel-heading"><div><span className="panel-kicker">DISTRIBUIÇÃO GEOGRÁFICA</span><h2>Observações por UF</h2></div><span className="neutral-tag">Base selecionada</span></div>
              {analytics?.by_state.length ? <Bars items={analytics.by_state} labelKey="uf" valueKey="observations"/> : <div className="empty-state">Sem observações para a competência selecionada.</div>}
            </section>
            <section className="panel"><div className="panel-heading"><div><span className="panel-kicker">SÉRIE HISTÓRICA</span><h2>Volume de registros por competência</h2></div><span className="neutral-tag">Histórico carregado</span></div>
              {analytics?.by_reference.length ? <Trend items={analytics.by_reference}/> : <div className="empty-state">A série será exibida após a primeira carga.</div>}
            </section>
            <section className="panel"><div className="panel-heading"><div><span className="panel-kicker">COMPOSIÇÃO DA BASE</span><h2>Observações por tabela</h2></div></div>
              {analytics?.by_table.length ? <Bars items={analytics.by_table} labelKey="table_type" valueKey="observations"/> : <div className="empty-state">Sem dados para classificar.</div>}
            </section>
            <section className="panel connection-panel"><div className="panel-heading"><div><span className="panel-kicker">CONECTIVIDADE</span><h2>Serviços e persistência</h2></div><span className="live-indicator"><span /> LIVE</span></div>
              <div className="service-row"><div className="service-icon"><Activity size={17}/></div><div className="service-info"><strong>API GET-SINAPI</strong><small>FastAPI · /api/health</small></div><span className={apiState === "online" ? "service-state online" : "service-state offline"}>{apiLabel}</span></div>
              <div className="service-row"><div className="service-icon"><Database size={17}/></div><div className="service-info"><strong>Banco histórico</strong><small>SQLite · leitura da base persistida</small></div><span className="service-state online">{references.length} competências</span></div>
              <div className="service-row"><div className="service-icon"><ChartColumn size={17}/></div><div className="service-info"><strong>Camada analítica</strong><small>Agregações SQL reais</small></div><span className="service-state online">Ativa</span></div>
              <div className="service-foot">Última verificação: {lastCheck}</div>
            </section>
          </div>
          <section className="panel history-panel"><div className="panel-heading"><div><span className="panel-kicker">RASTREABILIDADE</span><h2>Competências disponíveis</h2></div><span className="neutral-tag">{references.length} carregadas</span></div>
            {references.length ? <div className="data-table-wrap"><table><thead><tr><th>Competência</th><th>Arquivo de origem</th><th>Carregada em</th><th>Registros de preços</th><th>Composições</th></tr></thead><tbody>{analytics?.by_reference.slice().reverse().map((item) => <tr key={item.reference}><td className="code-cell">{item.reference}</td><td>{references.find(x=>x.reference===item.reference)?.source_file ?? "—"}</td><td>{references.find(x=>x.reference===item.reference)?.loaded_at ?? "—"}</td><td>{number(item.input_prices)}</td><td>{number(item.compositions)}</td></tr>)}</tbody></table></div> : <div className="empty-state">Aguardando primeira carga histórica.</div>}
          </section>
        </>}

        {page === "insumos" && <section className="panel workspace-panel">
          <div className="panel-heading"><div><span className="panel-kicker">CATÁLOGO DE PREÇOS</span><h2>Pesquisa de insumos</h2></div><span className="neutral-tag">{number(priceTotal)} registros · página {pageIndex+1}</span></div>
          <form className="filter-bar" onSubmit={searchPrices}><label className="search-field"><Search size={17}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Código ou descrição do insumo"/></label><label>REGIME<select value={regime} disabled={encargoMode === "sem_encargos"} onChange={(event) => setRegime(event.target.value)}><option value="nao_desonerado">Não desonerado</option><option value="desonerado">Desonerado</option></select></label><label>ENCARGOS<select value={encargoMode} onChange={(event) => setEncargoMode(event.target.value)}><option value="com_encargos">Com encargos</option><option value="sem_encargos">Sem encargos</option></select></label><button className="primary-button" disabled={busy || !reference}><Search size={15}/>{busy ? "Consultando..." : "Pesquisar"}</button></form>
          <div className="data-table-wrap"><table><thead><tr><th>Código</th><th>Descrição</th><th>Un.</th><th>UF</th><th>Tabela</th><th>Preço</th><th>Situação</th></tr></thead><tbody>{prices.map((item, index) => <tr key={item.code + item.uf + item.table_type + index}><td className="code-cell">{item.code}</td><td>{item.description}</td><td>{item.unit}</td><td>{item.uf}</td><td>{item.table_type}</td><td className="price-cell">{money(item.price)}</td><td><span className={item.status === "reported" || item.status === "reported_zero" ? "status-label good" : "status-label warn"}>{item.status}</span></td></tr>)}</tbody></table>{!prices.length && <div className="empty-state">Nenhum registro encontrado para os filtros informados.</div>}</div><div className="pagination"><button className="secondary-button" type="button" disabled={pageIndex===0||busy} onClick={()=>void searchPrices(undefined,pageIndex-1)}>Anterior</button><span>{prices.length ? `${pageIndex*PAGE_SIZE+1}–${Math.min((pageIndex+1)*PAGE_SIZE,priceTotal)} de ${number(priceTotal)}` : `0 de ${number(priceTotal)}`}</span><button className="secondary-button" type="button" disabled={(pageIndex+1)*PAGE_SIZE>=priceTotal||busy} onClick={()=>void searchPrices(undefined,pageIndex+1)}>Próxima</button></div>
        </section>}

        {page === "composicoes" && <section className="panel workspace-panel">
          <div className="panel-heading"><div><span className="panel-kicker">BASE ANALÍTICA</span><h2>Composições SINAPI</h2></div><span className="neutral-tag">{number(compositionTotal)} registros · página {pageIndex+1}</span></div>
          <form className="filter-bar" onSubmit={searchCompositions}><label className="search-field"><Search size={17}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Código ou descrição da composição"/></label><button className="primary-button" disabled={busy || !reference}><Search size={15}/>{busy ? "Consultando..." : "Pesquisar"}</button></form>
          <div className="data-table-wrap"><table><thead><tr><th>Código</th><th>Descrição</th><th>Un.</th><th>Situação</th><th>Ação</th></tr></thead><tbody>{compositions.map((item) => <tr key={item.code}><td className="code-cell">{item.code}</td><td>{item.description}</td><td>{item.unit}</td><td>{item.status ?? "—"}</td><td><button className="text-action" type="button" onClick={() => calculateComposition(item.code)} disabled={busy}>Calcular custo <ChevronRight size={14}/></button></td></tr>)}</tbody></table>{!compositions.length && <div className="empty-state">Nenhuma composição encontrada para a pesquisa.</div>}</div><div className="pagination"><button className="secondary-button" type="button" disabled={pageIndex===0||busy} onClick={()=>void searchCompositions(undefined,pageIndex-1)}>Anterior</button><span>{compositions.length ? `${pageIndex*PAGE_SIZE+1}–${Math.min((pageIndex+1)*PAGE_SIZE,compositionTotal)} de ${number(compositionTotal)}` : `0 de ${number(compositionTotal)}`}</span><button className="secondary-button" type="button" disabled={(pageIndex+1)*PAGE_SIZE>=compositionTotal||busy} onClick={()=>void searchCompositions(undefined,pageIndex+1)}>Próxima</button></div>
          {selectedCost && <div className="cost-result"><div className="cost-result-head"><div><span className="panel-kicker">CUSTO UNITÁRIO · {selectedCost.composition_code}</span><h3>{money(selectedCost.total)}</h3></div><span className={selectedCost.status === "complete" ? "status-label good" : "status-label warn"}>{selectedCost.status}</span></div><div className="data-table-wrap"><table><thead><tr><th>Componente</th><th>Coeficiente</th><th>Preço unitário</th><th>Custo parcial</th></tr></thead><tbody>{selectedCost.lines.map((line, index) => <tr key={line.item_code + index}><td>{line.item_code} · {line.description}</td><td>{line.coefficient}</td><td>{money(line.unit_price)}</td><td>{money(line.total)}</td></tr>)}</tbody></table></div>{selectedCost.issues.map((issue) => <p className="issue-line" key={issue}>{issue}</p>)}</div>}
        </section>}

        {page === "orcamento" && <section className="panel workspace-panel">
          <div className="panel-heading"><div><span className="panel-kicker">COMPOSIÇÃO DE CUSTOS</span><h2>Orçamento por referência SINAPI</h2></div><span className="neutral-tag">Cálculo com Decimal</span></div>
          <form onSubmit={calculateBudget} className="budget-form">
            <div className="budget-context"><label>REGIME<select value={regime} disabled={encargoMode === "sem_encargos"} onChange={(event) => setRegime(event.target.value)}><option value="nao_desonerado">Não desonerado</option><option value="desonerado">Desonerado</option></select></label><label>ENCARGOS<select value={encargoMode} onChange={(event) => setEncargoMode(event.target.value)}><option value="com_encargos">Com encargos</option><option value="sem_encargos">Sem encargos</option></select></label></div>
            <div className="budget-lines">{budgetRows.map((row, index) => <div className="budget-line" key={index}><label>CÓDIGO SINAPI<input value={row.code} onChange={(event) => updateBudgetRow(index, "code", event.target.value)} placeholder="Ex.: 104658"/></label><label>TIPO<select value={row.item_type} onChange={(event) => updateBudgetRow(index, "item_type", event.target.value)}><option value="COMPOSICAO">Composição</option><option value="INSUMO">Insumo</option></select></label><label>QUANTIDADE<input type="number" min="0" step="any" value={row.quantity} onChange={(event) => updateBudgetRow(index, "quantity", event.target.value)}/></label><button className="remove-button" type="button" aria-label="Remover item" onClick={() => setBudgetRows((rows) => rows.length > 1 ? rows.filter((_, rowIndex) => rowIndex !== index) : rows)}><Trash2 size={16}/></button></div>)}</div>
            <div className="budget-actions"><button className="secondary-button" type="button" onClick={() => setBudgetRows((rows) => [...rows, { code: "", item_type: "COMPOSICAO", quantity: "1" }])}><Plus size={15}/>Adicionar item</button><button className="primary-button" disabled={busy || !reference}><Calculator size={15}/>{busy ? "Calculando..." : "Calcular orçamento"}</button></div>
          </form>
          {budgetResult && <div className="cost-result"><div className="cost-result-head"><div><span className="panel-kicker">TOTAL DO ORÇAMENTO</span><h3>{money(budgetResult.total)}</h3></div><span className={budgetResult.status === "complete" ? "status-label good" : "status-label warn"}>{budgetResult.status}</span></div><div className="data-table-wrap"><table><thead><tr><th>Código</th><th>Tipo</th><th>Quantidade</th><th>Custo unitário</th><th>Total</th></tr></thead><tbody>{budgetResult.lines.map((line, index) => <tr key={line.code + index}><td className="code-cell">{line.code}</td><td>{line.item_type}</td><td>{line.quantity}</td><td>{money(line.unit_cost)}</td><td>{money(line.total)}</td></tr>)}</tbody></table></div>{budgetResult.issues.map((issue) => <p className="issue-line" key={issue}>{issue}</p>)}</div>}
        </section>}

        <footer className="footer"><span>GET-SINAPI <i>·</i> NR Data Analysis</span><span>Dados oficiais, rastreabilidade e integridade.</span></footer>
      </main>
    </div>
  );
}

export default App;
