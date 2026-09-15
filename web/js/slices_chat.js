/**
 * Módulo de Fatias Verticais, Governança 3x3 e Chat (Slices & Chat)
 * Renderização do Kanban de fatias, pares da frota, vereditos do Gauntlet,
 * gate humano de aprovação e chat de direcionamento (Human Steering).
 */

import { escapeHtml } from './ui_utils.js';
import { apiFetch, state, setState, currentProjectId, activeSliceId, setActiveSliceId } from './state.js';
import { renderWorktreeSidebar } from './sidebar.js';

// Variáveis e referências defensivas aos elementos de DOM
let epicTitle = null;
let overviewEpicGoal = null;
let nodesCanvas = null;
let pairsContainer = null;
let overviewFleetRow = null;
let approvedSlicesCount = null;
let globalProgressFill = null;
let gateStatus = null;
let chatMessages = null;
let chatForm = null;
let chatInput = null;
let btnReset = null;
let btnTestCycle = null;
let kpiTokens = null;
let kpiFirstPass = null;
let kpiCompletedSlices = null;
let kpiVerdictsCount = null;
let gauntletFullList = null;
let btnHumanGate = null;
let btnRefreshHandoff = null;
let handoffDirDisplay = null;
let handoffPathDisplay = null;
let handoffStatusBadge = null;
let handoffRenderedContent = null;
let drawerBackdrop = null;
let drawerClose = null;
let drawerSliceId = null;
let drawerTitle = null;
let drawerSpecContent = null;
let drawerCriteriaContent = null;
let drawerGauntletContent = null;
let drawerTabs = null;

function resolveSlicesElements() {
  epicTitle = document.getElementById('epic-title');
  overviewEpicGoal = document.getElementById('overview-epic-goal');
  nodesCanvas = document.getElementById('nodes-canvas');
  pairsContainer = document.getElementById('pairs-container');
  overviewFleetRow = document.getElementById('overview-fleet-row');
  approvedSlicesCount = document.getElementById('approved-slices-count');
  globalProgressFill = document.getElementById('global-progress-fill');
  gateStatus = document.getElementById('gate-status');
  chatMessages = document.getElementById('chat-messages');
  chatForm = document.getElementById('chat-form');
  chatInput = document.getElementById('chat-input');
  btnReset = document.getElementById('btn-reset');
  btnTestCycle = document.getElementById('btn-test-cycle');
  kpiTokens = document.getElementById('kpi-tokens');
  kpiFirstPass = document.getElementById('kpi-first-pass');
  kpiCompletedSlices = document.getElementById('kpi-completed-slices');
  kpiVerdictsCount = document.getElementById('kpi-verdicts-count');
  gauntletFullList = document.getElementById('gauntlet-full-list');
  btnHumanGate = document.getElementById('btn-human-gate');
  btnRefreshHandoff = document.getElementById('btn-refresh-handoff');
  handoffDirDisplay = document.getElementById('handoff-dir-display');
  handoffPathDisplay = document.getElementById('handoff-path-display');
  handoffStatusBadge = document.getElementById('handoff-status-badge');
  handoffRenderedContent = document.getElementById('handoff-rendered-content');
  drawerBackdrop = document.getElementById('drawer-backdrop');
  drawerClose = document.getElementById('drawer-close');
  drawerSliceId = document.getElementById('drawer-slice-id');
  drawerTitle = document.getElementById('drawer-title');
  drawerSpecContent = document.getElementById('drawer-spec-content');
  drawerCriteriaContent = document.getElementById('drawer-criteria-content');
  drawerGauntletContent = document.getElementById('drawer-gauntlet-content');
  drawerTabs = document.querySelectorAll('.drawer-tab');
}

export function renderAll() {
  resolveSlicesElements();
  renderHeaderAndKPIs();
  renderNodes();
  renderPairs();
  renderFinalGate();
  renderChatMessages();
  renderGauntletFull();
  renderWorktreeSidebar();
  if (activeSliceId) updateDrawerContent();
  if (typeof window.fileExplorerManager !== 'undefined' && window.fileExplorerManager) {
    window.fileExplorerManager.updateProjectHeader();
  }
}

