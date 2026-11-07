import { useEffect, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  Boxes,
  ChartColumn,
  CircleHelp,
  Database,
  FileSpreadsheet,
  Gauge,
  Layers3,
  Search,
  Settings2,
  ShieldCheck,
} from "lucide-react";

type ApiState = "checking" | "online" | "offline";

const navigation = [
  { label: "Visão geral", icon: Gauge, active: true },
  { label: "Insumos", icon: Boxes, active: false },
  { label: "Composições", icon: Layers3, active: false },
  { label: "Comparador", icon: ChartColumn, active: false },
  { label: "Importações", icon: ArrowDownToLine, active: false },
];

function App() {
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [lastCheck, setLastCheck] = useState<string>("Aguardando verificação");

  useEffect(() => {
    let active = true;
    fetch("/api/health")
      .then((response) => {
        if (!response.ok) throw new Error("API indisponível");
        return response.json();
      })
      .then((data: { status: string }) => {
        if (!active) return;
        setApiState(data.status === "ok" ? "online" : "offline");
        setLastCheck(new Date().toLocaleTimeString("pt-BR"));
      })
      .catch(() => {
        if (!active) return;
        setApiState("offline");
        setLastCheck(new Date().toLocaleTimeString("pt-BR"));
      });
    return () => { active = false; };
  }, []);

  const apiLabel = apiState === "online" ? "API operacional" : apiState === "offline" ? "API desconectada" : "Verificando API";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark"><Activity size={23} /></div>
          <div><span className="brand-name">GET-SINAPI</span><span className="brand-subtitle">NR DATA ANALYSIS</span></div>
        </div>
        <div className="workspace-label">PLATAFORMA</div>
        <nav className="navigation" aria-label="Navegação principal">
          {navigation.map(({ label, icon: Icon, active }) => (
            <button className={active ? "nav-item active" : "nav-item"} key={label} type="button" disabled={!active}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {label === "Visão geral" && <span className="nav-indicator" />}
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
          <div className="breadcrumb">Plataforma <span>/</span> <strong>Visão geral</strong></div>
          <div className="topbar-right"><span className="environment-tag">LOCAL / DEV</span><button className="icon-button" aria-label="Ajuda" type="button"><CircleHelp size={18} /></button></div>
        </header>

        <section className="page-heading">
          <div><div className="eyebrow">CENTRAL DE INTELIGÊNCIA DE CUSTOS</div><h1>Visão geral</h1><p>Acompanhe a estrutura, a ingestão e a disponibilidade dos dados SINAPI.</p></div>
          <div className="reference-chip"><FileSpreadsheet size={16} /><span>Competência de referência</span><strong>—</strong></div>
        </section>

        <section className="system-banner">
          <div className="banner-icon"><ShieldCheck size={21} /></div>
          <div className="banner-copy"><strong>Fundação do sistema em construção</strong><span>Os indicadores serão habilitados à medida que os dados oficiais forem processados e validados.</span></div>
          <span className="development-pill">FASE 01 · FUNDAÇÃO</span>
        </section>

        <section className="metrics-grid" aria-label="Indicadores do sistema">
          <article className="metric-card"><div className="metric-top"><span>Insumos catalogados</span><Boxes size={18} /></div><div className="metric-value">—</div><div className="metric-foot">Aguardando parser de insumos</div></article>
          <article className="metric-card"><div className="metric-top"><span>Composições</span><Layers3 size={18} /></div><div className="metric-value">—</div><div className="metric-foot">Aguardando parser analítico</div></article>
          <article className="metric-card"><div className="metric-top"><span>Competências processadas</span><Database size={18} /></div><div className="metric-value">—</div><div className="metric-foot">Histórico ainda não persistido</div></article>
          <article className="metric-card"><div className="metric-top"><span>Qualidade dos dados</span><ShieldCheck size={18} /></div><div className="metric-value">—</div><div className="metric-foot">Sem execução de validação integrada</div></article>
        </section>

        <div className="content-grid">
          <section className="panel pipeline-panel">
            <div className="panel-heading"><div><span className="panel-kicker">FLUXO DE DADOS</span><h2>Pipeline SINAPI</h2></div><span className="neutral-tag">Arquitetura planejada</span></div>
            <div className="pipeline-flow">
              <div className="pipeline-stage"><span className="stage-icon"><ArrowDownToLine size={19} /></span><strong>Bronze</strong><small>Pacote original</small><em>Implementado</em></div>
              <div className="stage-connector" />
              <div className="pipeline-stage"><span className="stage-icon"><FileSpreadsheet size={19} /></span><strong>Staging</strong><small>Extração e catálogo</small><em>Implementado</em></div>
              <div className="stage-connector pending" />
              <div className="pipeline-stage pending-stage"><span className="stage-icon"><ShieldCheck size={19} /></span><strong>Silver</strong><small>Dados normalizados</small><em>Em desenvolvimento</em></div>
              <div className="stage-connector pending" />
              <div className="pipeline-stage pending-stage"><span className="stage-icon"><ChartColumn size={19} /></span><strong>Gold</strong><small>Consultas e análises</small><em>Planejado</em></div>
            </div>
            <div className="panel-note"><Activity size={15} /><span>O fluxo exibido representa o estágio de implementação, não uma execução em tempo real.</span></div>
          </section>

          <section className="panel connection-panel">
            <div className="panel-heading"><div><span className="panel-kicker">CONECTIVIDADE</span><h2>Serviços</h2></div><span className="live-indicator"><span /> LIVE</span></div>
            <div className="service-row"><div className="service-icon"><Activity size={17} /></div><div className="service-info"><strong>API GET-SINAPI</strong><small>FastAPI · /api/health</small></div><span className={apiState === "online" ? "service-state online" : apiState === "offline" ? "service-state offline" : "service-state checking"}>{apiLabel}</span></div>
            <div className="service-row"><div className="service-icon"><Database size={17} /></div><div className="service-info"><strong>Banco de dados</strong><small>PostgreSQL</small></div><span className="service-state pending">Não configurado</span></div>
            <div className="service-row"><div className="service-icon"><Search size={17} /></div><div className="service-info"><strong>Camada de consulta</strong><small>Endpoints de negócio</small></div><span className="service-state pending">Em desenvolvimento</span></div>
            <div className="service-foot">Última verificação da API: {lastCheck}</div>
          </section>
        </div>

        <section className="panel roadmap-panel">
          <div className="panel-heading"><div><span className="panel-kicker">EVOLUÇÃO DO PRODUTO</span><h2>Próximas entregas</h2></div><span className="neutral-tag">Plano de execução</span></div>
          <div className="roadmap-list">
            <div className="roadmap-item done"><span className="roadmap-check">✓</span><div><strong>Coleta e extração de pacotes oficiais</strong><small>Download validado, checksum, extração segura e catálogo XLSX</small></div><span className="roadmap-status">Concluído</span></div>
            <div className="roadmap-item done"><span className="roadmap-check">✓</span><div><strong>Modelos iniciais de domínio</strong><small>Estados de preço, regimes, encargos e classificação de composições</small></div><span className="roadmap-status">Fundação</span></div>
            <div className="roadmap-item current"><span className="roadmap-number">03</span><div><strong>Parsers oficiais e validação</strong><small>ISD, ICD, ISE, CSD, CCD, CSE, analítico, mão de obra e coeficientes</small></div><span className="roadmap-status">Próxima etapa</span></div>
            <div className="roadmap-item"><span className="roadmap-number">04</span><div><strong>Persistência e API de consulta</strong><small>PostgreSQL, histórico e filtros por UF e competência</small></div><span className="roadmap-status">Planejado</span></div>
            <div className="roadmap-item"><span className="roadmap-number">05</span><div><strong>Dashboard analítico</strong><small>Comparativos, indicadores, consulta de composições e exportação</small></div><span className="roadmap-status">Planejado</span></div>
          </div>
        </section>
        <footer className="footer"><span>GET-SINAPI <i>·</i> NR Data Analysis</span><span>Dados oficiais, rastreabilidade e integridade.</span></footer>
      </main>
    </div>
  );
}

export default App;
