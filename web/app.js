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
    const colExecuting = node.kanban_status === 'EXECUTING' || node.kanban_status === 'REJECTED' ? renderTaskCard(node) : '';
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
    case 'CRITIQUING': return 'active-reviewing';
    case 'APPROVED': return 'active-approved';
    case 'REJECTED': return 'active-rejected';
    default: return '';
  }
}

function renderTaskCard(node) {
  const isRejected = node.kanban_status === 'REJECTED';
  const tagColor = isRejected ? 'var(--red-bright)' : 'var(--cyan-bright)';
  const tagText = isRejected ? 'Rejeitado (Corrigindo)' : (node.kanban_status === 'APPROVED' ? 'Aprovado' : 'Em Andamento');

  return `
    <div class="kanban-task-card active">
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

function setupCanvasGraph() {
  if (!graphCanvas || !canvasViewport) return;

  const rect = canvasViewport.getBoundingClientRect();
  graphCanvas.width = rect.width;
  graphCanvas.height = rect.height;

  const ctx = graphCanvas.getContext('2d');
  const nodes = graphData.nodes || [];
  const edges = graphData.edges || [];

  // Layout circular/orgânico
  const centerX = rect.width / 2;
  const centerY = rect.height / 2;
  const radius = Math.min(centerX, centerY) * 0.75;

  graphNodes = nodes.map((n, idx) => {
    const angle = (idx / (nodes.length || 1)) * 2 * Math.PI;
    const r = radius * (0.6 + 0.4 * Math.sin(idx * 2));
    return {
      ...n,
      x: centerX + r * Math.cos(angle),
      y: centerY + r * Math.sin(angle),
      radius: 12 + Math.min(n.lines / 30, 16)
    };
  });

  graphLinks = edges.map(e => ({
    source: graphNodes.find(n => n.id === e.source),
    target: graphNodes.find(n => n.id === e.target)
  })).filter(l => l.source && l.target);

  drawGraph();
}

function drawGraph() {
  if (!graphCanvas) return;
  const ctx = graphCanvas.getContext('2d');
  ctx.clearRect(0, 0, graphCanvas.width, graphCanvas.height);

  // Desenha Arestas
  graphLinks.forEach(link => {
    const isConnected = selectedGraphNode && (link.source.id === selectedGraphNode.id || link.target.id === selectedGraphNode.id);
    ctx.beginPath();
    ctx.moveTo(link.source.x, link.source.y);
    ctx.lineTo(link.target.x, link.target.y);
    ctx.strokeStyle = isConnected ? '#f59e0b' : (selectedGraphNode ? 'rgba(30, 41, 59, 0.3)' : 'rgba(56, 189, 248, 0.2)');
    ctx.lineWidth = isConnected ? 2.5 : 1;
    ctx.stroke();
  });

  // Desenha Nós
  graphNodes.forEach(node => {
    const isSelected = selectedGraphNode && selectedGraphNode.id === node.id;
    const isNeighbor = selectedGraphNode && graphLinks.some(l => (l.source.id === selectedGraphNode.id && l.target.id === node.id) || (l.target.id === selectedGraphNode.id && l.source.id === node.id));
    const isHovered = hoveredGraphNode && hoveredGraphNode.id === node.id;

    ctx.beginPath();
    ctx.arc(node.x, node.y, node.radius, 0, 2 * Math.PI);

    // Cor por tipo
    let fillColor = '#38bdf8';
    if (node.type === 'cs') fillColor = '#3b82f6';
    else if (node.type === 'py') fillColor = '#eab308';
    else if (node.type === 'ts' || node.type === 'js') fillColor = '#06b6d4';

    ctx.fillStyle = isSelected ? '#22c55e' : (isNeighbor ? '#f59e0b' : fillColor);
    ctx.fill();

    ctx.strokeStyle = isSelected || isHovered ? '#ffffff' : 'rgba(255,255,255,0.2)';
    ctx.lineWidth = isSelected ? 3 : 1.5;
    ctx.stroke();

    // Rótulo
    ctx.fillStyle = isSelected || isNeighbor ? '#ffffff' : '#8da0b8';
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.textAlign = 'center';
    ctx.fillText(node.label, node.x, node.y + node.radius + 12);
  });
}

// Mouse events on canvas
if (graphCanvas) {
  graphCanvas.addEventListener('mousemove', (e) => {
    const rect = graphCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    hoveredGraphNode = graphNodes.find(n => Math.hypot(n.x - x, n.y - y) <= n.radius);
    graphCanvas.style.cursor = hoveredGraphNode ? 'pointer' : 'default';
    drawGraph();
  });

  graphCanvas.addEventListener('click', (e) => {
    const rect = graphCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const clicked = graphNodes.find(n => Math.hypot(n.x - x, n.y - y) <= n.radius);
    if (clicked) {
      selectGraphNode(clicked);
    }
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
