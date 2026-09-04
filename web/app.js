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
  }
};

document.querySelectorAll('.nav-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const viewId = btn.getAttribute('data-view');
    switchTab(viewId);
  });
});

// 2. WEBSOCKET
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  wsStatusText.textContent = 'WS Conectando...';
  const led = wsStatusPill.querySelector('.pulse-led');
  if (led) led.className = 'pulse-led offline';

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    if (led) led.className = 'pulse-led online';
    wsStatusText.textContent = 'WS Online';
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.event === 'STATE_FULL') {
        state = data.payload;
        renderAll();
      } else if (data.event === 'STEERING_RECEIVED' || data.event === 'ORCHESTRATOR_MESSAGE') {
        renderChatMessages();
      } else if (data.event === 'PULSE_UPDATED' || data.event === 'VERDICT_LOGGED' || data.event === 'GATE_APPROVED' || data.event === 'HANDOFF_UPDATED') {
        renderAll();
        loadHandoff();
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
    if (isApproved) {
      btnHumanGate.className = 'action-btn gate-btn approved';
      btnHumanGate.textContent = 'Gate: Aprovado';
      btnHumanGate.title = `Release aprovado por ${state.human_gates.approved_by || 'usuário'}`;
    } else {
      btnHumanGate.className = 'action-btn gate-btn pending';
      btnHumanGate.textContent = 'Gate: Pendente (Aprovar)';
      btnHumanGate.title = 'Clique para aprovar e autorizar o release da entrega';
    }
  }
}

