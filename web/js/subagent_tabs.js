/**
 * Módulo de Gerenciamento de Abas Dedicadas de Subagentes e Isolamento no Workspace
 * Agent Cockpit - Superpowers SDD Architecture
 */

import { terminalWorkspace } from './terminal_workspace.js';
import { escapeHtml } from './ui_utils.js';

// Cache de abas de subagentes ativas: id -> metadata
const activeSubagentTabs = new Map();

/**
 * Retorna o ícone e rótulo do subagente com base no papel/tipo.
 * @param {string} roleType 
 * @returns {{ icon: string, label: string }}
 */
export function getSubagentRoleMeta(roleType = 'builder') {
  const normalized = (roleType || '').toLowerCase();
  if (normalized.includes('critic')) {
    return { icon: '🧐', label: 'Critic' };
  } else if (normalized.includes('executor') || normalized.includes('exec')) {
    return { icon: '⚡', label: 'Executor' };
  } else if (normalized.includes('builder')) {
    return { icon: '🤖', label: 'Builder' };
  } else if (normalized.includes('planner') || normalized.includes('architect')) {
    return { icon: '📐', label: 'Architect' };
  }
  return { icon: '🔬', label: 'Subagent' };
}

/**
 * Formata o título descritivo padronizado para a aba do subagente.
 * Exemplo: '🤖 [Builder] slice-1'
 * @param {Object} subagentInfo 
 * @returns {string}
 */
export function formatSubagentTabTitle(subagentInfo = {}) {
  const roleType = subagentInfo.role || subagentInfo.type || subagentInfo.subagent_type || 'builder';
  const meta = getSubagentRoleMeta(roleType);
  const sliceId = subagentInfo.sliceId || subagentInfo.slice_id || (subagentInfo.taskId ? `task-${subagentInfo.taskId}` : 'slice-1');
  return `${meta.icon} [${meta.label}] ${sliceId}`;
}

/**
 * Cria ou foca uma aba dedicada para o subagente no workspace com terminal isolado.
 * @param {Object} subagentInfo 
 * @returns {Object} Representação da aba e sessão de terminal criada
 */
