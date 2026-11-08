import { FormEvent, useCallback, useEffect, useState } from "react";
import { Activity, Search, RefreshCw, ChevronLeft, ChevronRight, FileSpreadsheet } from "lucide-react";

type CatalogRow = {
  reference: string; record_type: "INSUMO" | "COMPOSICAO" | "COMPONENTE";
  code: string; description: string; unit: string; uf: string | null;
  regime: string | null; encargo_mode: string | null; table_type: string;
  value: string | null; value_type: string | null; composition_code: string | null;
  status: string | null; source_file: string; source_sheet: string; source_row: number;
};
type CatalogResponse = { items: CatalogRow[]; total: number; limit: number; offset: number };
type Filters = { search: string; uf: string; record_type: string };
const PAGE_SIZE = 100;
const STATES = ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"];

function formatValue(row: CatalogRow) {
  if (row.value === null || row.value === undefined || row.value === "") return "—";
  const value = Number(row.value);
  if (!Number.isFinite(value)) return row.value;
  return row.value_type === "PREÇO"
    ? value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
    : value.toLocaleString("pt-BR", { maximumFractionDigits: 8 });
}
function App() {
  const [draft, setDraft] = useState<Filters>({ search: "", uf: "", record_type: "" });
  const [filters, setFilters] = useState<Filters>({ search: "", uf: "", record_type: "" });
  const [data, setData] = useState<CatalogResponse>({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [apiOnline, setApiOnline] = useState(false);

  const load = useCallback(async (offset = 0, selected = filters) => {
    setBusy(true); setError("");
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      if (selected.search.trim()) params.set("search", selected.search.trim());
      if (selected.uf) params.set("uf", selected.uf);
      if (selected.record_type) params.set("record_type", selected.record_type);
      const response = await fetch(`/api/catalog?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Falha ao consultar o catálogo SINAPI.");
      setData(payload as CatalogResponse);
      setApiOnline(true);
    } catch (cause) {
      setApiOnline(false);
      setError(cause instanceof Error ? cause.message : "API SINAPI indisponível.");
    } finally { setBusy(false); }
  }, [filters]);

  useEffect(() => { void load(0, filters); }, [load, filters]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setFilters({ ...draft });
  }

  const page = Math.floor(data.offset / PAGE_SIZE) + 1;
  const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const firstRow = data.total ? data.offset + 1 : 0;
  const lastRow = Math.min(data.offset + data.items.length, data.total);

  return (
    <div className="app-shell catalog-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark"><Activity size={23} /></div>
          <div><span className="brand-name">GET-SINAPI</span><span className="brand-subtitle">NR DATA ANALYSIS</span></div>
        </div>
        <div className="workspace-label">CATÁLOGO OFICIAL</div>
        <div className="catalog-sidebar-copy">Consulta unificada dos dados publicados pela CAIXA.</div>
        <div className="sidebar-bottom">
          <div className="sidebar-status"><span className={apiOnline ? "status-dot" : "status-dot offline-dot"} /><span>{apiOnline ? "Serviço conectado" : "Aguardando conexão"}</span></div>
          <div className="sidebar-version">GET-SINAPI <span>v0.1.0</span></div>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">Plataforma <span>/</span> <strong>Catálogo SINAPI</strong></div>
          <div className="topbar-right"><span className="environment-tag">CAIXA · SINAPI</span></div>
        </header>
        <section className="page-heading catalog-heading">
          <div>
            <div className="eyebrow">NR DATA ANALYSIS / BASE PÚBLICA</div>
            <h1>Catálogo SINAPI</h1>
            <p>Insumos, composições e componentes em uma única listagem paginada.</p>
          </div>
          <div className="catalog-total"><span>REGISTROS LOCALIZADOS</span><strong>{data.total.toLocaleString("pt-BR")}</strong></div>
        </section>

        <section className="panel catalog-panel">
          <div className="panel-heading">
            <div><span className="panel-kicker">EXPLORADOR DE DADOS</span><h2>Base consolidada</h2></div>
            <div className="catalog-live"><span className={apiOnline ? "catalog-live-dot" : "catalog-live-dot offline-dot"} />{apiOnline ? "API operacional" : "API desconectada"}</div>
          </div>
          <form className="catalog-filters" onSubmit={applyFilters}>
            <label className="catalog-search"><span>BUSCA GLOBAL</span><div><Search size={16}/><input value={draft.search} onChange={e=>setDraft(v=>({...v,search:e.target.value}))} placeholder="Código, descrição ou arquivo"/></div></label>
            <label><span>UF</span><select value={draft.uf} onChange={e=>setDraft(v=>({...v,uf:e.target.value}))}><option value="">Todas as UFs</option>{STATES.map(state=><option key={state} value={state}>{state}</option>)}</select></label>
            <label><span>TIPO DE REGISTRO</span><select value={draft.record_type} onChange={e=>setDraft(v=>({...v,record_type:e.target.value}))}><option value="">Todos os registros</option><option value="INSUMO">Insumos</option><option value="COMPOSICAO">Composições</option><option value="COMPONENTE">Componentes</option></select></label>
            <button className="primary-button" disabled={busy} type="submit"><Search size={15}/>{busy ? "Consultando..." : "Aplicar filtros"}</button>
          </form>
          {error && <div className="alert-error" role="alert">{error}</div>}
          <div className="catalog-table-meta">
            <span><FileSpreadsheet size={16}/> Exibindo {firstRow.toLocaleString("pt-BR")}–{lastRow.toLocaleString("pt-BR")} de {data.total.toLocaleString("pt-BR")} registros</span>
            <button className="catalog-refresh" type="button" disabled={busy} onClick={()=>void load(data.offset,filters)}><RefreshCw size={14}/> Atualizar listagem</button>
          </div>
          <div className="data-table-wrap catalog-table-wrap">
            <table className="catalog-table">
              <thead><tr><th>Competência</th><th>Tipo</th><th>Código</th><th>Descrição</th><th>Un.</th><th>UF</th><th>Regime</th><th>Tabela</th><th>Valor / coef.</th><th>Arquivo de origem</th><th>Planilha</th></tr></thead>
              <tbody>
                {data.items.map((row,index)=><tr key={row.reference+row.record_type+row.code+row.source_file+row.source_row+index}>
                  <td className="code-cell">{row.reference}</td>
                  <td><span className={`catalog-type type-${row.record_type.toLowerCase()}`}>{row.record_type}</span></td>
                  <td className="code-cell">{row.record_type==="COMPONENTE" ? <>{row.code}<small className="catalog-parent">Composição {row.composition_code}</small></> : row.code}</td>
                  <td className="catalog-description">{row.description}</td><td>{row.unit || "—"}</td><td>{row.uf || "Nacional"}</td>
                  <td>{row.regime ? (row.regime==="desonerado"?"Desonerado":"Não desonerado") : "—"}</td>
                  <td>{row.table_type || "—"}</td><td className="price-cell">{formatValue(row)}</td>
                  <td className="catalog-source">{row.source_file}</td><td>{row.source_sheet} · {row.source_row}</td>
                </tr>)}
              </tbody>
            </table>
            {!busy && !data.items.length && <div className="empty-state">{error ? "Não foi possível carregar os registros." : "Nenhum registro corresponde aos filtros."}</div>}
            {busy && !data.items.length && <div className="empty-state">Consultando a base SINAPI...</div>}
          </div>
          <div className="catalog-pagination">
            <span>Página {page.toLocaleString("pt-BR")} de {lastPage.toLocaleString("pt-BR")}</span>
            <div><button className="secondary-button" type="button" disabled={busy||data.offset===0} onClick={()=>void load(Math.max(0,data.offset-PAGE_SIZE),filters)}><ChevronLeft size={15}/> Anterior</button>
              <button className="secondary-button" type="button" disabled={busy||data.offset+PAGE_SIZE>=data.total} onClick={()=>void load(data.offset+PAGE_SIZE,filters)}>Próxima <ChevronRight size={15}/></button></div>
          </div>
        </section>
        <footer className="footer"><span>GET-SINAPI <i>·</i> NR Data Analysis</span><span>Fonte: CAIXA Econômica Federal · SINAPI</span></footer>
      </main>
    </div>
  );
}
export default App;
