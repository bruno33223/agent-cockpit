/**
 * Agent Cockpit - Main Entrypoint & System Orchestrator (ES Module)
 * Clean Architecture & SOLID Modular Decomposition (Issue #9)
 */

// 1. Importação dos Módulos Especializados
import { escapeHtml, formatRelativeCwd, formatBytes, showToast } from './js/ui_utils.js';
import {
  state,
  setState,
  currentProjectId,
  setCurrentProjectId,
  activeSliceId,
  setActiveSliceId,
  knownProjects,
  setKnownProjects,
  apiFetch,
  loadProjects,
  switchProject,
  triggerScanProjects,
  getPinnedProjectIds,
  savePinnedProjectIds,
  getRecentProjectIds,
  recordRecentProject,
  getProjectDotClass,
  getProjectDotTitle
} from './js/state.js';
import {
  initSidebar,
  switchTab,
  renderWorktreeSidebar,
  togglePinProject,
  toggleShowMoreProjects,
  initOrcaNavigationAndModals,
  openQuickSearch,
  closeQuickSearch,
  renderQuickSearchResults
} from './js/sidebar.js';
import {
  TerminalWorkspaceManager,
  terminalWorkspace,
  initOrFitTerminal,
  sendTerminalCommand
} from './js/terminal_workspace.js';
import {
  FileExplorerManager,
  fileExplorerManager
} from './js/file_explorer.js';
import {
  renderAll,
  renderHeaderAndKPIs,
  loadHandoff,
  renderNodes,
  getNodeStatusClass,
  renderTaskCard,
  renderPairs,
  createPairCard,
  getAgentStatusClass,
  renderFinalGate,
  renderChatMessages,
  renderGauntletFull,
  updateDrawerContent,
  initSlicesChatEvents,
  activeSliceTabId,
  setActiveSliceTabId,
  getActiveSliceTabId,
  renderSliceTabs,
  switchSliceTab,
  renderDedicatedSliceView,
  renderDedicatedSliceChatMessages
} from './js/slices_chat.js';
import {
  initOrRefreshGraph,
  getActiveProjectRoot,
  selectGraphNode,
  deselectGraphNode,
  fitGraphToViewport,
  initCodebaseGraphEvents
} from './js/codebase_graph.js';
import {
  loadLocalWorker,
  loadWorkerQueue,
  renderWorkerQueue,
  selectLocalModel,
  pullLocalModel,
  startOllamaServer,
  stopOllamaServer,
  openOllamaConsole,
  closeOllamaConsole,
  fetchOllamaLogs,
  renderOllamaLogLine,
  initLocalWorkerEvents
} from './js/local_worker.js';
import {
  checkAutostartStatus,
  updateAutostartUI,
  loadSettings,
  applySettingsToUI,
  saveSettingUpdate,
  initSettingsEvents,
  checkOmniRouteStatus,
  loadOmniRouteSettings,
  initTerminalAndOmniEvents
} from './js/settings.js';
import {
  initWebSocket,
  socket
} from './js/websocket_client.js';
import {
  openCodeChat,
  initOpenCodeChat
} from './js/opencode_chat.js';


// 2. Exportação para Escopo Global (window) para Retrocompatibilidade com DOM e Testes
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'state', {
    get: () => state,
    set: (v) => { if (v !== state) setState(v); },
    configurable: true,
    enumerable: true
  });
  Object.defineProperty(window, 'currentProjectId', {
    get: () => currentProjectId,
    set: (v) => { if (v !== currentProjectId) setCurrentProjectId(v); },
    configurable: true,
    enumerable: true
  });
  Object.defineProperty(window, 'activeSliceId', {
    get: () => activeSliceId,
    set: (v) => { if (v !== activeSliceId) setActiveSliceId(v); },
    configurable: true,
    enumerable: true
  });
  Object.defineProperty(window, 'knownProjects', {
    get: () => knownProjects,
    set: (v) => { if (v !== knownProjects) setKnownProjects(v); },
    configurable: true,
    enumerable: true
  });
}