export function openSubagentTab(subagentInfo = {}) {
  if (!subagentInfo || typeof subagentInfo !== 'object') {
    subagentInfo = {};
  }

  const roleType = subagentInfo.role || subagentInfo.type || subagentInfo.subagent_type || 'builder';
  const sliceId = subagentInfo.sliceId || subagentInfo.slice_id || 'slice-1';
  const subagentId = subagentInfo.id || subagentInfo.subagentId || `subagent-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const title = subagentInfo.title || formatSubagentTabTitle(subagentInfo);
  const status = (subagentInfo.status || 'RUNNING').toUpperCase();
  const agentType = subagentInfo.agentType || 'opencode';
  const cwd = subagentInfo.cwd || (typeof terminalWorkspace !== 'undefined' && terminalWorkspace.getSliceCwd ? terminalWorkspace.getSliceCwd(sliceId) : null);

  // Se a aba do subagente já existir, apenas foca e retorna
  if (activeSubagentTabs.has(subagentId)) {
    const existingRecord = activeSubagentTabs.get(subagentId);
    focusSubagentTab(subagentId);
    return existingRecord;
  }

  // 1. Cria ou recupera a sessão isolada de terminal via TerminalWorkspaceManager
  let session = null;
  if (typeof terminalWorkspace !== 'undefined' && typeof terminalWorkspace.createSession === 'function') {
    if (terminalWorkspace.sessions && terminalWorkspace.sessions.has(`term-${subagentId}`)) {
      session = terminalWorkspace.sessions.get(`term-${subagentId}`);
    } else {
      session = terminalWorkspace.createSession({
        id: `term-${subagentId}`,
        name: title,
        role: 'subagent',
        sliceId: sliceId,
        agentType: agentType,
        cwd: cwd,
        contextKey: `slice:${sliceId}`
      });
    }
  }

  // 2. Renderiza ou anexa a aba no container de abas caso disponível
  const tabsContainer = document.getElementById('terminal-tabs-bar') || document.querySelector('.terminal-tabs');
  let tabEl = null;

  if (tabsContainer) {
    // Procura se já existe aba desse subagente
    tabEl = document.getElementById(`tab-subagent-${subagentId}`);
    if (!tabEl) {
      tabEl = document.createElement('div');
      tabEl.id = `tab-subagent-${subagentId}`;
      tabEl.className = 'orca-terminal-tab subagent-tab active';
      tabEl.setAttribute('data-subagent-id', subagentId);
      tabEl.setAttribute('data-slice-id', sliceId);

      const statusBadgeClass = getBadgeStatusClass(status);

      tabEl.innerHTML = `
        <div class="subagent-tab-header">
          <span class="subagent-tab-title" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
          <span class="subagent-badge ${statusBadgeClass}" id="badge-${subagentId}">${escapeHtml(status)}</span>
          <button class="subagent-tab-close" title="Fechar aba do subagente">&times;</button>
        </div>
      `;

      // Evento de fechar
      const btnClose = tabEl.querySelector('.subagent-tab-close');
      if (btnClose) {
        btnClose.addEventListener('click', (e) => {
          e.stopPropagation();
          closeSubagentTab(subagentId);
        });
      }

      // Evento de clique para focar
      tabEl.addEventListener('click', () => {
        focusSubagentTab(subagentId);
      });

      tabsContainer.appendChild(tabEl);
    }
  }

  // 3. Monta painel visual de chat OpenCode se aplicável
  let chatPanel = null;
  const workspaceGrid = document.getElementById('terminal-workspace-grid') || document.querySelector('.terminal-grid');
  if (workspaceGrid && agentType.includes('opencode')) {
    chatPanel = document.getElementById(`panel-subagent-${subagentId}`);
    if (!chatPanel) {
      chatPanel = document.createElement('div');
      chatPanel.id = `panel-subagent-${subagentId}`;
      chatPanel.className = 'opencode-chat-panel active';
      chatPanel.innerHTML = `
        <div class="opencode-chat-header">
          <div class="opencode-chat-title">
            <span>💬</span> <strong>${escapeHtml(title)}</strong>
          </div>
          <div class="opencode-chat-actions">
            <span class="subagent-badge ${getBadgeStatusClass(status)}">${escapeHtml(status)}</span>
          </div>
        </div>
        <div class="opencode-chat-body" id="chat-body-${subagentId}">
          <div class="chat-placeholder-msg">Terminal e sessão isolada inicializados para [${escapeHtml(sliceId)}].</div>
        </div>
      `;
      // Injeta de forma não-bloqueante no DOM se workspaceGrid estiver disponível
      if (workspaceGrid.appendChild) {
        workspaceGrid.appendChild(chatPanel);
      }
    }
  }

  const tabRecord = {
    id: subagentId,
    title,
    sliceId,
    roleType,
    status,
    session,
    tabEl,
    chatPanel,
    createdAt: new Date().toISOString()
  };

  activeSubagentTabs.set(subagentId, tabRecord);
  return tabRecord;
}

/**
 * Atualiza o status e badge de uma aba de subagente.
 * @param {string} subagentId 
 * @param {string} newStatus 
 */
export function updateSubagentTabStatus(subagentId, newStatus) {
  const record = activeSubagentTabs.get(subagentId);
  if (!record) return;

  record.status = (newStatus || 'IDLE').toUpperCase();
  const badgeEl = document.getElementById(`badge-${subagentId}`);
  if (badgeEl) {
    badgeEl.className = `subagent-badge ${getBadgeStatusClass(record.status)}`;
    badgeEl.textContent = record.status;
  }
}

/**
 * Foca a aba do subagente e o respectivo terminal/chat panel.
 * @param {string} subagentId 
 */
export function focusSubagentTab(subagentId) {
  const record = activeSubagentTabs.get(subagentId);
  if (!record) return;

  document.querySelectorAll('.subagent-tab').forEach(t => t.classList.remove('active'));
  if (record.tabEl) {
    record.tabEl.classList.add('active');
  }

  if (record.session && typeof terminalWorkspace !== 'undefined' && terminalWorkspace.selectSession) {
    terminalWorkspace.selectSession(record.session.id, true);
  }
}

/**
 * Encerra a aba do subagente e fecha a sessão correspondente.
 * @param {string} subagentId 
 */
export function closeSubagentTab(subagentId) {
  const record = activeSubagentTabs.get(subagentId);
  if (!record) return;

  if (record.tabEl && record.tabEl.parentNode) {
    record.tabEl.parentNode.removeChild(record.tabEl);
  }
  if (record.chatPanel && record.chatPanel.parentNode) {
    record.chatPanel.parentNode.removeChild(record.chatPanel);
  }
  if (record.session && typeof terminalWorkspace !== 'undefined' && terminalWorkspace.closeSession) {
    terminalWorkspace.closeSession(record.session.id);
  }

  activeSubagentTabs.delete(subagentId);
}

/**
 * Retorna as classes CSS de estilo da badge baseadas no status.
 * @param {string} status 
 * @returns {string}
 */
function getBadgeStatusClass(status) {
  switch ((status || '').toUpperCase()) {
    case 'RUNNING': return 'status-running';
    case 'IDLE': return 'status-idle';
    case 'DONE': return 'status-done';
    case 'FAILED':
    case 'FAIL':
    case 'ERROR': return 'status-error';
    default: return 'status-pending';
  }
}

// Exposição no escopo global para integração direta com window
if (typeof window !== 'undefined') {
  window.openSubagentTab = openSubagentTab;
  window.updateSubagentTabStatus = updateSubagentTabStatus;
  window.closeSubagentTab = closeSubagentTab;
  window.activeSubagentTabs = activeSubagentTabs;
}
