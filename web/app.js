// Base URLs unificadas (Suporte híbrido: Navegador local ou Tauri Desktop)
const IS_HOSTED_SERVER = (window.location.port === '8765' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'));
const API_BASE = IS_HOSTED_SERVER ? '' : 'http://127.0.0.1:8765';
const WS_BASE = IS_HOSTED_SERVER 
  ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`
  : 'ws://127.0.0.1:8765/ws';

// Wrapper unificado para fetch direcionando dinamicamente para o backend
function apiFetch(endpoint, options) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  return fetch(url, options);
}

// Inicialização da Sidebar Retrátil (Hambúrguer)
function initSidebar() {
  const sidebar = document.getElementById('app-sidebar');
  const toggleBtn = document.getElementById('btn-sidebar-toggle');
  if (!sidebar || !toggleBtn) return;

  const isCollapsed = localStorage.getItem('cockpit_sidebar_collapsed') === 'true';
  if (isCollapsed) {
    sidebar.classList.add('collapsed');
  }

  toggleBtn.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    localStorage.setItem('cockpit_sidebar_collapsed', sidebar.classList.contains('collapsed'));
  });
}

let state = {
  epic: {},
  nodes: [],
  pairs_3x3: [],
  steering_messages: [],
  gauntlet_log: []
};

let activeSliceId = null;
let socket = null;
let graphData = { nodes: [], edges: [] };
let selectedGraphNode = null;
let hoveredGraphNode = null;
let graphAnimationId = null;

// DOM Elements
const projectSelect = document.getElementById('project-select');
let currentProjectId = localStorage.getItem('cockpit_project_id') || 'default';
let knownProjects = [];

const wsStatusText = document.getElementById('ws-status-text');
const wsStatusPill = document.getElementById('ws-status');
const epicTitle = document.getElementById('epic-title');
const overviewEpicGoal = document.getElementById('overview-epic-goal');
const nodesCanvas = document.getElementById('nodes-canvas');
const pairsContainer = document.getElementById('pairs-container');
const overviewFleetRow = document.getElementById('overview-fleet-row');
const approvedSlicesCount = document.getElementById('approved-slices-count');
const globalProgressFill = document.getElementById('global-progress-fill');
const gateStatus = document.getElementById('gate-status');
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const btnReset = document.getElementById('btn-reset');
const btnTestCycle = document.getElementById('btn-test-cycle');
const btnRefreshGraph = document.getElementById('btn-refresh-graph');
const graphSearchInput = document.getElementById('graph-search');

// KPI Elements
const kpiTokens = document.getElementById('kpi-tokens');
const kpiFirstPass = document.getElementById('kpi-first-pass');
const kpiCompletedSlices = document.getElementById('kpi-completed-slices');
const kpiVerdictsCount = document.getElementById('kpi-verdicts-count');
const gauntletFullList = document.getElementById('gauntlet-full-list');

// Human Gate & Handoff
const btnHumanGate = document.getElementById('btn-human-gate');
const btnRefreshHandoff = document.getElementById('btn-refresh-handoff');
const handoffDirDisplay = document.getElementById('handoff-dir-display');
const handoffPathDisplay = document.getElementById('handoff-path-display');
const handoffStatusBadge = document.getElementById('handoff-status-badge');
const handoffRenderedContent = document.getElementById('handoff-rendered-content');

// Canvas
const graphCanvas = document.getElementById('graph-canvas');
const canvasViewport = document.getElementById('canvas-viewport');
const inspectorEmpty = document.getElementById('inspector-empty');
const inspectorContent = document.getElementById('inspector-content');

// Drawer
const drawerBackdrop = document.getElementById('drawer-backdrop');
const drawerClose = document.getElementById('drawer-close');
const drawerSliceId = document.getElementById('drawer-slice-id');
const drawerTitle = document.getElementById('drawer-title');
const drawerSpecContent = document.getElementById('drawer-spec-content');
const drawerCriteriaContent = document.getElementById('drawer-criteria-content');
const drawerGauntletContent = document.getElementById('drawer-gauntlet-content');
const drawerTabs = document.querySelectorAll('.drawer-tab');

// 1. TAB NAVIGATION
window.switchTab = function(viewId) {
  document.querySelectorAll('.nav-tab').forEach(t => {
    t.classList.toggle('active', t.getAttribute('data-view') === viewId);
  });
  document.querySelectorAll('.tab-view').forEach(v => {
    v.classList.toggle('active', v.id === viewId);
  });

  if (viewId === 'view-graph') {
    initOrRefreshGraph();
  } else if (viewId === 'view-handoff') {
    loadHandoff();
  } else if (viewId === 'view-worker') {
    loadLocalWorker();
  }
};

document.querySelectorAll('.nav-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const viewId = btn.getAttribute('data-view');
    switchTab(viewId);
  });
});

// 1.5. PROJETOS / MULTI-WORKSPACE
async function loadProjects() {
  if (!projectSelect) return;
  try {
    const res = await apiFetch('/api/projects');
    if (res.ok) {
      const data = await res.json();
      knownProjects = data.projects || [];
      const serverCurrent = data.current_project_id || 'default';

      if (!knownProjects.some(p => p.id === currentProjectId)) {
        currentProjectId = serverCurrent;
        localStorage.setItem('cockpit_project_id', currentProjectId);
      }
      renderProjectSelectOptions();
    }
  } catch (err) {
    console.warn('[Projects] Falha ao carregar lista de projetos:', err);
  }
}

function renderProjectSelectOptions() {
  if (!projectSelect) return;
  projectSelect.innerHTML = '';

  if (knownProjects.length === 0) {
    const opt = document.createElement('option');
    opt.value = 'default';
    opt.textContent = 'Projeto Padrão';
    projectSelect.appendChild(opt);
    return;
  }

  knownProjects.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    const slicesInfo = p.total_slices > 0 ? ` (${p.approved_slices}/${p.total_slices})` : '';
    opt.textContent = `${p.name}${slicesInfo}`;
    if (p.id === currentProjectId) {
      opt.selected = true;
    }
    projectSelect.appendChild(opt);
  });
}

async function switchProject(projectId) {
  if (!projectId || projectId === currentProjectId && state.nodes && state.nodes.length > 0) return;
  currentProjectId = projectId;
  localStorage.setItem('cockpit_project_id', currentProjectId);

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({
      action: 'SUBSCRIBE_PROJECT',
      project_id: currentProjectId
    }));
  }

  try {
    const res = await apiFetch(`/api/state?project_id=${encodeURIComponent(currentProjectId)}`);
    if (res.ok) {
      state = await res.json();
      renderAll();
      loadHandoff();
      fetchGraph();
      loadLocalWorker();
    }
  } catch (err) {
    console.error('[Projects] Erro ao carregar estado do projeto:', err);
  }
  renderProjectSelectOptions();
}

if (projectSelect) {
  projectSelect.addEventListener('change', (e) => {
    switchProject(e.target.value);
  });
}

const btnScanProjects = document.getElementById('btn-scan-projects');
async function triggerScanProjects() {
  if (btnScanProjects) {
    btnScanProjects.disabled = true;
    btnScanProjects.style.opacity = '0.5';
  }
  try {
    const res = await apiFetch('/api/projects/scan', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      knownProjects = data.projects || [];
      renderProjectSelectOptions();
    }
  } catch (err) {
    console.warn('[Projects] Erro ao escanear projetos:', err);
  } finally {
    if (btnScanProjects) {
      btnScanProjects.disabled = false;
      btnScanProjects.style.opacity = '1';
    }
  }
}

if (btnScanProjects) {
  btnScanProjects.addEventListener('click', triggerScanProjects);
}

// 2. WEBSOCKET
function initWebSocket() {
  wsStatusText.textContent = 'WS Conectando...';
  const led = wsStatusPill.querySelector('.pulse-led');
  if (led) led.className = 'pulse-led offline';

  try {
    socket = new WebSocket(WS_BASE);
  } catch (err) {
    console.error('[WebSocket] Erro ao instanciar:', err);
    setTimeout(initWebSocket, 3000);
    return;
  }

  socket.onopen = () => {
    if (led) led.className = 'pulse-led online';
    wsStatusText.textContent = 'WS Online';
    
    // Subscrição no canal do projeto ativo
    socket.send(JSON.stringify({
      action: 'SUBSCRIBE_PROJECT',
      project_id: currentProjectId
    }));
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.event === 'PROJECTS_UPDATED') {
        knownProjects = data.payload || [];
        renderProjectSelectOptions();
      } else if (data.event === 'STATE_FULL') {
        if (!data.project_id || data.project_id === currentProjectId) {
          state = data.payload;
          renderAll();
          loadLocalWorker();
        }
      } else if (data.event === 'LOCAL_WORKER_CONFIG_UPDATED' || data.event === 'LOCAL_WORKER_STATUS_CHANGED' || data.event === 'ollama_status' || data.type === 'ollama_status') {
        if (!data.project_id || data.project_id === currentProjectId) {
          if (data.payload && typeof data.payload === 'object') {
            const p = data.payload;
            if (p.running !== undefined) localWorkerStatus.running = !!p.running;
            if (p.pid !== undefined) localWorkerStatus.pid = p.pid || null;
            renderLocalWorkerUI();
          }
          loadLocalWorker();
        }
      } else if (data.event === 'worker_queue_updated' || data.type === 'worker_queue_updated') {
        const queuePayload = data.payload || data;
        renderWorkerQueue(queuePayload);
      } else if (data.event === 'ollama_log' || data.type === 'ollama_log' || data.event === 'OLLAMA_LOG') {
        renderOllamaLogLine(data.payload || data.line || data.message || data);
      } else if (data.event === 'model_pull_progress') {
        const payload = data.payload || {};
        const chunk = payload.progress || {};
        const model = payload.model || '';

        // Atualiza banner na página dedicada do Worker
        const workerBanner = document.getElementById('worker-pull-progress-banner');
        const workerPullTitle = document.getElementById('worker-pull-title');
        const workerPullPercent = document.getElementById('worker-pull-percent');
        const workerPullBar = document.getElementById('worker-pull-bar');
        const workerPullDetails = document.getElementById('worker-pull-details');

        let percent = 0;
        let detailsText = chunk.status || 'Processando...';

        if (chunk.completed !== undefined && chunk.total && chunk.total > 0) {
          percent = Math.round((chunk.completed * 100) / chunk.total);
          const mbCompleted = (chunk.completed / (1024 * 1024)).toFixed(1);
          const mbTotal = (chunk.total / (1024 * 1024)).toFixed(1);
          detailsText = `${mbCompleted} MB / ${mbTotal} MB • ${chunk.status || 'downloading'}`;
        }

        if (workerBanner) {
          workerBanner.style.display = 'block';
          if (workerPullTitle) workerPullTitle.textContent = `Baixando modelo: ${model}`;
          if (workerPullPercent) workerPullPercent.textContent = `${percent}%`;
          if (workerPullBar) workerPullBar.style.width = `${percent}%`;
          if (workerPullDetails) workerPullDetails.textContent = detailsText;
        }

        // Atualiza feedback no modal (se aberto)
        if (pullFeedbackMsg) {
          pullFeedbackMsg.style.display = 'block';
          pullFeedbackMsg.className = 'pull-feedback-msg info';
          pullFeedbackMsg.textContent = `Baixando ${model || 'modelo'}: ${percent}% (${detailsText})`;
        }
      } else if (data.event === 'model_pull_complete') {
        loadLocalWorkerModels();
        const payload = data.payload || {};

        const workerBanner = document.getElementById('worker-pull-progress-banner');
        const workerPullTitle = document.getElementById('worker-pull-title');
        const workerPullPercent = document.getElementById('worker-pull-percent');
        const workerPullBar = document.getElementById('worker-pull-bar');
        const workerPullDetails = document.getElementById('worker-pull-details');

        if (payload.status === 'success') {
          if (workerBanner) {
            if (workerPullTitle) workerPullTitle.textContent = `✓ Download Concluído: ${payload.model}`;
            if (workerPullPercent) workerPullPercent.textContent = `100%`;
            if (workerPullBar) workerPullBar.style.width = `100%`;
            if (workerPullDetails) workerPullDetails.textContent = `Modelo ${payload.model} instalado e pronto para uso!`;
            setTimeout(() => {
              if (workerBanner) workerBanner.style.display = 'none';
            }, 6000);
          }

          if (pullFeedbackMsg) {
            pullFeedbackMsg.textContent = `Download do modelo "${payload.model}" concluído com sucesso!`;
            pullFeedbackMsg.className = 'pull-feedback-msg success';
            pullFeedbackMsg.style.display = 'block';
          }
        } else {
          if (workerBanner) {
            if (workerPullTitle) workerPullTitle.textContent = `Falha no Download: ${payload.model}`;
            if (workerPullDetails) workerPullDetails.textContent = payload.message || 'Erro desconhecido';
          }

          if (pullFeedbackMsg) {
            pullFeedbackMsg.textContent = `Erro ao baixar modelo "${payload.model}": ${payload.message || 'Falha no download'}`;
            pullFeedbackMsg.className = 'pull-feedback-msg error';
            pullFeedbackMsg.style.display = 'block';
          } else {
            alert(`Erro no download do modelo "${payload.model}": ${payload.message || 'Falha desconhecida'}`);
          }
        }
      } else if (data.event === 'STEERING_RECEIVED' || data.event === 'ORCHESTRATOR_MESSAGE') {
        if (!data.project_id || data.project_id === currentProjectId) {
          renderChatMessages();
        }
      } else if (data.event === 'PULSE_UPDATED' || data.event === 'VERDICT_LOGGED' || data.event === 'GATE_APPROVED' || data.event === 'HANDOFF_UPDATED') {
        if (!data.project_id || data.project_id === currentProjectId) {
          renderAll();
          loadHandoff();
        }
      }
    } catch (e) {
      console.error('Erro processando mensagem WebSocket:', e);
    }
  };

  socket.onclose = () => {
    if (led) led.className = 'pulse-led offline';
    wsStatusText.textContent = 'WS Desconectado';
    setTimeout(initWebSocket, 2000);
  };

  socket.onerror = () => socket.close();
}

// 3. RENDER ALL
function renderAll() {
  renderHeaderAndKPIs();
  renderNodes();
  renderPairs();
  renderFinalGate();
  renderChatMessages();
  renderGauntletFull();
  if (activeSliceId) updateDrawerContent();
}

function renderHeaderAndKPIs() {
  const epicName = state.epic && state.epic.name ? state.epic.name : 'Nenhum Épico Sincronizado';
  const epicGoal = state.epic && state.epic.goal ? state.epic.goal : 'Conecte o Antigravity via MCP para sincronizar.';

  epicTitle.textContent = epicName;
  overviewEpicGoal.textContent = epicGoal;

  const nodes = state.nodes || [];
  const approved = nodes.filter(n => n.kanban_status === 'APPROVED').length;
  const total = nodes.length || 3;
  const logs = state.gauntlet_log || [];

  const totalAttempts = nodes.reduce((acc, n) => acc + (n.attempt || 1), 0);
  const firstPassCount = nodes.filter(n => n.kanban_status === 'APPROVED' && (n.attempt || 1) === 1).length;
  const firstPassRate = approved > 0 ? Math.round((firstPassCount / approved) * 100) : 100;

  // Estimativa de tokens economizados
  const tokensSaved = (totalAttempts * 3500) + (logs.length * 1800) + 14200;

  kpiTokens.textContent = tokensSaved.toLocaleString('pt-BR');
  kpiFirstPass.textContent = `${firstPassRate}%`;
  kpiCompletedSlices.textContent = `${approved} / ${total}`;
  kpiVerdictsCount.textContent = `${logs.length}`;

  // Human Gate Button
  if (btnHumanGate) {
    const isApproved = state.human_gates && state.human_gates.gate_ship_approved;
    const gateLabel = btnHumanGate.querySelector('.gate-text') || btnHumanGate.querySelector('.tab-label');
    
    btnHumanGate.classList.toggle('approved', !!isApproved);
    btnHumanGate.classList.toggle('pending', !isApproved);
    
    if (isApproved) {
      if (gateLabel) gateLabel.textContent = 'Gate: Aprovado';
      btnHumanGate.setAttribute('data-tooltip', `Release aprovado por ${state.human_gates.approved_by || 'usuário'}`);
      btnHumanGate.title = `Release aprovado por ${state.human_gates.approved_by || 'usuário'}`;
    } else {
      if (gateLabel) gateLabel.textContent = 'Gate: Pendente';
      btnHumanGate.setAttribute('data-tooltip', 'Portão Humano: Pendente (Clique para Aprovar)');
      btnHumanGate.title = 'Clique para aprovar e autorizar o release da entrega';
    }
  }
}

// HANDOFF LOADER
async function loadHandoff() {
  if (!handoffRenderedContent) return;
  handoffRenderedContent.textContent = 'Carregando handoff em disco...';
  try {
    const res = await apiFetch(`/api/handoff?project_id=${encodeURIComponent(currentProjectId)}`);
    const data = await res.json();
    if (data.status === 'NO_HANDOFF_FOUND') {
      if (handoffDirDisplay) handoffDirDisplay.textContent = 'Nenhum detectado';
      if (handoffPathDisplay) handoffPathDisplay.textContent = 'HANDOFF.md';
      if (handoffStatusBadge) {
        handoffStatusBadge.className = 'meta-value badge aguardando';
        handoffStatusBadge.textContent = 'Aguardando';
      }
      handoffRenderedContent.innerHTML = `<p class="empty-state">${escapeHtml(data.content)}</p>`;
      return;
    }
    if (handoffDirDisplay) handoffDirDisplay.textContent = data.blueprint_dir || 'blueprint';
    if (handoffPathDisplay) handoffPathDisplay.textContent = data.handoff_path || 'HANDOFF.md';
    const contentStr = data.content || '';
    const isPassed = !contentStr.includes('Status Testes: FALHOU');
    if (handoffStatusBadge) {
      handoffStatusBadge.className = `meta-value badge ${isPassed ? 'passou' : 'falhou'}`;
      handoffStatusBadge.textContent = isPassed ? 'PASSOU' : 'FALHOU';
    }
    handoffRenderedContent.textContent = contentStr;
  } catch (e) {
    handoffRenderedContent.textContent = `Erro ao ler handoff: ${e}`;
  }
}

if (btnRefreshHandoff) {
  btnRefreshHandoff.addEventListener('click', loadHandoff);
}

if (btnHumanGate) {
  btnHumanGate.addEventListener('click', () => {
    const isApproved = state.human_gates && state.human_gates.gate_ship_approved;
    if (!isApproved) {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: 'APPROVE_GATE', gate: 'gate_ship_approved', project_id: currentProjectId }));
      } else {
        apiFetch('/api/gates/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gate: 'gate_ship_approved', approved_by: 'user', project_id: currentProjectId })
        }).then(r => r.json()).then(() => renderAll());
      }
    }
  });
}

function renderNodes() {
  nodesCanvas.innerHTML = '';

  (state.nodes || []).forEach(node => {
    const card = document.createElement('div');
    const statusClass = getNodeStatusClass(node.kanban_status);
    card.className = `flow-node-card ${statusClass}`;

    const colBacklog = node.kanban_status === 'BACKLOG' ? renderTaskCard(node) : '';
    const colExecuting = (node.kanban_status === 'EXECUTING' || node.kanban_status === 'WAITING_REVIEW' || node.kanban_status === 'REJECTED' || node.kanban_status === 'BLOCKED_NO_CREDIT' || node.kanban_status === 'STALLED') ? renderTaskCard(node) : '';
    const colReviewing = node.kanban_status === 'CRITIQUING' ? renderTaskCard(node) : '';
    const colApproved = node.kanban_status === 'APPROVED' ? renderTaskCard(node) : '';

    card.innerHTML = `
      <div class="node-header">
        <div class="node-title-group">
          <span class="node-id-badge">${escapeHtml(node.id.toUpperCase())}</span>
          <span class="node-title">${escapeHtml(node.title)}</span>
        </div>
        <div class="node-meta">
          <span class="pair-tag">Par ${node.pair_id}</span>
          <span class="attempt-badge">Tentativa ${node.attempt}/${node.max_attempts || 5}</span>
          <button class="btn-inspect" onclick="openDrawer('${node.id}')">Inspecionar Spec</button>
        </div>
      </div>
      <div class="node-kanban-board">
        <div class="kanban-col"><div class="kanban-col-header">1. Backlog</div>${colBacklog}</div>
        <div class="kanban-col"><div class="kanban-col-header">2. Builder</div>${colExecuting}</div>
        <div class="kanban-col"><div class="kanban-col-header">3. Critic</div>${colReviewing}</div>
        <div class="kanban-col"><div class="kanban-col-header">4. Aprovado</div>${colApproved}</div>
      </div>
    `;
    nodesCanvas.appendChild(card);
  });
}

function getNodeStatusClass(status) {
  switch (status) {
    case 'EXECUTING': return 'active-working';
    case 'WAITING_REVIEW': return 'active-waiting';
    case 'CRITIQUING': return 'active-reviewing';
    case 'APPROVED': return 'active-approved';
    case 'REJECTED': return 'active-rejected';
    case 'BLOCKED_NO_CREDIT': return 'active-blocked';
    case 'STALLED': return 'active-stalled';
    default: return '';
  }
}

function renderTaskCard(node) {
  const status = node.kanban_status;
  let tagColor = 'var(--cyan-bright)';
  let tagText = 'Em Construção';
  let cardClass = 'active';

  if (status === 'BLOCKED_NO_CREDIT') {
    tagColor = '#ef4444';
    tagText = '💳 Sem Crédito / Bloqueado';
    cardClass = 'blocked';
  } else if (status === 'STALLED') {
    tagColor = '#f97316';
    tagText = '⚠️ Zumbi / Inativo';
    cardClass = 'stalled';
  } else if (status === 'WAITING_REVIEW') {
    tagColor = 'var(--amber-bright)';
    tagText = 'Entregue (Aguardando Revisor)';
    cardClass = 'waiting';
  } else if (status === 'CRITIQUING') {
    tagColor = 'var(--purple-bright)';
    tagText = 'Harsh Critic em Auditoria';
    cardClass = 'reviewing';
  } else if (status === 'REJECTED') {
    tagColor = 'var(--red-bright)';
    tagText = 'Rejeitado (Corrigindo)';
    cardClass = 'rejected';
  } else if (status === 'APPROVED') {
    tagColor = 'var(--green-bright)';
    tagText = 'Aprovado';
    cardClass = 'approved';
  }

  const tddBadge = node.tdd_stage === 'GREEN_CONFIRMED' 
    ? '<span style="font-size: 9px; padding: 1px 4px; border-radius: 3px; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); margin-left: 6px;">TDD: GREEN</span>'
    : (node.tdd_stage === 'RED_CONFIRMED'
      ? '<span style="font-size: 9px; padding: 1px 4px; border-radius: 3px; background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); margin-left: 6px;">TDD: RED</span>'
      : '');

  const metrics = node.review_metrics || { critical: 0, important: 0, minor: 0 };
  const hasFindings = (metrics.critical || 0) + (metrics.important || 0) + (metrics.minor || 0) > 0;
  const metricsBadges = hasFindings ? `
    <div style="display: flex; gap: 4px; margin-top: 4px;">
      ${metrics.critical > 0 ? `<span style="font-size: 8px; padding: 1px 3px; border-radius: 2px; background: #dc2626; color: #fff;">CRIT: ${metrics.critical}</span>` : ''}
      ${metrics.important > 0 ? `<span style="font-size: 8px; padding: 1px 3px; border-radius: 2px; background: #ea580c; color: #fff;">IMP: ${metrics.important}</span>` : ''}
      ${metrics.minor > 0 ? `<span style="font-size: 8px; padding: 1px 3px; border-radius: 2px; background: #0284c7; color: #fff;">MIN: ${metrics.minor}</span>` : ''}
    </div>
  ` : '';

  return `
    <div class="kanban-task-card ${cardClass}">
      <div style="font-weight: 600; font-size: 10px; color: ${tagColor}; display: flex; align-items: center; justify-content: space-between;">
        <span>${tagText}</span>
        ${tddBadge}
      </div>
      <div class="task-desc">${escapeHtml(node.latest_feedback || 'Em processamento')}</div>
      ${metricsBadges}
      <div style="font-size: 9px; color: var(--text-muted); margin-top: 4px; font-family: var(--font-mono)">${node.updated_at || ''}</div>
    </div>
  `;
}

function renderPairs() {
  pairsContainer.innerHTML = '';
  overviewFleetRow.innerHTML = '';

  (state.pairs_3x3 || []).forEach(pair => {
    const card = createPairCard(pair);
    pairsContainer.appendChild(card);

    const overviewCard = createPairCard(pair);
    overviewFleetRow.appendChild(overviewCard);
  });
}

function createPairCard(pair) {
  const card = document.createElement('div');
  card.className = 'pair-card';

  const bClass = getAgentStatusClass(pair.builder_status);
  const cClass = getAgentStatusClass(pair.critic_status);

  card.innerHTML = `
    <div class="pair-header">
      <span class="pair-name">${escapeHtml(pair.name)}</span>
      <span class="pair-time">${pair.last_heartbeat || ''}</span>
    </div>
    <div class="pair-agents-row">
      <div class="agent-status-box">
        <span class="agent-role">Executor</span>
        <span class="agent-state ${bClass}">${pair.builder_status || 'IDLE'}</span>
      </div>
      <div class="agent-status-box">
        <span class="agent-role">Revisor</span>
        <span class="agent-state ${cClass}">${pair.critic_status || 'IDLE'}</span>
      </div>
    </div>
  `;
  return card;
}

function getAgentStatusClass(status) {
  switch (status) {
    case 'WORKING': return 'state-working';
    case 'WAITING': return 'state-waiting';
    case 'REVIEWING': return 'state-reviewing';
    case 'APPROVED': return 'state-approved';
    case 'REJECTED': return 'state-rejected';
    default: return 'state-idle';
  }
}

function renderFinalGate() {
  const nodes = state.nodes || [];
  const approved = nodes.filter(n => n.kanban_status === 'APPROVED').length;
  const total = nodes.length || 3;
  const pct = Math.round((approved / total) * 100);

  approvedSlicesCount.textContent = `${approved} / ${total}`;
  globalProgressFill.style.width = `${pct}%`;

  if (approved === total && total > 0) {
    gateStatus.className = 'gatekeeper-badge approved';
    gateStatus.textContent = 'COESÃO GLOBAL APROVADA';
  } else {
    gateStatus.className = 'gatekeeper-badge pending';
    gateStatus.textContent = `EM ANDAMENTO (${approved}/${total})`;
  }
}

function renderChatMessages() {
  chatMessages.innerHTML = '';
  const messages = state.steering_messages || [];

  messages.forEach(msg => {
    const bubble = document.createElement('div');
    const isUser = msg.sender === 'USER';
    bubble.className = `chat-bubble ${isUser ? 'user' : 'orchestrator'}`;

    bubble.innerHTML = `
      <div class="bubble-meta">
        <span>${isUser ? '👤 Você' : '⚡ Orquestrador'}</span>
        <span>${msg.timestamp || ''}</span>
      </div>
      <div>${escapeHtml(msg.text)}</div>
    `;
    chatMessages.appendChild(bubble);
  });

  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function renderGauntletFull() {
  gauntletFullList.innerHTML = '';
  const logs = state.gauntlet_log || [];

  if (logs.length === 0) {
    gauntletFullList.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; font-family: var(--font-mono)">Nenhuma auditoria registrada no Gauntlet até o momento.</div>';
    return;
  }

  logs.forEach(log => {
    const isApproved = log.verdict === 'APROVADO';
    const item = document.createElement('div');
    item.className = `timeline-item ${isApproved ? 'aprovado' : 'rejeitado'}`;
    const m = log.review_metrics || { critical: 0, important: 0, minor: 0 };
    const hasFindings = (m.critical || 0) + (m.important || 0) + (m.minor || 0) > 0;
    const badges = hasFindings ? `
      <div style="display: flex; gap: 6px; margin: 4px 0;">
        ${m.critical > 0 ? `<span style="font-size: 10px; padding: 2px 6px; border-radius: 3px; background: #dc2626; color: #fff; font-weight: 600;">CRITICAL: ${m.critical}</span>` : ''}
        ${m.important > 0 ? `<span style="font-size: 10px; padding: 2px 6px; border-radius: 3px; background: #ea580c; color: #fff; font-weight: 600;">IMPORTANT: ${m.important}</span>` : ''}
        ${m.minor > 0 ? `<span style="font-size: 10px; padding: 2px 6px; border-radius: 3px; background: #0284c7; color: #fff; font-weight: 600;">MINOR: ${m.minor}</span>` : ''}
      </div>
    ` : '';

    item.innerHTML = `
      <div class="timeline-header">
        <span class="timeline-verdict ${isApproved ? 'aprovado' : 'rejeitado'}">${log.verdict} — ${escapeHtml(log.slice_id || '')} (Tentativa ${log.attempt})</span>
        <span style="color: var(--text-muted)">${log.timestamp || ''}</span>
      </div>
      ${badges}
      <div class="timeline-reason">${escapeHtml(log.reason || '')}</div>
    `;
    gauntletFullList.appendChild(item);
  });
}

// 4. CHAT STEERING
chatForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'USER_STEERING', text, project_id: currentProjectId }));
  } else {
    apiFetch('/api/steering', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, project_id: currentProjectId })
    });
  }
  chatInput.value = '';
});

// Fallback Polling a cada 2s (garante atualização automática sem F5 mesmo se o WebSocket falhar)
setInterval(async () => {
  try {
    const res = await apiFetch(`/api/state?project_id=${encodeURIComponent(currentProjectId)}`);
    if (res.ok) {
      const remoteState = await res.json();
      if (JSON.stringify(remoteState) !== JSON.stringify(state)) {
        state = remoteState;
        renderAll();
      }
    }
  } catch (e) {
    // Silencioso
  }
}, 2000);

// 5. INTERACTIVE CODE GRAPH (CANVAS 2D)
function getActiveProjectRoot() {
  return localStorage.getItem('cockpit_target_project') || (state && state.project_root) || '';
}

function deselectGraphNode() {
  selectedGraphNode = null;
  drawGraph();

  if (inspectorEmpty) inspectorEmpty.style.display = 'flex';
  if (inspectorContent) inspectorContent.style.display = 'none';

  const noteEditor = document.getElementById('inspector-note-editor');
  if (noteEditor) noteEditor.value = '';
  const noteStatus = document.getElementById('note-save-status');
  if (noteStatus) noteStatus.textContent = '';
}

function initOrRefreshGraph(customRoot = null) {
  const targetRoot = (typeof customRoot === 'string' && customRoot.trim()) ? customRoot.trim() : getActiveProjectRoot();
  const url = targetRoot ? `/api/graph?root=${encodeURIComponent(targetRoot)}` : '/api/graph';
  apiFetch(url)
    .then(r => r.json())
    .then(data => {
      graphData = data;
      deselectGraphNode();
      activeClusterFilter = null;
      setupCanvasGraph();
    })
    .catch(err => console.error('Erro carregando /api/graph:', err));
}

let graphNodes = [];
let graphLinks = [];
let graphZoom = 1;
let graphPanX = 0;
let graphPanY = 0;
let isGraphPanning = false;
let startPanX = 0;
let startPanY = 0;
let draggedGraphNode = null;
let activeClusterFilter = null;

const CLUSTER_PALETTE = {
  'Entities': '#10b981',   // Emerald
  'Systems': '#0ea5e9',    // Sky blue
  'Core': '#f59e0b',       // Amber
  'Tests': '#a855f7',      // Purple
  'UI': '#ec4899',         // Pink
  'Graphics': '#6366f1',   // Indigo
  'Audio': '#06b6d4',      // Cyan
  'Navigation': '#14b8a6', // Teal
  'Common': '#84cc16',     // Lime
  'Raiz': '#38bdf8'        // Light cyan
};

function renderClusterFilterPills(nodes) {
  const container = document.getElementById('cluster-pills-container');
  if (!container) return;

  const clusterCounts = {};
  nodes.forEach(n => {
    const c = n.cluster || 'Raiz';
    clusterCounts[c] = (clusterCounts[c] || 0) + 1;
  });

  const sortedClusters = Object.keys(clusterCounts).sort((a, b) => clusterCounts[b] - clusterCounts[a]);

  let html = `
    <div class="cluster-pill ${activeClusterFilter === null ? 'active' : ''}" data-cluster="ALL">
      <span class="cluster-dot" style="background: #38bdf8"></span>
      <span>Todos</span>
      <span class="cluster-count">(${nodes.length})</span>
    </div>
  `;

  sortedClusters.forEach(c => {
    const col = CLUSTER_PALETTE[c] || '#94a3b8';
    const isActive = activeClusterFilter === c;
    html += `
      <div class="cluster-pill ${isActive ? 'active' : ''}" data-cluster="${c}">
        <span class="cluster-dot" style="background: ${col}"></span>
        <span>${c}</span>
        <span class="cluster-count">(${clusterCounts[c]})</span>
      </div>
    `;
  });

  container.innerHTML = html;

  container.querySelectorAll('.cluster-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const targetCluster = pill.getAttribute('data-cluster');
      // Desseleciona qualquer nó ativo para permitir filtrar o cluster limpo
      deselectGraphNode();

      if (targetCluster === 'ALL' || activeClusterFilter === targetCluster) {
        activeClusterFilter = null;
      } else {
        activeClusterFilter = targetCluster;
      }
      renderClusterFilterPills(nodes);
      drawGraph();
    });
  });
}

function updateGraphStatsBadge() {
  const badge = document.getElementById('graph-stats-badge');
  if (badge) {
    const n = graphNodes.length;
    const e = graphLinks.length;
    badge.textContent = `${n} nós • ${e} conexões`;
  }
}

function fitGraphToViewport() {
  if (!graphCanvas || !canvasViewport || graphNodes.length === 0) return;
  const rect = canvasViewport.getBoundingClientRect();
  
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  graphNodes.forEach(n => {
    if (n.x < minX) minX = n.x;
    if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.y > maxY) maxY = n.y;
  });

  const pad = 70;
  const w = Math.max(100, maxX - minX);
  const h = Math.max(100, maxY - minY);
  const scaleX = (rect.width - pad * 2) / w;
  const scaleY = (rect.height - pad * 2) / h;
  graphZoom = Math.max(0.18, Math.min(scaleX, scaleY, 1.2));
  graphPanX = (rect.width - w * graphZoom) / 2 - minX * graphZoom;
  graphPanY = (rect.height - h * graphZoom) / 2 - minY * graphZoom;
  drawGraph();
}

function setupCanvasGraph() {
  if (!graphCanvas || !canvasViewport) return;

  const rect = canvasViewport.getBoundingClientRect();
  graphCanvas.width = rect.width;
  graphCanvas.height = rect.height;

  const nodes = graphData.nodes || [];
  const edges = graphData.edges || [];

  const centerX = rect.width / 2;
  const centerY = rect.height / 2;

  // 1. Identifica clusters e posiciona centros em anel amplo (estilo galáxia solar)
  const clusters = [...new Set(nodes.map(n => n.cluster || 'Raiz'))];
  const clusterCenters = {};
  const ringRadius = Math.max(650, Math.min(centerX, centerY) * 1.8);

  clusters.forEach((c, idx) => {
    const angle = (idx / (clusters.length || 1)) * 2 * Math.PI;
    clusterCenters[c] = {
      x: centerX + ringRadius * Math.cos(angle),
      y: centerY + ringRadius * Math.sin(angle)
    };
  });

  // 2. Cria nós com posições iniciais distribuídas em torno dos clusters
  graphNodes = nodes.map((n, idx) => {
    const center = clusterCenters[n.cluster || 'Raiz'] || { x: centerX, y: centerY };
    const jitter = 50 + (idx % 25) * 14;
    const jAngle = (idx * 2.3999) * 2 * Math.PI; // Ângulo dourado para evitar sobreposições em linha
    const deg = n.degree || 0;
    const r = Math.max(4, Math.min(4 + Math.sqrt(deg) * 1.8, 18));
    const col = CLUSTER_PALETTE[n.cluster] || '#38bdf8';

    return {
      ...n,
      x: center.x + jitter * Math.cos(jAngle),
      y: center.y + jitter * Math.sin(jAngle),
      vx: 0,
      vy: 0,
      radius: r,
      clusterColor: col
    };
  });

  graphLinks = edges.map(e => ({
    source: graphNodes.find(n => n.id === e.source),
    target: graphNodes.find(n => n.id === e.target)
  })).filter(l => l.source && l.target);

  // 3. Relaxamento de Força Estilo Obsidian (Coulomb repulsivo amplo + molas com distância de descanso)
  const nodeCount = graphNodes.length;
  const iterations = 60;
  
  for (let iter = 0; iter < iterations; iter++) {
    const temp = Math.max(0.08, 1.0 - (iter / iterations) * 0.85);

    // A. Repulsão entre nós (Coulomb com amplo raio para evitar aglomerações)
    for (let i = 0; i < nodeCount; i++) {
      const n1 = graphNodes[i];
      for (let j = i + 1; j < nodeCount; j++) {
        const n2 = graphNodes[j];
        const dx = n2.x - n1.x;
        const dy = n2.y - n1.y;
        const distSq = dx * dx + dy * dy || 1;
        if (distSq < 62500) { // Raio de influência: 250px
          const dist = Math.sqrt(distSq) || 1;
          const force = Math.min(18.0, 2600.0 / (distSq + 120));
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          n1.vx -= fx;
          n1.vy -= fy;
          n2.vx += fx;
          n2.vy += fy;
        }
      }
    }

    // B. Atração elástica de arestas (Hooke Springs com rest-length generoso)
    for (let i = 0; i < graphLinks.length; i++) {
      const l = graphLinks[i];
      const dx = l.target.x - l.source.x;
      const dy = l.target.y - l.source.y;
      const dist = Math.hypot(dx, dy) || 1;
      const restLen = 95; // Dá respiro arquitetural entre arquivos conectados
      const force = Math.max(-10.0, Math.min(10.0, (dist - restLen) * 0.007));
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      l.source.vx += fx;
      l.source.vy += fy;
      l.target.vx -= fx;
      l.target.vy -= fy;
    }

    // C. Coesão de cluster + gravidade suave de ancoragem
    const maxV = 9.0;
    for (let i = 0; i < nodeCount; i++) {
      const n = graphNodes[i];
      const cCenter = clusterCenters[n.cluster || 'Raiz'] || { x: centerX, y: centerY };

      // Puxa suavemente em direção ao sol do próprio cluster
      n.vx += (cCenter.x - n.x) * 0.0035;
      n.vy += (cCenter.y - n.y) * 0.0035;

      // Ancoragem muito suave em direção ao centro geral
      n.vx += (centerX - n.x) * 0.0006;
      n.vy += (centerY - n.y) * 0.0006;

      // Limita velocidade máxima
      n.vx = Math.max(-maxV, Math.min(maxV, n.vx));
      n.vy = Math.max(-maxV, Math.min(maxV, n.vy));

      n.x += n.vx * temp;
      n.y += n.vy * temp;
      n.vx *= 0.6;
      n.vy *= 0.6;
    }
  }

  // Renderiza filtros e enquadra o grafo automaticamente
  renderClusterFilterPills(graphNodes);
  updateGraphStatsBadge();
  fitGraphToViewport();
}

function drawGraph() {
  if (!graphCanvas) return;
  const ctx = graphCanvas.getContext('2d');
  ctx.save();
  ctx.clearRect(0, 0, graphCanvas.width, graphCanvas.height);

  // Aplica Pan & Zoom para coordenadas do mundo
  ctx.translate(graphPanX, graphPanY);
  ctx.scale(graphZoom, graphZoom);

  const focusNode = hoveredGraphNode || selectedGraphNode;
  const focusId = focusNode ? focusNode.id : null;
  const neighborIds = new Set();

  if (focusId) {
    graphLinks.forEach(l => {
      if (l.source.id === focusId) neighborIds.add(l.target.id);
      if (l.target.id === focusId) neighborIds.add(l.source.id);
    });
  }

  // 1. DESENHA ARESTAS (Estilo constelação limpa Obsidian)
  graphLinks.forEach(link => {
    const isHigh = focusId && (link.source.id === focusId || link.target.id === focusId);
    let strokeColor;
    let lineWidth;

    if (focusId) {
      if (isHigh) {
        strokeColor = '#f59e0b'; // Dourado brilhante para conexões ativas
        lineWidth = Math.max(1.5, 2.2 / graphZoom);
      } else {
        strokeColor = 'rgba(255, 255, 255, 0.012)'; // Fundo quase transparente
        lineWidth = 0.5 / graphZoom;
      }
    } else if (activeClusterFilter) {
      const inFilter = (link.source.cluster === activeClusterFilter && link.target.cluster === activeClusterFilter);
      if (inFilter) {
        strokeColor = 'rgba(56, 189, 248, 0.16)';
        lineWidth = Math.max(0.7, 1.0 / graphZoom);
      } else {
        strokeColor = 'rgba(255, 255, 255, 0.008)';
        lineWidth = 0.4 / graphZoom;
      }
    } else {
      // Visão geral sem seleção: teia de constelação ultra sutil (evita tempestade azul)
      strokeColor = 'rgba(56, 189, 248, 0.038)';
      lineWidth = Math.max(0.4, 0.6 / graphZoom);
    }

    ctx.beginPath();
    ctx.moveTo(link.source.x, link.source.y);
    ctx.lineTo(link.target.x, link.target.y);
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  });

  // 2. DESENHA NÓS
  const nodesToLabel = [];

  graphNodes.forEach(node => {
    const isSelected = selectedGraphNode && selectedGraphNode.id === node.id;
    const isHovered = hoveredGraphNode && hoveredGraphNode.id === node.id;
    const isNeighbor = neighborIds.has(node.id);
    const matchesFilter = !activeClusterFilter || node.cluster === activeClusterFilter;

    // Anel externo/halo de destaque para nó com foco
    if (isSelected || isHovered) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius + (4 / graphZoom), 0, 2 * Math.PI);
      ctx.strokeStyle = isSelected ? '#22c55e' : '#f59e0b';
      ctx.lineWidth = Math.max(1.5, 2.0 / graphZoom);
      ctx.stroke();
    }

    // Corpo do nó
    ctx.beginPath();
    ctx.arc(node.x, node.y, node.radius, 0, 2 * Math.PI);

    let fillColor = node.clusterColor || '#38bdf8';
    if (focusId) {
      if (isSelected) fillColor = '#22c55e';
      else if (isHovered || isNeighbor) fillColor = '#f59e0b';
      else fillColor = 'rgba(30, 41, 59, 0.2)';
    } else if (activeClusterFilter) {
      if (!matchesFilter) fillColor = 'rgba(30, 41, 59, 0.2)';
    }

    ctx.fillStyle = fillColor;
    ctx.fill();

    // Borda do nó
    ctx.strokeStyle = (isSelected || isHovered) ? '#ffffff' : (isNeighbor ? 'rgba(245, 158, 11, 0.7)' : 'rgba(255, 255, 255, 0.18)');
    ctx.lineWidth = (isSelected || isHovered || isNeighbor) ? Math.max(1.2, 1.8 / graphZoom) : Math.max(0.5, 0.8 / graphZoom);
    ctx.stroke();

    // Regras estritas de Level-of-Detail (LoD) para Rótulos de Texto
    const isFocused = isSelected || isHovered || isNeighbor;
    const isMajorHub = (node.degree >= 40 && graphZoom >= 1.25);
    const isMediumHub = (node.degree >= 18 && graphZoom >= 1.85);
    const isAllVisible = graphZoom >= 2.4;

    if (matchesFilter && (isFocused || isMajorHub || isMediumHub || isAllVisible)) {
      nodesToLabel.push({
        node,
        isSelected,
        isHovered,
        isNeighbor,
        isMajorHub
      });
    }
  });

  ctx.restore(); // Restaura coordenadas para espaço de tela 1:1

  // 3. DESENHA RÓTULOS EM ESPAÇO DE TELA (Pixel-perfect, sem borrões, com badges de fundo)
  ctx.font = "10px 'JetBrains Mono', monospace";
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  nodesToLabel.forEach(item => {
    const node = item.node;
    const screenX = node.x * graphZoom + graphPanX;
    const screenY = (node.y + node.radius) * graphZoom + graphPanY + 11;

    // Ignora nós fora dos limites da tela
    if (screenX < -80 || screenX > graphCanvas.width + 80 || screenY < -20 || screenY > graphCanvas.height + 20) {
      return;
    }

    const text = node.label;
    const metrics = ctx.measureText(text);
    const padX = 5;
    const padY = 3;
    const w = metrics.width + padX * 2;
    const h = 15;
    const rx = screenX - w / 2;
    const ry = screenY - h / 2;

    // Desenha pílula escura de contraste
    ctx.save();
    ctx.beginPath();
    const r = 3;
    ctx.moveTo(rx + r, ry);
    ctx.lineTo(rx + w - r, ry);
    ctx.quadraticCurveTo(rx + w, ry, rx + w, ry + r);
    ctx.lineTo(rx + w, ry + h - r);
    ctx.quadraticCurveTo(rx + w, ry + h, rx + w - r, ry + h);
    ctx.lineTo(rx + r, ry + h);
    ctx.quadraticCurveTo(rx, ry + h, rx, ry + h - r);
    ctx.lineTo(rx, ry + r);
    ctx.quadraticCurveTo(rx, ry, rx + r, ry);
    ctx.closePath();

    ctx.fillStyle = 'rgba(10, 15, 29, 0.92)';
    ctx.fill();

    let strokeCol = 'rgba(56, 189, 248, 0.25)';
    let textCol = '#94a3b8';

    if (item.isSelected) {
      strokeCol = '#22c55e';
      textCol = '#ffffff';
    } else if (item.isHovered) {
      strokeCol = '#f59e0b';
      textCol = '#fbbf24';
    } else if (item.isNeighbor) {
      strokeCol = 'rgba(245, 158, 11, 0.6)';
      textCol = '#f1f5f9';
    } else if (item.isMajorHub) {
      strokeCol = 'rgba(56, 189, 248, 0.4)';
      textCol = '#cbd5e1';
    }

    ctx.strokeStyle = strokeCol;
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = textCol;
    ctx.fillText(text, screenX, screenY);
    ctx.restore();
  });
}

// Interação com Mouse (Pan, Zoom, Drag & Click)
if (graphCanvas) {
  graphCanvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    const rect = graphCanvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    graphPanX = mouseX - (mouseX - graphPanX) * zoomFactor;
    graphPanY = mouseY - (mouseY - graphPanY) * zoomFactor;
    graphZoom = Math.max(0.15, Math.min(graphZoom * zoomFactor, 6.0));
    drawGraph();
  }, { passive: false });

  let mouseDownScreenX = 0;
  let mouseDownScreenY = 0;
  let hasDraggedMouse = false;

  graphCanvas.addEventListener('mousedown', (e) => {
    const rect = graphCanvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - graphPanX) / graphZoom;
    const y = (e.clientY - rect.top - graphPanY) / graphZoom;

    mouseDownScreenX = e.clientX;
    mouseDownScreenY = e.clientY;
    hasDraggedMouse = false;

    const clicked = graphNodes.find(n => Math.hypot(n.x - x, n.y - y) <= n.radius + 5);
    if (clicked) {
      draggedGraphNode = clicked;
      // Toggle de foco: se clicar no mesmo nó que já estava selecionado, DESFOCA / DESSELECIONA!
      if (selectedGraphNode && selectedGraphNode.id === clicked.id) {
        deselectGraphNode();
      } else {
        selectGraphNode(clicked);
      }
    } else {
      isGraphPanning = true;
      startPanX = e.clientX - graphPanX;
      startPanY = e.clientY - graphPanY;
    }
  });

  window.addEventListener('mousemove', (e) => {
    if (Math.hypot(e.clientX - mouseDownScreenX, e.clientY - mouseDownScreenY) > 4) {
      hasDraggedMouse = true;
    }

    if (isGraphPanning) {
      graphPanX = e.clientX - startPanX;
      graphPanY = e.clientY - startPanY;
      drawGraph();
      return;
    }
    if (draggedGraphNode && graphCanvas) {
      const rect = graphCanvas.getBoundingClientRect();
      draggedGraphNode.x = (e.clientX - rect.left - graphPanX) / graphZoom;
      draggedGraphNode.y = (e.clientY - rect.top - graphPanY) / graphZoom;
      drawGraph();
      return;
    }
    if (graphCanvas && graphCanvas.offsetParent !== null) {
      const rect = graphCanvas.getBoundingClientRect();
      const x = (e.clientX - rect.left - graphPanX) / graphZoom;
      const y = (e.clientY - rect.top - graphPanY) / graphZoom;
      const prevHover = hoveredGraphNode;
      hoveredGraphNode = graphNodes.find(n => Math.hypot(n.x - x, n.y - y) <= n.radius + 5);

      if (hoveredGraphNode !== prevHover) {
        graphCanvas.style.cursor = hoveredGraphNode ? 'pointer' : 'grab';
        drawGraph();
      }
    }
  });

  window.addEventListener('mouseup', () => {
    // Se clicou no fundo vazio do canvas e NÃO arrastou: DESFOCA / DESSELECIONA!
    if (isGraphPanning && !hasDraggedMouse) {
      deselectGraphNode();
    }
    isGraphPanning = false;
    draggedGraphNode = null;
    if (graphCanvas) graphCanvas.style.cursor = 'grab';
  });

  graphCanvas.addEventListener('dblclick', () => {
    fitGraphToViewport();
  });

  window.addEventListener('resize', () => {
    if (graphCanvas && canvasViewport && document.getElementById('view-graph')?.classList.contains('active')) {
      const rect = canvasViewport.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        graphCanvas.width = rect.width;
        graphCanvas.height = rect.height;
        drawGraph();
      }
    }
  });
}

// Botões Flutuantes de Controle do Canvas
const btnZoomIn = document.getElementById('btn-zoom-in');
const btnZoomOut = document.getElementById('btn-zoom-out');
const btnZoomFit = document.getElementById('btn-zoom-fit');

if (btnZoomIn) {
  btnZoomIn.addEventListener('click', () => {
    const rect = graphCanvas.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const factor = 1.3;
    graphPanX = cx - (cx - graphPanX) * factor;
    graphPanY = cy - (cy - graphPanY) * factor;
    graphZoom = Math.min(graphZoom * factor, 6.0);
    drawGraph();
  });
}

if (btnZoomOut) {
  btnZoomOut.addEventListener('click', () => {
    const rect = graphCanvas.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const factor = 0.77;
    graphPanX = cx - (cx - graphPanX) * factor;
    graphPanY = cy - (cy - graphPanY) * factor;
    graphZoom = Math.max(graphZoom * factor, 0.15);
    drawGraph();
  });
}

if (btnZoomFit) {
  btnZoomFit.addEventListener('click', () => fitGraphToViewport());
}

function selectGraphNode(node) {
  selectedGraphNode = node;
  drawGraph();

  inspectorEmpty.style.display = 'none';
  inspectorContent.style.display = 'block';

  document.getElementById('inspector-type').textContent = (node.type || 'FILE').toUpperCase();
  document.getElementById('inspector-filename').textContent = node.label;
  document.getElementById('inspector-path').textContent = node.id;
  document.getElementById('inspector-lines').textContent = node.lines;

  // Consulta raio de impacto
  apiFetch(`/api/graph`)
    .then(() => {
      const dependents = graphLinks.filter(l => l.target.id === node.id).map(l => l.source.id);
      const riskBadge = document.getElementById('inspector-risk');
      const risk = dependents.length <= 1 ? 'LOW' : (dependents.length <= 3 ? 'MEDIUM' : 'HIGH');

      riskBadge.textContent = risk;
      riskBadge.className = `risk-badge ${risk.toLowerCase()}`;

      // Símbolos
      const symbolsList = document.getElementById('inspector-symbols');
      symbolsList.innerHTML = '';
      if (node.symbols && node.symbols.length) {
        node.symbols.forEach(s => {
          const li = document.createElement('li');
          li.textContent = s;
          symbolsList.appendChild(li);
        });
      } else {
        symbolsList.innerHTML = '<li style="color: var(--text-muted)">Nenhum símbolo exportado</li>';
      }

      // Dependentes
      const depList = document.getElementById('inspector-dependents');
      depList.innerHTML = '';
      if (dependents.length) {
        dependents.forEach(d => {
          const li = document.createElement('li');
          li.textContent = d;
          depList.appendChild(li);
        });
      } else {
        depList.innerHTML = '<li style="color: var(--text-muted)">Nenhum arquivo dependente direto</li>';
      }
    });

  // Carrega nota Obsidian do vault (cockpit-agent/vault)
  const noteEditor = document.getElementById('inspector-note-editor');
  const noteStatus = document.getElementById('note-save-status');
  if (noteEditor) {
    noteEditor.value = 'Carregando anotação de cockpit-agent/vault...';
    if (noteStatus) noteStatus.textContent = '';

    const targetRoot = getActiveProjectRoot();
    const noteUrl = targetRoot ? `/api/vault/note?file=${encodeURIComponent(node.id)}&root=${encodeURIComponent(targetRoot)}` : `/api/vault/note?file=${encodeURIComponent(node.id)}`;

    apiFetch(noteUrl)
      .then(r => r.json())
      .then(data => {
        if (data.found) {
          noteEditor.value = data.notes || '';
          noteEditor.placeholder = 'Digite anotações arquiteturais que serão salvas no .md...';
        } else {
          noteEditor.value = '';
          noteEditor.placeholder = 'Nenhuma anotação anterior. Digite aqui e clique em Salvar Nota.';
        }
      })
      .catch(() => {
        noteEditor.value = '';
        noteEditor.placeholder = 'Erro ao carregar nota do vault.';
      });
  }
}

// Botão Salvar Nota do Vault
const btnSaveNote = document.getElementById('btn-save-note');
if (btnSaveNote) {
  btnSaveNote.addEventListener('click', () => {
    if (!selectedGraphNode) return;
    const noteEditor = document.getElementById('inspector-note-editor');
    const noteStatus = document.getElementById('note-save-status');
    if (!noteEditor) return;

    const content = noteEditor.value.trim();
    const targetRoot = getActiveProjectRoot();

    btnSaveNote.disabled = true;
    btnSaveNote.textContent = 'Salvando...';

    apiFetch('/api/vault/note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file: selectedGraphNode.id,
        content: content,
        root: targetRoot
      })
    })
    .then(r => r.json())
    .then(res => {
      btnSaveNote.disabled = false;
      btnSaveNote.textContent = 'Salvar Nota';
      if (res.status === 'ok') {
        if (noteStatus) {
          noteStatus.textContent = '✓ Salvo em cockpit-agent/vault!';
          setTimeout(() => { if (noteStatus) noteStatus.textContent = ''; }, 3500);
        }
      } else {
        alert(res.message || 'Erro ao salvar nota.');
      }
    })
    .catch(err => {
      btnSaveNote.disabled = false;
      btnSaveNote.textContent = 'Salvar Nota';
      alert('Erro na requisição: ' + err);
    });
  });
}

if (btnRefreshGraph) {
  btnRefreshGraph.addEventListener('click', () => initOrRefreshGraph());
}

if (graphSearchInput) {
  graphSearchInput.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase().trim();
    if (!term) {
      selectedGraphNode = null;
      drawGraph();
      return;
    }
    const match = graphNodes.find(n => n.label.toLowerCase().includes(term) || n.id.toLowerCase().includes(term) || (n.symbols && n.symbols.some(s => s.toLowerCase().includes(term))));
    if (match) {
      selectGraphNode(match);
      if (graphCanvas) {
        const rect = graphCanvas.getBoundingClientRect();
        graphPanX = rect.width / 2 - match.x * graphZoom;
        graphPanY = rect.height / 2 - match.y * graphZoom;
        drawGraph();
      }
    }
  });
}

// 6. DRAWER
window.openDrawer = function(sliceId) {
  activeSliceId = sliceId;
  updateDrawerContent();
  drawerBackdrop.classList.add('open');
};

function updateDrawerContent() {
  const node = (state.nodes || []).find(n => n.id === activeSliceId);
  if (!node) return;

  drawerSliceId.textContent = node.id.toUpperCase();
  drawerTitle.textContent = node.title;
  drawerSpecContent.textContent = node.spec_md || 'Nenhuma especificação gravada.';
  drawerCriteriaContent.textContent = node.acceptance_criteria || 'Nenhum critério registrado.';

  drawerGauntletContent.innerHTML = '';
  const nodeLogs = (state.gauntlet_log || []).filter(l => l.slice_id === node.id);

  if (nodeLogs.length === 0) {
    drawerGauntletContent.innerHTML = '<div style="color: var(--text-muted); font-size: 11px; font-family: var(--font-mono)">Nenhuma tentativa registrada no Gauntlet Log para esta fatia.</div>';
  } else {
    nodeLogs.forEach(log => {
      const isApproved = log.verdict === 'APROVADO';
      const item = document.createElement('div');
      item.className = `timeline-item ${isApproved ? 'aprovado' : 'rejeitado'}`;
      item.innerHTML = `
        <div class="timeline-header">
          <span class="timeline-verdict ${isApproved ? 'aprovado' : 'rejeitado'}">${log.verdict} (Tentativa ${log.attempt})</span>
          <span style="color: var(--text-muted)">${log.timestamp || ''}</span>
        </div>
        <div class="timeline-reason">${escapeHtml(log.reason || '')}</div>
      `;
      drawerGauntletContent.appendChild(item);
    });
  }
}

drawerClose.addEventListener('click', () => drawerBackdrop.classList.remove('open'));
drawerBackdrop.addEventListener('click', (e) => {
  if (e.target === drawerBackdrop) drawerBackdrop.classList.remove('open');
});

drawerTabs.forEach(tab => {
  tab.addEventListener('click', () => {
    drawerTabs.forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.drawer-tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(tab.getAttribute('data-tab')).classList.add('active');
  });
});

// TOPBAR ACTIONS
btnReset.addEventListener('click', () => {
  if (confirm(`Restaurar o estado do projeto ativo (${currentProjectId}) para os valores iniciais?`)) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: 'RESET_STATE', project_id: currentProjectId }));
    } else {
      apiFetch('/api/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: currentProjectId })
      });
    }
  }
});

btnTestCycle.addEventListener('click', () => {
  const node = state.nodes && state.nodes[0];
  if (!node) return;
  const nextStatus = node.kanban_status === 'BACKLOG' ? 'EXECUTING' :
                     node.kanban_status === 'EXECUTING' ? 'CRITIQUING' :
                     node.kanban_status === 'CRITIQUING' ? 'APPROVED' : 'BACKLOG';

  apiFetch('/api/steering', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: `Simulação de pulso: ${node.id} movido para ${nextStatus}`, project_id: currentProjectId })
  });
});

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// AUTOSTART LOGIC
const btnAutostart = document.getElementById('btn-autostart');
let autostartEnabled = false;

async function checkAutostartStatus() {
  if (!btnAutostart) return;
  try {
    const res = await apiFetch('/api/autostart');
    if (res.ok) {
      const data = await res.json();
      updateAutostartUI(data.enabled);
    }
  } catch (err) {
    console.warn('[Autostart] Falha ao checar status:', err);
  }
}

function updateAutostartUI(enabled) {
  autostartEnabled = !!enabled;
  if (!btnAutostart) return;
  btnAutostart.classList.remove('loading');
  const label = btnAutostart.querySelector('.autostart-text');
  if (autostartEnabled) {
    btnAutostart.className = 'sidebar-action-btn autostart-btn enabled';
    if (label) label.textContent = 'Autostart: Ativo';
    btnAutostart.title = 'Agent Cockpit inicia automaticamente com o sistema operacional. Clique para desativar.';
  } else {
    btnAutostart.className = 'sidebar-action-btn autostart-btn disabled';
    if (label) label.textContent = 'Autostart: Desligado';
    btnAutostart.title = 'Inicialização com o sistema está desativada. Clique para ativar.';
  }
}

if (btnAutostart) {
  btnAutostart.addEventListener('click', async () => {
    btnAutostart.classList.add('loading');
    const newState = !autostartEnabled;
    try {
      const res = await apiFetch('/api/autostart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newState })
      });
      if (res.ok) {
        const data = await res.json();
        updateAutostartUI(data.enabled);
      } else {
        updateAutostartUI(autostartEnabled);
      }
    } catch (err) {
      console.error('[Autostart] Erro ao alternar autostart:', err);
      updateAutostartUI(autostartEnabled);
    }
  });
}

// ==========================================================================
// LOCAL WORKER (OLLAMA) INTEGRATION (Fatia 3)
// ==========================================================================
const lwPillLed = document.getElementById('lw-pill-led');
const lwTopbarSelect = document.getElementById('lw-topbar-select');
const btnTopbarPullModal = document.getElementById('btn-topbar-pull-modal');

const lwStatusBadge = document.getElementById('lw-status-badge');
const lwSidebarSelect = document.getElementById('lw-sidebar-select');
const lwEndpointDisplay = document.getElementById('lw-endpoint-display');
const btnOpenPullModal = document.getElementById('btn-open-pull-modal');

const modalModelDownload = document.getElementById('modal-model-download');
const btnCloseModelModal = document.getElementById('btn-close-model-modal');
const formCustomPull = document.getElementById('form-custom-pull');
const inputCustomModel = document.getElementById('input-custom-model');
const btnStartPull = document.getElementById('btn-start-pull');
const pullStatusBox = document.getElementById('pull-status-box');
const pullStatusMessage = document.getElementById('pull-status-message');
const pullFeedbackMsg = document.getElementById('pull-feedback-msg');

// Elementos de Controle e Terminal do Ollama (Local Worker)
const btnStartOllama = document.getElementById('btn-start-ollama');
const btnStopOllama = document.getElementById('btn-stop-ollama');
const btnOpenOllamaConsole = document.getElementById('btn-open-ollama-console');
const btnCloseOllamaConsole = document.getElementById('btn-close-ollama-console');
const modalOllamaConsole = document.getElementById('modal-ollama-console');
const ollamaTerminalLogs = document.getElementById('ollama-terminal-logs');
const btnClearOllamaLogs = document.getElementById('btn-clear-ollama-logs');
const btnToggleAutoscroll = document.getElementById('btn-toggle-autoscroll');
const terminalProcessStatus = document.getElementById('terminal-process-status');
const terminalLogCounter = document.getElementById('terminal-log-counter');
const lwProcessStatus = document.getElementById('lw-process-status');
const lwProcessPid = document.getElementById('lw-process-pid');
let isOllamaAutoScrollEnabled = true;

let localWorkerStatus = {
  online: false,
  running: false,
  pid: null,
  model: '',
  endpoint: 'http://127.0.0.1:11434',
  installed: [],
  recommended: []
};

async function loadLocalWorker() {
  try {
    const statusPromise = apiFetch(`/api/local-worker/status?project_id=${encodeURIComponent(currentProjectId)}`);
    const modelsPromise = apiFetch(`/api/local-worker/models?project_id=${encodeURIComponent(currentProjectId)}`);

    const [statusRes, modelsRes] = await Promise.all([statusPromise, modelsPromise]);

    if (statusRes.ok) {
      const statusData = await statusRes.json();
      const serverStatus = statusData.server_status || {};
      localWorkerStatus.online = !!statusData.online;
      localWorkerStatus.running = statusData.running !== undefined
        ? !!statusData.running
        : (serverStatus.running !== undefined ? !!serverStatus.running : !!statusData.online);
      localWorkerStatus.pid = statusData.pid || serverStatus.pid || null;
      localWorkerStatus.model = statusData.model || '';
      localWorkerStatus.endpoint = statusData.endpoint || 'http://127.0.0.1:11434';
    }

    if (modelsRes.ok) {
      const modelsData = await modelsRes.json();
      localWorkerStatus.installed = modelsData.installed || [];
      localWorkerStatus.recommended = modelsData.recommended || [];
      if (modelsData.current_model) {
        localWorkerStatus.model = modelsData.current_model;
      }
      if (modelsData.online !== undefined) {
        localWorkerStatus.online = !!modelsData.online;
        if (localWorkerStatus.running === undefined) {
          localWorkerStatus.running = !!modelsData.online;
        }
      }
    }

    renderLocalWorkerUI();
    loadWorkerQueue();
  } catch (err) {
    console.warn('[LocalWorker] Falha ao carregar status/modelos:', err);
    localWorkerStatus.online = false;
    localWorkerStatus.running = false;
    renderLocalWorkerUI();
    loadWorkerQueue();
  }
}

async function loadWorkerQueue() {
  try {
    const res = await apiFetch('/api/local-worker/queue');
    if (res.ok) {
      const data = await res.json();
      renderWorkerQueue(data);
    }
  } catch (err) {
    console.warn('[LocalWorkerQueue] Falha ao carregar status da fila:', err);
  }
}

function renderWorkerQueue(queueData) {
  if (!queueData) return;

  const isBusy = !!queueData.is_busy;
  const activeTask = queueData.active_task;
  const queueLength = queueData.queue_length || 0;
  const queuedTasks = queueData.queued_tasks || [];

  // 1. Status Indicator & Badges
  const queueStatusBadge = document.getElementById('lw-queue-status-badge');
  const queueLed = document.getElementById('lw-queue-led');
  const queueLengthBadge = document.getElementById('lw-queue-length-badge');

  if (queueStatusBadge) {
    if (isBusy) {
      queueStatusBadge.className = 'lw-badge busy';
      queueStatusBadge.textContent = 'PROCESSANDO NA GPU';
    } else {
      queueStatusBadge.className = 'lw-badge ready';
      queueStatusBadge.textContent = 'LIVRE';
    }
  }

  if (queueLed) {
    queueLed.className = isBusy ? 'pulse-led busy' : 'pulse-led online';
  }

  if (queueLengthBadge) {
    queueLengthBadge.textContent = `${queueLength} na fila`;
  }

  // 2. Active Task Container
  const activeContainer = document.getElementById('lw-active-task-container');
  if (activeContainer) {
    if (isBusy && activeTask) {
      const elapsed = activeTask.elapsed_seconds !== undefined ? `${activeTask.elapsed_seconds}s` : 'Iniciando...';
      activeContainer.innerHTML = `
        <div class="active-task-card">
          <div class="active-task-header">
            <span class="active-task-slice">${escapeHtml(activeTask.slice_id || 'Fatia')}</span>
            <span class="active-task-file"><code>${escapeHtml(activeTask.target_file || '')}</code></span>
            <span class="active-task-timer">⏱ Decorrido: <strong>${elapsed}</strong></span>
          </div>
          <div class="active-task-instruction">
            ${escapeHtml(activeTask.instruction_summary || 'Executando geração de código...')}
          </div>
        </div>
      `;
    } else {
      activeContainer.innerHTML = `
        <div class="queue-empty-placeholder">
          <span class="empty-icon">✓</span>
          <span>A GPU está ociosa e pronta para processar novas requisições.</span>
        </div>
      `;
    }
  }

  // 3. Waiting Queue List / Table
  const queueListContainer = document.getElementById('lw-queue-list-container');
  if (queueListContainer) {
    if (queuedTasks.length > 0) {
      const rowsHtml = queuedTasks.map(task => `
        <tr class="queue-row">
          <td class="col-pos"><span class="queue-pos-badge">#${task.position}</span></td>
          <td class="col-slice"><strong>${escapeHtml(task.slice_id)}</strong></td>
          <td class="col-file"><code>${escapeHtml(task.target_file)}</code></td>
          <td class="col-inst">${escapeHtml(task.instruction_summary || '-')}</td>
          <td class="col-time">${task.waiting_seconds !== undefined ? `${task.waiting_seconds}s` : '-'}</td>
        </tr>
      `).join('');

      queueListContainer.innerHTML = `
        <div class="queue-table-wrapper">
          <table class="queue-table">
            <thead>
              <tr>
                <th>Posição</th>
                <th>Fatia</th>
                <th>Arquivo Alvo</th>
                <th>Instrução</th>
                <th>Espera</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
      `;
    } else {
      queueListContainer.innerHTML = `
        <div class="queue-empty-subtext">
          Nenhuma fatia aguardando na fila.
        </div>
      `;
    }
  }
}

async function loadLocalWorkerModels() {
  await loadLocalWorker();
}

function renderLocalWorkerUI() {
  // 1. Atualiza LEDs e Badges de Conexão e Processo
  const isOnline = localWorkerStatus.online;
  const isRunning = !!(localWorkerStatus.running || localWorkerStatus.online);
  const pidText = localWorkerStatus.pid ? `PID: ${localWorkerStatus.pid}` : (isRunning ? 'PID: Ativo' : 'PID: -');

  if (lwPillLed) {
    lwPillLed.className = `pulse-led ${isOnline ? 'online' : 'offline'}`;
    lwPillLed.title = isOnline ? 'Ollama Online' : 'Ollama Offline / Inacessível';
  }

  const lwCardLed = document.getElementById('lw-card-led');
  if (lwCardLed) {
    lwCardLed.className = `pulse-led ${isOnline ? 'online' : 'offline'}`;
  }

  if (lwStatusBadge) {
    lwStatusBadge.className = `lw-badge ${isOnline ? 'online' : 'offline'}`;
    lwStatusBadge.textContent = isOnline ? 'Online' : 'Offline';
  }

  if (lwEndpointDisplay) {
    lwEndpointDisplay.textContent = localWorkerStatus.endpoint;
  }

  if (lwProcessStatus) {
    lwProcessStatus.className = `lw-proc-badge ${isRunning ? 'running' : 'stopped'}`;
    lwProcessStatus.textContent = isRunning ? 'Executando' : 'Parado';
  }

  if (terminalProcessStatus) {
    terminalProcessStatus.className = `lw-proc-badge ${isRunning ? 'running' : 'stopped'}`;
    terminalProcessStatus.textContent = isRunning ? 'Executando' : 'Parado';
  }

  if (lwProcessPid) {
    lwProcessPid.textContent = pidText;
  }

  // 2. Popula os selects (topbar e página dedicada)
  const modelsToDisplay = [...localWorkerStatus.installed];
  if (localWorkerStatus.model && !modelsToDisplay.includes(localWorkerStatus.model)) {
    modelsToDisplay.unshift(localWorkerStatus.model);
  }

  const updateSelect = (selectElem) => {
    if (!selectElem) return;
    selectElem.innerHTML = '';

    if (modelsToDisplay.length === 0) {
      const opt = document.createElement('option');
      opt.value = localWorkerStatus.model || '';
      opt.textContent = localWorkerStatus.model ? `${localWorkerStatus.model} (padrão)` : '(Nenhum modelo detectado)';
      selectElem.appendChild(opt);
    } else {
      modelsToDisplay.forEach(modelName => {
        const opt = document.createElement('option');
        opt.value = modelName;
        opt.textContent = modelName;
        if (modelName === localWorkerStatus.model) {
          opt.selected = true;
        }
        selectElem.appendChild(opt);
      });
    }

    if (localWorkerStatus.model) {
      selectElem.value = localWorkerStatus.model;
    }
  };

  updateSelect(lwTopbarSelect);
  updateSelect(lwSidebarSelect);

  // 3. Renderiza Grid de Modelos Já Instalados (Baixados)
  const installedGrid = document.getElementById('lw-installed-models-grid');
  const installedCount = document.getElementById('lw-installed-count');
  if (installedCount) {
    const count = localWorkerStatus.installed.length;
    installedCount.textContent = `${count} ${count === 1 ? 'modelo baixado' : 'modelos baixados'}`;
  }

  if (installedGrid) {
    installedGrid.innerHTML = '';
    if (!localWorkerStatus.installed || localWorkerStatus.installed.length === 0) {
      installedGrid.innerHTML = `
        <div class="empty-installed-card">
          <p>Nenhum modelo baixado no Ollama ainda.</p>
          <span style="font-size: 11px; color: var(--text-muted);">
            Selecione um dos modelos recomendados abaixo (ex: <strong>qwen2.5-coder:7b</strong>) para baixar com 1 clique e começar a programar localmente.
          </span>
        </div>
      `;
    } else {
      localWorkerStatus.installed.forEach(modelName => {
        const isActive = modelName === localWorkerStatus.model;
        const card = document.createElement('div');
        card.className = `installed-model-card ${isActive ? 'active' : ''}`;
        card.innerHTML = `
          <div class="installed-model-card-top">
            <span class="installed-model-name">${modelName}</span>
            ${isActive ? '<span class="installed-model-badge-active">EM USO NO HARNESS</span>' : ''}
          </div>
          <div class="installed-model-meta">
            <span>● GPU Vulkan Ready</span>
            <span>● Custo Zero de Tokens</span>
          </div>
          <div class="installed-model-actions">
            ${isActive 
              ? '<button class="action-btn success btn-sm" disabled style="opacity: 0.9;">✓ Modelo Ativo</button>'
              : `<button class="action-btn secondary btn-sm btn-select-model" data-model="${modelName}">Ativar no Harness</button>`
            }
          </div>
        `;
        installedGrid.appendChild(card);
      });

      installedGrid.querySelectorAll('.btn-select-model').forEach(btn => {
        btn.addEventListener('click', () => {
          const m = btn.getAttribute('data-model');
          selectLocalModel(m);
        });
      });
    }
  }

  // 4. Atualiza estado dos cards de modelos recomendados
  const recGrid = document.getElementById('lw-recommended-models-grid');
  if (recGrid) {
    recGrid.querySelectorAll('.rec-model-card').forEach(card => {
      const model = card.getAttribute('data-model');
      const btn = card.querySelector('.btn-quick-pull');
      if (model && btn) {
        if (localWorkerStatus.installed.includes(model)) {
          btn.textContent = '✓ Já Instalado';
          btn.className = 'action-btn secondary btn-sm';
          btn.title = 'Este modelo já está presente no seu disco local.';
        } else {
          btn.textContent = '⬇ Baixar Modelo';
          btn.className = 'action-btn primary btn-sm btn-quick-pull';
          btn.disabled = false;
        }
      }
    });
  }
}

async function selectLocalModel(modelName) {
  if (!modelName) return;
  try {
    const res = await apiFetch('/api/local-worker/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: modelName, project_id: currentProjectId })
    });

    if (res.ok) {
      const data = await res.json();
      localWorkerStatus.model = data.model;
      if (lwTopbarSelect) lwTopbarSelect.value = data.model;
      if (lwSidebarSelect) lwSidebarSelect.value = data.model;
      renderLocalWorkerUI();
    }
  } catch (err) {
    console.error('[LocalWorker] Erro ao selecionar modelo:', err);
  }
}

async function pullLocalModel(modelName) {
  const target = (modelName || '').trim();
  if (!target) return;

  if (pullStatusBox) pullStatusBox.style.display = 'flex';
  if (pullStatusMessage) pullStatusMessage.textContent = `Disparando download de "${target}"...`;
  if (pullFeedbackMsg) {
    pullFeedbackMsg.style.display = 'none';
    pullFeedbackMsg.className = 'pull-feedback-msg';
  }

  // Atualiza banner da página do Worker
  const workerBanner = document.getElementById('worker-pull-progress-banner');
  const workerPullTitle = document.getElementById('worker-pull-title');
  const workerPullPercent = document.getElementById('worker-pull-percent');
  const workerPullBar = document.getElementById('worker-pull-bar');
  const workerPullDetails = document.getElementById('worker-pull-details');

  if (workerBanner) {
    workerBanner.style.display = 'block';
    if (workerPullTitle) workerPullTitle.textContent = `Iniciando download: ${target}...`;
    if (workerPullPercent) workerPullPercent.textContent = `0%`;
    if (workerPullBar) workerPullBar.style.width = `2%`;
    if (workerPullDetails) workerPullDetails.textContent = 'Enviando requisição ao Ollama...';
  }

  // Desabilita botões durante o envio da solicitação
  if (btnStartPull) btnStartPull.disabled = true;
  document.querySelectorAll('.btn-quick-pull').forEach(b => b.disabled = true);

  try {
    const res = await apiFetch('/api/local-worker/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: target, project_id: currentProjectId })
    });

    const data = await res.json();
    if (res.ok && data.status !== 'error') {
      if (pullFeedbackMsg) {
        pullFeedbackMsg.textContent = data.message || `Download de '${target}' iniciado em segundo plano no Ollama. Acompanhe o progresso no Console de Logs.`;
        pullFeedbackMsg.className = 'pull-feedback-msg info';
        pullFeedbackMsg.style.display = 'block';
      }
      if (inputCustomModel) inputCustomModel.value = '';
    } else {
      if (pullFeedbackMsg) {
        pullFeedbackMsg.textContent = `Erro ao iniciar download: ${data.message || data.details?.message || data.status || 'Falha no download'}`;
        pullFeedbackMsg.className = 'pull-feedback-msg error';
        pullFeedbackMsg.style.display = 'block';
      }
    }
  } catch (err) {
    if (pullFeedbackMsg) {
      pullFeedbackMsg.textContent = `Falha de conexão com o servidor: ${err.message}`;
      pullFeedbackMsg.className = 'pull-feedback-msg error';
      pullFeedbackMsg.style.display = 'block';
    }
  } finally {
    if (pullStatusBox) pullStatusBox.style.display = 'none';
    if (btnStartPull) btnStartPull.disabled = false;
    document.querySelectorAll('.btn-quick-pull').forEach(b => b.disabled = false);
  }
}

function openModelModal() {
  if (modalModelDownload) {
    modalModelDownload.style.display = 'flex';
    if (pullFeedbackMsg) pullFeedbackMsg.style.display = 'none';
    if (pullStatusBox) pullStatusBox.style.display = 'none';
  }
}

function closeModelModal() {
  if (modalModelDownload) {
    modalModelDownload.style.display = 'none';
  }
}

async function startOllamaServer() {
  const btnStart = document.getElementById('btn-start-ollama');
  if (btnStart) {
    btnStart.disabled = true;
    btnStart.textContent = 'Iniciando...';
  }
  try {
    const res = await apiFetch('/api/local-worker/start-server', { method: 'POST' });
    const data = await res.json();
    renderOllamaLogLine(`[SISTEMA] Iniciar Ollama: ${data.status || 'OK'}`);
    await loadLocalWorker();
  } catch (err) {
    renderOllamaLogLine(`[ERRO] Falha ao iniciar Ollama: ${err.message}`);
  } finally {
    if (btnStart) {
      btnStart.disabled = false;
      btnStart.textContent = '▶ Iniciar Ollama';
    }
  }
}

async function stopOllamaServer() {
  const btnStop = document.getElementById('btn-stop-ollama');
  if (btnStop) {
    btnStop.disabled = true;
    btnStop.textContent = 'Parando...';
  }
  try {
    const res = await apiFetch('/api/local-worker/stop-server', { method: 'POST' });
    const data = await res.json();
    renderOllamaLogLine(`[SISTEMA] Parar Ollama: ${data.status || 'OK'}`);
    await loadLocalWorker();
  } catch (err) {
    renderOllamaLogLine(`[ERRO] Falha ao parar Ollama: ${err.message}`);
  } finally {
    if (btnStop) {
      btnStop.disabled = false;
      btnStop.textContent = '⏹ Parar';
    }
  }
}

let ollamaLogsPollingInterval = null;

function openOllamaConsole() {
  if (modalOllamaConsole) {
    modalOllamaConsole.style.display = 'flex';
    fetchOllamaLogs();
    if (!ollamaLogsPollingInterval) {
      ollamaLogsPollingInterval = setInterval(fetchOllamaLogs, 3000);
    }
  }
}

function closeOllamaConsole() {
  if (modalOllamaConsole) {
    modalOllamaConsole.style.display = 'none';
  }
  if (ollamaLogsPollingInterval) {
    clearInterval(ollamaLogsPollingInterval);
    ollamaLogsPollingInterval = null;
  }
}

async function fetchOllamaLogs() {
  try {
    const res = await apiFetch('/api/local-worker/server-logs?limit=80');
    if (res.ok) {
      const data = await res.json();
      const logs = data.logs || [];
      if (logs.length > 0) {
        logs.forEach(line => renderOllamaLogLine(line));
      }
    }
  } catch (err) {
    console.warn('[Ollama] Falha ao consultar histórico de logs:', err);
  }
}

function renderOllamaLogLine(line) {
  const terminal = document.getElementById('ollama-terminal-logs');
  const inpageTerminal = document.getElementById('inpage-ollama-logs');
  if (!terminal && !inpageTerminal) return;

  const removePlaceholder = (term) => {
    if (!term) return;
    const placeholder = term.querySelector('.terminal-placeholder');
    if (placeholder) placeholder.remove();
  };

  removePlaceholder(terminal);
  removePlaceholder(inpageTerminal);

  const createLineElem = () => {
    const lineElem = document.createElement('div');
    lineElem.className = 'ollama-log-line';

    let text = '';
    let timestamp = '';

    if (typeof line === 'string') {
      text = line;
    } else if (line && typeof line === 'object') {
      text = line.message || line.text || line.line || JSON.stringify(line);
      timestamp = line.timestamp || line.time || '';
    }

    if (/error|err|fail|fatal/i.test(text)) {
      lineElem.classList.add('error');
    } else if (/warn|warning/i.test(text)) {
      lineElem.classList.add('warn');
    } else if (/system|init|started|listening/i.test(text)) {
      lineElem.classList.add('system');
    }

    if (timestamp) {
      const tsSpan = document.createElement('span');
      tsSpan.className = 'log-timestamp';
      tsSpan.textContent = `[${timestamp}] `;
      lineElem.appendChild(tsSpan);
    }

    const contentSpan = document.createElement('span');
    contentSpan.className = 'log-content';
    contentSpan.textContent = text;
    lineElem.appendChild(contentSpan);

    return lineElem;
  };

  if (terminal) {
    terminal.appendChild(createLineElem());
    const counter = document.getElementById('terminal-log-counter');
    if (counter) {
      const totalLines = terminal.querySelectorAll('.ollama-log-line').length;
      counter.textContent = `${totalLines} linha${totalLines === 1 ? '' : 's'}`;
    }
    if (isOllamaAutoScrollEnabled) {
      terminal.scrollTop = terminal.scrollHeight;
    }
  }

  if (inpageTerminal) {
    inpageTerminal.appendChild(createLineElem());
    if (isOllamaAutoScrollEnabled) {
      inpageTerminal.scrollTop = inpageTerminal.scrollHeight;
    }
  }
}

function initLocalWorkerEvents() {
  if (lwTopbarSelect) {
    lwTopbarSelect.addEventListener('change', (e) => selectLocalModel(e.target.value));
  }
  if (lwSidebarSelect) {
    lwSidebarSelect.addEventListener('change', (e) => selectLocalModel(e.target.value));
  }

  if (btnTopbarPullModal) {
    btnTopbarPullModal.addEventListener('click', openModelModal);
  }
  if (btnOpenPullModal) {
    btnOpenPullModal.addEventListener('click', openModelModal);
  }
  if (btnCloseModelModal) {
    btnCloseModelModal.addEventListener('click', closeModelModal);
  }

  if (modalModelDownload) {
    modalModelDownload.addEventListener('click', (e) => {
      if (e.target === modalModelDownload) closeModelModal();
    });
  }

  // Eventos de Iniciar, Parar e Console do Ollama
  if (btnStartOllama) {
    btnStartOllama.addEventListener('click', startOllamaServer);
  }
  if (btnStopOllama) {
    btnStopOllama.addEventListener('click', stopOllamaServer);
  }
  if (btnOpenOllamaConsole) {
    btnOpenOllamaConsole.addEventListener('click', openOllamaConsole);
  }
  if (btnCloseOllamaConsole) {
    btnCloseOllamaConsole.addEventListener('click', closeOllamaConsole);
  }

  if (modalOllamaConsole) {
    modalOllamaConsole.addEventListener('click', (e) => {
      if (e.target === modalOllamaConsole) closeOllamaConsole();
    });
  }

  if (btnClearOllamaLogs) {
    btnClearOllamaLogs.addEventListener('click', () => {
      if (ollamaTerminalLogs) {
        ollamaTerminalLogs.innerHTML = '<div class="terminal-placeholder">Console limpo. Aguardando novos logs...</div>';
      }
      if (terminalLogCounter) terminalLogCounter.textContent = '0 linhas';
    });
  }

  if (btnToggleAutoscroll) {
    btnToggleAutoscroll.addEventListener('click', () => {
      isOllamaAutoScrollEnabled = !isOllamaAutoScrollEnabled;
      btnToggleAutoscroll.textContent = `Auto-Scroll: ${isOllamaAutoScrollEnabled ? 'ON' : 'OFF'}`;
      btnToggleAutoscroll.classList.toggle('active', isOllamaAutoScrollEnabled);
    });
  }

  // Controles na Página Dedicada (#view-worker)
  const btnRefreshWorker = document.getElementById('btn-refresh-worker');
  if (btnRefreshWorker) {
    btnRefreshWorker.addEventListener('click', () => {
      btnRefreshWorker.textContent = '⟳ Atualizando...';
      loadLocalWorker().then(() => {
        setTimeout(() => { btnRefreshWorker.textContent = '⟳ Atualizar Status'; }, 500);
      });
    });
  }

  const btnClearInpageLogs = document.getElementById('btn-clear-inpage-logs');
  if (btnClearInpageLogs) {
    btnClearInpageLogs.addEventListener('click', () => {
      const term = document.getElementById('inpage-ollama-logs');
      if (term) {
        term.innerHTML = '<div class="terminal-placeholder">Logs limpos. Aguardando novos registros...</div>';
      }
    });
  }

  const btnToggleInpageAutoscroll = document.getElementById('btn-toggle-inpage-autoscroll');
  if (btnToggleInpageAutoscroll) {
    btnToggleInpageAutoscroll.addEventListener('click', () => {
      isOllamaAutoScrollEnabled = !isOllamaAutoScrollEnabled;
      btnToggleInpageAutoscroll.textContent = `Auto-scroll: ${isOllamaAutoScrollEnabled ? 'ON' : 'OFF'}`;
      btnToggleInpageAutoscroll.classList.toggle('active', isOllamaAutoScrollEnabled);
      if (btnToggleAutoscroll) {
        btnToggleAutoscroll.textContent = `Auto-Scroll: ${isOllamaAutoScrollEnabled ? 'ON' : 'OFF'}`;
        btnToggleAutoscroll.classList.toggle('active', isOllamaAutoScrollEnabled);
      }
    });
  }

  const btnWorkerViewLogs = document.getElementById('btn-worker-view-logs');
  if (btnWorkerViewLogs) {
    btnWorkerViewLogs.addEventListener('click', openOllamaConsole);
  }

  // Clicar na pílula do Topbar abre a aba dedicada do Local Worker
  const topbarPill = document.getElementById('local-worker-pill');
  if (topbarPill) {
    topbarPill.addEventListener('click', (e) => {
      if (e.target.tagName.toLowerCase() !== 'select') {
        window.switchTab('view-worker');
      }
    });
  }

  if (formCustomPull) {
    formCustomPull.addEventListener('submit', (e) => {
      e.preventDefault();
      if (inputCustomModel) pullLocalModel(inputCustomModel.value);
    });
  }

  // Form custom pull na página do worker
  const btnInpagePull = document.getElementById('btn-start-pull');
  if (btnInpagePull) {
    btnInpagePull.addEventListener('click', (e) => {
      e.preventDefault();
      if (inputCustomModel) pullLocalModel(inputCustomModel.value);
    });
  }

  document.querySelectorAll('.btn-quick-pull').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const model = btn.getAttribute('data-model');
      pullLocalModel(model);
    });
  });
}

// Inicializa
initSidebar();
loadProjects();
initWebSocket();
checkAutostartStatus();
initLocalWorkerEvents();
loadLocalWorker();

