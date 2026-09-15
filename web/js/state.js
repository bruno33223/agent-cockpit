/**
 * Módulo de Gerenciamento de Estado (State Store)
 * Centraliza estado reativo, persistência de workspace e comunicação com a API.
 */

// Base URLs unificadas (Suporte híbrido: Navegador local ou Tauri Desktop)
export const IS_HOSTED_SERVER = (window.location.port === '8765' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'));
export const API_BASE = IS_HOSTED_SERVER ? '' : 'http://127.0.0.1:8765';
export const WS_BASE = IS_HOSTED_SERVER 
  ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`
  : 'ws://127.0.0.1:8765/ws';

// Wrapper unificado para fetch direcionando dinamicamente para o backend
export function apiFetch(endpoint, options) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  return fetch(url, options);
}

// Estado reativo central
export let state = {
  epic: {},
  nodes: [],
  pairs_3x3: [],
  steering_messages: [],
  gauntlet_log: []
};

export function setState(newState) {
  state = newState;
  notifySubscribers('state', state);
}

export let activeSliceId = null;

export function setActiveSliceId(sliceId) {
  activeSliceId = sliceId;
  notifySubscribers('slice', activeSliceId);
}

export let currentProjectId = localStorage.getItem('cockpit_project_id') || 'default';

export function setCurrentProjectId(pid) {
  currentProjectId = pid;
  localStorage.setItem('cockpit_project_id', currentProjectId);
  notifySubscribers('project', currentProjectId);
}

export let knownProjects = [];

export function setKnownProjects(projects) {
  knownProjects = projects || [];
  notifySubscribers('projects', knownProjects);
}

// Simple Pub/Sub para desacoplar módulos
const subscribers = {
  state: new Set(),
  project: new Set(),
  projects: new Set(),
  slice: new Set()
};

export function subscribe(event, callback) {
  if (subscribers[event]) {
    subscribers[event].add(callback);
    return () => subscribers[event].delete(callback);
  }
  return () => {};
}

function notifySubscribers(event, data) {
  if (subscribers[event]) {
    subscribers[event].forEach(cb => {
      try { cb(data); } catch (e) { console.error(`[StateBus] Erro em subscriber de ${event}:`, e); }
    });
  }
}

// Gerenciamento de Projetos Fixados (Pinned)
export function getPinnedProjectIds() {
  try {
    const raw = localStorage.getItem('cockpit_pinned_projects');
    if (raw !== null) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    }
  } catch (e) {
    console.warn('[Projects] Erro ao ler cockpit_pinned_projects:', e);
  }
  return ['default'];
}

export function savePinnedProjectIds(ids) {
  try {
    localStorage.setItem('cockpit_pinned_projects', JSON.stringify(ids));
  } catch (e) {
    console.warn('[Projects] Erro ao gravar cockpit_pinned_projects:', e);
  }
}

// Gerenciamento de Projetos Recentes (Recent)
export function getRecentProjectIds() {
  try {
    const raw = localStorage.getItem('cockpit_recent_projects');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    }
  } catch (e) {}
  return [];
}

export function recordRecentProject(projectId) {
  if (!projectId) return;
  try {
    let recent = getRecentProjectIds();
    recent = [projectId, ...recent.filter(id => id !== projectId)].slice(0, 15);
    localStorage.setItem('cockpit_recent_projects', JSON.stringify(recent));
  } catch (e) {}
}

// Indicadores semânticos de estado do projeto
export function getProjectDotClass(proj) {
  if (!proj) return 'idle';
  // 1. Verde: concluído (todos os slices aprovados com sucesso)
  if (proj.total_slices > 0 && proj.approved_slices === proj.total_slices) {
    return 'done';
  }

  const isCurrent = (typeof state !== 'undefined' && state && (state.active_project_id === proj.id || currentProjectId === proj.id));

  // 2. Laranja: aguardando validação ou ação do usuário
  const isWaiting = Boolean(
    proj.waiting_user ||
    (isCurrent && (
      state.human_gate_pending ||
      (state.nodes && state.nodes.some(n => ['WAITING_REVIEW', 'WAITING_USER', 'HUMAN_GATE'].includes(n.kanban_status)))
    ))
  );
  if (isWaiting) return 'waiting';

  // 3. Azul: agentes trabalhando (em execução)
  const isWorking = Boolean(
    (proj.active_agents && proj.active_agents > 0) ||
    (isCurrent && (
      (state.nodes && state.nodes.some(n => ['EXECUTING', 'CRITIQUING', 'WORKING'].includes(n.kanban_status))) ||
      (state.pairs_3x3 && state.pairs_3x3.some(p => p.builder_status === 'WORKING' || p.critic_status === 'WORKING'))
    ))
  );
  if (isWorking) return 'working';

  // 4. Cinza: inativo (sem agentes trabalhando)
  return 'idle';
}

export function getProjectDotTitle(dotClass) {
  switch (dotClass) {
    case 'working':
      return 'Agentes trabalhando (Executando)';
    case 'waiting':
      return 'Aguardando validação ou ação do usuário';
    case 'done':
      return 'Concluído (Todas as fatias aprovadas)';
    case 'idle':
    default:
      return 'Inativo (Nenhum agente em execução)';
  }
}

// Carregamento de Projetos
export async function loadProjects() {
  const projectSelect = document.getElementById('project-select');
  try {
    const res = await apiFetch('/api/projects');
    if (res.ok) {
      const data = await res.json();
      setKnownProjects(data.projects || []);
      const serverCurrent = data.current_project_id || 'default';

      if (!knownProjects.some(p => p.id === currentProjectId)) {
        setCurrentProjectId(serverCurrent);
      }
      renderProjectSelectOptions();
      if (typeof window.renderWorktreeSidebar === 'function') {
        window.renderWorktreeSidebar();
      }
    }
  } catch (err) {
    console.warn('[Projects] Falha ao carregar lista de projetos:', err);
  }
}

export function renderProjectSelectOptions() {
  const projectSelect = document.getElementById('project-select');
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

// Troca de Projeto Concorrente (Context Isolation)
export async function switchProject(projectId) {
  if (!projectId) return;
  setCurrentProjectId(projectId);

  // Limpeza de estado residual de projeto anterior
  if (activeSliceId) {
    const hasSlice = state && state.nodes && state.nodes.some(n => n.id === activeSliceId);
    if (!hasSlice) {
      setActiveSliceId(null);
      if (typeof window.closeDrawer === 'function') window.closeDrawer();
    }
  }
  if (typeof window.fileExplorerManager !== 'undefined' && window.fileExplorerManager) {
    window.fileExplorerManager.selectedFilePath = null;
    if (typeof window.fileExplorerManager.closeFilePreview === 'function') {
      window.fileExplorerManager.closeFilePreview();
    }
  }

  // 1. Sincronização via POST /api/projects/switch
  try {
    const switchRes = await apiFetch('/api/projects/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: currentProjectId })
    });
    if (switchRes.ok) {
      const switchData = await switchRes.json();
      if (switchData.state) {
        switchData.state.active_project_id = currentProjectId;
        setState(switchData.state);
      }
      if (switchData.projects) {
        setKnownProjects(switchData.projects);
      }
    }
  } catch (err) {
    console.warn('[Projects] Falha ao sincronizar switch com backend:', err);
  }

  // 2. WebSocket Subscription
  if (window.cockpitSocket && window.cockpitSocket.readyState === WebSocket.OPEN) {
    window.cockpitSocket.send(JSON.stringify({
      action: 'SUBSCRIBE_PROJECT',
      project_id: currentProjectId,
      switch_current: true
    }));
  }

  // 3. Garante estado completo e unificação de active_project_id
  try {
    const res = await apiFetch(`/api/state?project_id=${encodeURIComponent(currentProjectId)}`);
    if (res.ok) {
      const stateData = await res.json();
      stateData.active_project_id = currentProjectId;
      setState(stateData);
    }
  } catch (err) {
    console.error('[Projects] Erro ao carregar estado do projeto:', err);
  }

  // 4. Reatividade estrita por projeto em todos os subsistemas
  if (typeof window.renderAll === 'function') window.renderAll();
  if (typeof window.loadHandoff === 'function') window.loadHandoff();
  if (typeof window.initOrRefreshGraph === 'function') window.initOrRefreshGraph();
  if (typeof window.loadLocalWorker === 'function') window.loadLocalWorker();
  if (typeof terminalWorkspace !== 'undefined' && terminalWorkspace) {
    terminalWorkspace.onProjectSwitched(currentProjectId);
  }
  if (typeof fileExplorerManager !== 'undefined' && fileExplorerManager) {
    fileExplorerManager.loadFileTree(currentProjectId);
  } else if (typeof window !== 'undefined' && window.fileExplorerManager) {
    window.fileExplorerManager.loadFileTree(currentProjectId);
  }
  renderProjectSelectOptions();
  if (typeof window.renderWorktreeSidebar === 'function') {
    window.renderWorktreeSidebar();
  }
}

// Escaneamento de novos projetos
export async function triggerScanProjects() {
  const btnScanProjects = document.getElementById('btn-scan-projects');
  if (btnScanProjects) {
    btnScanProjects.disabled = true;
    btnScanProjects.style.opacity = '0.5';
  }
  try {
    const res = await apiFetch('/api/projects/scan', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      setKnownProjects(data.projects || []);
      renderProjectSelectOptions();
      if (typeof window.renderWorktreeSidebar === 'function') {
        window.renderWorktreeSidebar();
      }
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