Object.assign(window, {
  // Utils
  escapeHtml,
  formatRelativeCwd,
  formatBytes,
  showToast,

  // State & Multi-Workspace Setters
  setState,
  setCurrentProjectId,
  setActiveSliceId,
  setKnownProjects,
  apiFetch,
  loadProjects,
  switchProject,
  triggerScanProjects,
  getPinnedProjectIds,
  savePinnedProjectIds,
  getRecentProjectIds,
  recordRecentProject,
  getProjectDotClass,
  getProjectDotTitle,

  // Sidebar & Navigation
  initSidebar,
  switchTab,
  renderWorktreeSidebar,
  togglePinProject,
  toggleShowMoreProjects,
  initOrcaNavigationAndModals,
  openQuickSearch,
  closeQuickSearch,
  renderQuickSearchResults,

  // Terminal Workspace
  TerminalWorkspaceManager,
  terminalWorkspace,
  initOrFitTerminal,
  sendTerminalCommand,

  // File Explorer
  FileExplorerManager,
  fileExplorerManager,

  // Slices & Governance
  renderAll,
  renderHeaderAndKPIs,
  loadHandoff,
  renderNodes,
  getNodeStatusClass,
  renderTaskCard,
  renderPairs,
  createPairCard,
  getAgentStatusClass,
  renderFinalGate,
  renderChatMessages,
  renderGauntletFull,
  updateDrawerContent,
  initSlicesChatEvents,
  activeSliceTabId,
  setActiveSliceTabId,
  getActiveSliceTabId,
  renderSliceTabs,
  switchSliceTab,
  renderDedicatedSliceView,
  renderDedicatedSliceChatMessages,

  // Codebase Graph
  initOrRefreshGraph,
  getActiveProjectRoot,
  selectGraphNode,
  deselectGraphNode,
  fitGraphToViewport,
  initCodebaseGraphEvents,

  // Local AI Worker
  loadLocalWorker,
  loadWorkerQueue,
  renderWorkerQueue,
  selectLocalModel,
  pullLocalModel,
  startOllamaServer,
  stopOllamaServer,
  openOllamaConsole,
  closeOllamaConsole,
  fetchOllamaLogs,
  renderOllamaLogLine,
  initLocalWorkerEvents,

  // Settings & Integrations
  checkAutostartStatus,
  updateAutostartUI,
  loadSettings,
  applySettingsToUI,
  saveSettingUpdate,
  initSettingsEvents,
  checkOmniRouteStatus,
  loadOmniRouteSettings,
  initTerminalAndOmniEvents,

  // WebSocket
  initWebSocket,
  cockpitSocket: socket,

  // OpenCode Visual Chat
  openCodeChat,
  initOpenCodeChat
});

// 3. Inicialização e Bootstrapping da Aplicação
async function bootstrapCockpit() {
  console.log('[Agent Cockpit] Inicializando orquestrador modular...');

  const safeInit = (name, fn) => {
    try {
      fn();
    } catch (err) {
      console.warn(`[Agent Cockpit] Aviso ao inicializar ${name}:`, err);
    }
  };

  // 1. Inicializa subsistemas visuais e eventos
  safeInit("initSidebar", initSidebar);
  safeInit("initSlicesChatEvents", initSlicesChatEvents);
  safeInit("initCodebaseGraphEvents", initCodebaseGraphEvents);
  safeInit("initLocalWorkerEvents", initLocalWorkerEvents);
  safeInit("initSettingsEvents", initSettingsEvents);
  safeInit("initTerminalAndOmniEvents", initTerminalAndOmniEvents);

  // 2. Inicializa terminais virtuais, explorador de arquivos e chat visual
  safeInit("terminalWorkspace.init", () => terminalWorkspace.init());
  safeInit("fileExplorerManager.init", () => fileExplorerManager.init());
  safeInit("initOpenCodeChat", initOpenCodeChat);

  // 3. Inicializa conexão WebSocket em tempo real
  safeInit("initWebSocket", initWebSocket);

  // 4. Carrega projetos e sincroniza estado dos subsistemas
  try {
    await loadProjects();
    renderWorktreeSidebar();
  } catch (err) {
    console.warn('[Agent Cockpit] Erro ao carregar projetos iniciais:', err);
  }

  checkAutostartStatus();
  loadLocalWorker();
  loadSettings();
  loadOmniRouteSettings();

  if (typeof fileExplorerManager !== 'undefined' && fileExplorerManager) {
    fileExplorerManager.loadFileTree(currentProjectId);
  }

  // Terminal é a view primária padrão do Cockpit: ajusta terminais imediatamente
  if (typeof terminalWorkspace !== 'undefined' && terminalWorkspace) {
    terminalWorkspace.fitAll();
    setTimeout(() => terminalWorkspace.fitAll(), 150);
  }

  console.log('[Agent Cockpit] Inicialização modular concluída com sucesso.');
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrapCockpit);
  } else {
    bootstrapCockpit();
  }
}

// Exportações do entrypoint
export {
  terminalWorkspace,
  fileExplorerManager,
  switchProject,
  switchTab,
  renderWorktreeSidebar,
  openCodeChat,
  initOpenCodeChat
};