// HANDOFF LOADER
async function loadHandoff() {
  if (!handoffRenderedContent) return;
  handoffRenderedContent.textContent = 'Carregando handoff em disco...';
  try {
    const res = await fetch('/api/handoff');
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
        socket.send(JSON.stringify({ action: 'APPROVE_GATE', gate: 'gate_ship_approved' }));
      } else {
        fetch('/api/gates/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gate: 'gate_ship_approved', approved_by: 'user' })
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
    const colExecuting = (node.kanban_status === 'EXECUTING' || node.kanban_status === 'WAITING_REVIEW' || node.kanban_status === 'REJECTED') ? renderTaskCard(node) : '';
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
    default: return '';
  }
}

function renderTaskCard(node) {
  const status = node.kanban_status;
  let tagColor = 'var(--cyan-bright)';
  let tagText = 'Em Construção';
  let cardClass = 'active';

  if (status === 'WAITING_REVIEW') {
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

  return `
    <div class="kanban-task-card ${cardClass}">
      <div style="font-weight: 600; font-size: 10px; color: ${tagColor}">${tagText}</div>
      <div class="task-desc">${escapeHtml(node.latest_feedback || 'Em processamento')}</div>
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
    item.innerHTML = `
      <div class="timeline-header">
        <span class="timeline-verdict ${isApproved ? 'aprovado' : 'rejeitado'}">${log.verdict} — ${escapeHtml(log.slice_id || '')} (Tentativa ${log.attempt})</span>
        <span style="color: var(--text-muted)">${log.timestamp || ''}</span>
      </div>
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
    socket.send(JSON.stringify({ action: 'USER_STEERING', text }));
  } else {
    fetch('/api/steering', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
  }
  chatInput.value = '';
});

// Fallback Polling a cada 2s (garante atualização automática sem F5 mesmo se o WebSocket falhar)
setInterval(async () => {
  try {
    const res = await fetch('/api/state');
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
const projectPathInput = document.getElementById('project-path-input');
const btnScanProject = document.getElementById('btn-scan-project');

function initOrRefreshGraph(customRoot = null) {
  const targetRoot = customRoot || (projectPathInput ? projectPathInput.value.trim() : '') || localStorage.getItem('cockpit_target_project') || (state && state.project_root) || '';
  if (projectPathInput && targetRoot && !projectPathInput.value) {
    projectPathInput.value = targetRoot;
  }
  const url = targetRoot ? `/api/graph?root=${encodeURIComponent(targetRoot)}` : '/api/graph';
  fetch(url)
    .then(r => r.json())
    .then(data => {
      graphData = data;
      setupCanvasGraph();
    })
    .catch(err => console.error('Erro carregando /api/graph:', err));
}

if (btnScanProject) {
  btnScanProject.addEventListener('click', () => {
    const path = projectPathInput.value.trim();
    if (!path) return;
    localStorage.setItem('cockpit_target_project', path);
    fetch('/api/project_root', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    })
    .then(r => r.json())
    .then(res => {
      if (res.status === 'ok') {
        initOrRefreshGraph(path);
      } else {
        alert(res.message || 'Erro ao definir pasta.');
      }
    });
  });
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

function setupCanvasGraph() {
  if (!graphCanvas || !canvasViewport) return;

  const rect = canvasViewport.getBoundingClientRect();
  graphCanvas.width = rect.width;
  graphCanvas.height = rect.height;

  const nodes = graphData.nodes || [];
  const edges = graphData.edges || [];

  const centerX = rect.width / 2;
  const centerY = rect.height / 2;

  // 1. Identifica clusters e posiciona centros em anel
  const clusters = [...new Set(nodes.map(n => n.cluster || 'Raiz'))];
  const clusterCenters = {};
  const ringRadius = Math.min(centerX, centerY) * 0.6;
  clusters.forEach((c, idx) => {
    const angle = (idx / (clusters.length || 1)) * 2 * Math.PI;
    clusterCenters[c] = {
      x: centerX + ringRadius * Math.cos(angle),
      y: centerY + ringRadius * Math.sin(angle)
    };
  });

  // 2. Cria nós com posições iniciais próximas aos clusters
  graphNodes = nodes.map((n, idx) => {
    const center = clusterCenters[n.cluster || 'Raiz'] || { x: centerX, y: centerY };
    const jitter = 30 + (idx % 15) * 12;
    const jAngle = (idx * 1.37) * 2 * Math.PI;
    const deg = n.degree || 0;
    const r = Math.max(5, Math.min(5 + Math.sqrt(deg) * 2.5, 24));
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

  // 3. Relaxamento de Força Estilo Obsidian (Force-Directed Layout)
  const nodeCount = graphNodes.length;
  const iterations = Math.min(70, Math.max(30, Math.floor(12000 / (nodeCount || 1))));
  
  for (let iter = 0; iter < iterations; iter++) {
    // Repulsão (Coulomb)
    for (let i = 0; i < nodeCount; i++) {
      const n1 = graphNodes[i];
      for (let j = i + 1; j < nodeCount; j++) {
        const n2 = graphNodes[j];
        const dx = n2.x - n1.x;
        const dy = n2.y - n1.y;
        const distSq = dx * dx + dy * dy || 1;
        if (distSq < 22500) {
          const dist = Math.sqrt(distSq);
          const force = 1400 / (distSq + 80);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          n1.vx -= fx;
          n1.vy -= fy;
          n2.vx += fx;
          n2.vy += fy;
        }
      }
    }

    // Atração de arestas (Hooke Springs)
    for (let i = 0; i < graphLinks.length; i++) {
      const l = graphLinks[i];
      const dx = l.target.x - l.source.x;
      const dy = l.target.y - l.source.y;
      const dist = Math.hypot(dx, dy) || 1;
      const force = (dist - 45) * 0.035;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      l.source.vx += fx;
      l.source.vy += fy;
      l.target.vx -= fx;
      l.target.vy -= fy;
    }

    // Gravidade central + amortecimento
    for (let i = 0; i < nodeCount; i++) {
      const n = graphNodes[i];
      n.vx += (centerX - n.x) * 0.002;
      n.vy += (centerY - n.y) * 0.002;
      n.x += n.vx * 0.45;
      n.y += n.vy * 0.45;
      n.vx *= 0.68;
      n.vy *= 0.68;
    }
  }

  drawGraph();
}

function drawGraph() {
  if (!graphCanvas) return;
  const ctx = graphCanvas.getContext('2d');
  ctx.save();
  ctx.clearRect(0, 0, graphCanvas.width, graphCanvas.height);

  // Aplica Pan & Zoom
  ctx.translate(graphPanX, graphPanY);
  ctx.scale(graphZoom, graphZoom);

  // Desenha Arestas
  graphLinks.forEach(link => {
    const isConnected = selectedGraphNode && (link.source.id === selectedGraphNode.id || link.target.id === selectedGraphNode.id);
    const isHoverConnected = hoveredGraphNode && (link.source.id === hoveredGraphNode.id || link.target.id === hoveredGraphNode.id);
    const isHigh = isConnected || isHoverConnected;

    ctx.beginPath();
    ctx.moveTo(link.source.x, link.source.y);
    ctx.lineTo(link.target.x, link.target.y);

    if (isHigh) {
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 2.2 / graphZoom;
    } else if (selectedGraphNode || hoveredGraphNode) {
      ctx.strokeStyle = 'rgba(30, 41, 59, 0.12)';
      ctx.lineWidth = 0.5 / graphZoom;
    } else {
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.14)';
      ctx.lineWidth = 0.8 / graphZoom;
    }
    ctx.stroke();
  });

  // Desenha Nós
  graphNodes.forEach(node => {
    const isSelected = selectedGraphNode && selectedGraphNode.id === node.id;
    const isHovered = hoveredGraphNode && hoveredGraphNode.id === node.id;
    const isNeighbor = (selectedGraphNode && graphLinks.some(l => (l.source.id === selectedGraphNode.id && l.target.id === node.id) || (l.target.id === selectedGraphNode.id && l.source.id === node.id))) ||
                       (hoveredGraphNode && graphLinks.some(l => (l.source.id === hoveredGraphNode.id && l.target.id === node.id) || (l.target.id === hoveredGraphNode.id && l.source.id === node.id)));

    ctx.beginPath();
    ctx.arc(node.x, node.y, node.radius, 0, 2 * Math.PI);

    let fillColor = node.clusterColor || '#38bdf8';
    if (selectedGraphNode || hoveredGraphNode) {
      if (isSelected) fillColor = '#22c55e';
      else if (isHovered || isNeighbor) fillColor = '#f59e0b';
      else fillColor = 'rgba(30, 41, 59, 0.35)';
    }

    ctx.fillStyle = fillColor;
    ctx.fill();

    ctx.strokeStyle = (isSelected || isHovered) ? '#ffffff' : 'rgba(255,255,255,0.2)';
    ctx.lineWidth = (isSelected || isHovered) ? 2.5 / graphZoom : 1 / graphZoom;
    ctx.stroke();

    // Rótulo dinâmico baseado em zoom ou relevância
    const showLabel = isSelected || isHovered || isNeighbor || (node.degree >= 35) || (graphZoom > 1.25);
    if (showLabel) {
      ctx.fillStyle = isSelected || isNeighbor ? '#ffffff' : '#94a3b8';
      ctx.font = `${Math.max(9, Math.round(11 / graphZoom))}px 'JetBrains Mono', monospace`;
      ctx.textAlign = 'center';
      ctx.fillText(node.label, node.x, node.y + node.radius + (12 / graphZoom));
    }
  });

  ctx.restore();
}

// Mouse interaction (Pan, Zoom, Drag & Click)
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

  graphCanvas.addEventListener('mousedown', (e) => {
    const rect = graphCanvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - graphPanX) / graphZoom;
    const y = (e.clientY - rect.top - graphPanY) / graphZoom;

    const clicked = graphNodes.find(n => Math.hypot(n.x - x, n.y - y) <= n.radius + 3);
    if (clicked) {
      draggedGraphNode = clicked;
      selectGraphNode(clicked);
    } else {
      isGraphPanning = true;
      startPanX = e.clientX - graphPanX;
      startPanY = e.clientY - graphPanY;
    }
  });

  window.addEventListener('mousemove', (e) => {
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
      hoveredGraphNode = graphNodes.find(n => Math.hypot(n.x - x, n.y - y) <= n.radius + 3);
      graphCanvas.style.cursor = hoveredGraphNode ? 'pointer' : (isGraphPanning ? 'grabbing' : 'grab');
      drawGraph();
    }
  });

  window.addEventListener('mouseup', () => {
    isGraphPanning = false;
    draggedGraphNode = null;
    if (graphCanvas) graphCanvas.style.cursor = 'grab';
  });

  graphCanvas.addEventListener('dblclick', () => {
    graphZoom = 1;
    graphPanX = 0;
    graphPanY = 0;
    selectedGraphNode = null;
    drawGraph();
  });
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
  fetch(`/api/graph`)
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
}

if (btnRefreshGraph) {
  btnRefreshGraph.addEventListener('click', initOrRefreshGraph);
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
  if (confirm('Restaurar o estado do Cockpit para os valores iniciais?')) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: 'RESET_STATE' }));
    } else {
      fetch('/api/reset', { method: 'POST' });
    }
  }
});

btnTestCycle.addEventListener('click', () => {
  const node = state.nodes && state.nodes[0];
  if (!node) return;
  const nextStatus = node.kanban_status === 'BACKLOG' ? 'EXECUTING' :
                     node.kanban_status === 'EXECUTING' ? 'CRITIQUING' :
                     node.kanban_status === 'CRITIQUING' ? 'APPROVED' : 'BACKLOG';

  fetch('/api/steering', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: `Simulação de pulso: ${node.id} movido para ${nextStatus}` })
  });
});

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// Inicializa
initWebSocket();