export function renderHeaderAndKPIs() {
  if (!epicTitle) resolveSlicesElements();
  const epicName = state.epic && state.epic.name ? state.epic.name : 'Nenhum Épico Sincronizado';
  const epicGoal = state.epic && state.epic.goal ? state.epic.goal : 'Conecte o Antigravity via MCP para sincronizar.';

  if (epicTitle) epicTitle.textContent = epicName;
  if (overviewEpicGoal) overviewEpicGoal.textContent = epicGoal;

  const nodes = state.nodes || [];
  const approved = nodes.filter(n => n.kanban_status === 'APPROVED').length;
  const total = nodes.length || 3;
  const logs = state.gauntlet_log || [];

  const totalAttempts = nodes.reduce((acc, n) => acc + (n.attempt || 1), 0);
  const firstPassCount = nodes.filter(n => n.kanban_status === 'APPROVED' && (n.attempt || 1) === 1).length;
  const firstPassRate = approved > 0 ? Math.round((firstPassCount / approved) * 100) : 100;

  // Estimativa de tokens economizados
  const tokensSaved = (totalAttempts * 3500) + (logs.length * 1800) + 14200;

  if (kpiTokens) kpiTokens.textContent = tokensSaved.toLocaleString('pt-BR');
  if (kpiFirstPass) kpiFirstPass.textContent = `${firstPassRate}%`;
  if (kpiCompletedSlices) kpiCompletedSlices.textContent = `${approved} / ${total}`;
  if (kpiVerdictsCount) kpiVerdictsCount.textContent = `${logs.length}`;

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
export async function loadHandoff() {
  if (!handoffRenderedContent) resolveSlicesElements();
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

export function renderNodes() {
  if (!nodesCanvas) resolveSlicesElements();
  if (!nodesCanvas) return;
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

export function getNodeStatusClass(status) {
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

export function renderTaskCard(node) {
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
    ? '<span class="tdd-badge tdd-green">TDD GREEN ✓</span>'
    : (node.tdd_stage === 'RED_CONFIRMED' 
      ? '<span class="tdd-badge tdd-red">TDD RED ✕</span>' 
      : '<span class="tdd-badge tdd-idle">TDD INIT</span>');

  return `
    <div class="kanban-task-card ${cardClass}">
      <div class="task-card-title">${escapeHtml(node.title)}</div>
      <div class="task-card-meta">
        ${tddBadge}
        <span class="status-pill-subtle" style="color: ${tagColor}; border-color: ${tagColor}">${tagText}</span>
      </div>
      <div class="task-card-desc">${escapeHtml(node.spec_md ? node.spec_md.slice(0, 80) + '...' : 'Sem descrição')}</div>
    </div>
  `;
}

export function renderPairs() {
  if (!pairsContainer) resolveSlicesElements();
  if (!pairsContainer) return;
  pairsContainer.innerHTML = '';
  if (overviewFleetRow) overviewFleetRow.innerHTML = '';

  const pairs = state.pairs_3x3 || [];
  pairs.forEach(pair => {
    // Renderiza nos cards detalhados
    const card = createPairCard(pair);
    pairsContainer.appendChild(card);

    // Renderiza na linha da visão geral
    if (overviewFleetRow) {
      const bClass = getAgentStatusClass(pair.builder_status);
      const cClass = getAgentStatusClass(pair.critic_status);
      const mini = document.createElement('div');
      mini.className = 'fleet-pair-item';
      mini.innerHTML = `
        <div class="fleet-pair-title">${escapeHtml(pair.name)}</div>
        <div class="fleet-pair-agents">
          <div class="mini-agent-dot ${bClass}" title="Executor: ${pair.builder_status}"></div>
          <div class="mini-agent-dot ${cClass}" title="Revisor: ${pair.critic_status}"></div>
        </div>
      `;
      overviewFleetRow.appendChild(mini);
    }
  });
}

export function createPairCard(pair) {
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

export function getAgentStatusClass(status) {
  switch (status) {
    case 'WORKING': return 'state-working';
    case 'WAITING': return 'state-waiting';
    case 'REVIEWING': return 'state-reviewing';
    case 'APPROVED': return 'state-approved';
    case 'REJECTED': return 'state-rejected';
    default: return 'state-idle';
  }
}

export function renderFinalGate() {
  if (!approvedSlicesCount) resolveSlicesElements();
  const nodes = state.nodes || [];
  const approved = nodes.filter(n => n.kanban_status === 'APPROVED').length;
  const total = nodes.length || 3;
  const pct = Math.round((approved / total) * 100);

  if (approvedSlicesCount) approvedSlicesCount.textContent = `${approved} / ${total}`;
  if (globalProgressFill) globalProgressFill.style.width = `${pct}%`;

  if (gateStatus) {
    if (approved === total && total > 0) {
      gateStatus.className = 'gatekeeper-badge approved';
      gateStatus.textContent = 'COESÃO GLOBAL APROVADA';
    } else {
      gateStatus.className = 'gatekeeper-badge pending';
      gateStatus.textContent = `EM ANDAMENTO (${approved}/${total})`;
    }
  }
}

export function renderChatMessages() {
  if (!chatMessages) resolveSlicesElements();
  if (!chatMessages) return;
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

export function renderGauntletFull() {
  if (!gauntletFullList) resolveSlicesElements();
  if (!gauntletFullList) return;
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

export function updateDrawerContent() {
  if (!drawerSliceId) resolveSlicesElements();
  const node = (state.nodes || []).find(n => n.id === activeSliceId);
  if (!node) return;

  if (drawerSliceId) drawerSliceId.textContent = node.id.toUpperCase();
  if (drawerTitle) drawerTitle.textContent = node.title;
  if (drawerSpecContent) drawerSpecContent.textContent = node.spec_md || 'Nenhuma especificação gravada.';
  if (drawerCriteriaContent) drawerCriteriaContent.textContent = node.acceptance_criteria || 'Nenhum critério registrado.';

  if (drawerGauntletContent) {
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
}

export function initSlicesChatEvents() {
  resolveSlicesElements();

  if (btnRefreshHandoff) {
    btnRefreshHandoff.addEventListener('click', loadHandoff);
  }

  if (btnHumanGate) {
    btnHumanGate.addEventListener('click', () => {
      const isApproved = state.human_gates && state.human_gates.gate_ship_approved;
      if (!isApproved) {
        if (window.cockpitSocket && window.cockpitSocket.readyState === WebSocket.OPEN) {
          window.cockpitSocket.send(JSON.stringify({ action: 'APPROVE_GATE', gate: 'gate_ship_approved', project_id: currentProjectId }));
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

  if (chatForm) {
    chatForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const text = chatInput ? chatInput.value.trim() : '';
      if (!text) return;

      if (window.cockpitSocket && window.cockpitSocket.readyState === WebSocket.OPEN) {
        window.cockpitSocket.send(JSON.stringify({ action: 'USER_STEERING', text, project_id: currentProjectId }));
      } else {
        apiFetch('/api/steering', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, project_id: currentProjectId })
        });
      }
      if (chatInput) chatInput.value = '';
    });
  }

  if (drawerClose && drawerBackdrop) {
    drawerClose.addEventListener('click', () => drawerBackdrop.classList.remove('open'));
    drawerBackdrop.addEventListener('click', (e) => {
      if (e.target === drawerBackdrop) drawerBackdrop.classList.remove('open');
    });
  }

  if (drawerTabs) {
    drawerTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        drawerTabs.forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.drawer-tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        const target = document.getElementById(tab.getAttribute('data-tab'));
        if (target) target.classList.add('active');
      });
    });
  }

  if (btnReset) {
    btnReset.addEventListener('click', () => {
      if (confirm(`Restaurar o estado do projeto ativo (${currentProjectId}) para os valores iniciais?`)) {
        if (window.cockpitSocket && window.cockpitSocket.readyState === WebSocket.OPEN) {
          window.cockpitSocket.send(JSON.stringify({ action: 'RESET_STATE', project_id: currentProjectId }));
        } else {
          apiFetch('/api/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: currentProjectId })
          });
        }
      }
    });
  }

  if (btnTestCycle) {
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
  }

  window.openDrawer = function(sliceId) {
    setActiveSliceId(sliceId);
    updateDrawerContent();
    if (drawerBackdrop) drawerBackdrop.classList.add('open');
  };

  window.closeDrawer = function() {
    if (drawerBackdrop) drawerBackdrop.classList.remove('open');
  };

  // Fallback Polling a cada 2s (garante atualização automática sem F5)
  setInterval(async () => {
    try {
      const res = await apiFetch(`/api/state?project_id=${encodeURIComponent(currentProjectId)}`);
      if (res.ok) {
        const remoteState = await res.json();
        remoteState.active_project_id = currentProjectId;
        if (JSON.stringify(remoteState) !== JSON.stringify(state)) {
          setState(remoteState);
          renderAll();
        }
      }
    } catch (e) {
      // Silencioso
    }
  }, 2000);
}
