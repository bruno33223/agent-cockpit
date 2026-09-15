/**
 * Agent Cockpit - Main Entrypoint & System Orchestrator (ES Module)
 * Clean Architecture & SOLID Modular Decomposition (Issue #9)
 */

// 1. Importação dos Módulos Especializados
import { escapeHtml, formatRelativeCwd, formatBytes, showToast } from './js/ui_utils.js';
import {
  state,
  currentProjectId,
  activeSliceId,
  knownProjects,
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
  updateDrawerContent
} from './js/slices_chat.js';
import {
  initOrRefreshGraph,
  getActiveProjectRoot,
  selectGraphNode,
  deselectGraphNode,
  fitGraphToViewport
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

// 2. Exportação para Escopo Global (window) para Retrocompatibilidade com DOM e Testes
Object.assign(window, {
  // Utils
  escapeHtml,
  formatRelativeCwd,
  formatBytes,
  showToast,

  // State & Multi-Workspace
  state,
  currentProjectId,
  activeSliceId,
  knownProjects,
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

  // Codebase Graph
  initOrRefreshGraph,
  getActiveProjectRoot,
  selectGraphNode,
  deselectGraphNode,
  fitGraphToViewport,

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
  cockpitSocket: socket
});

// 3. Inicialização e Bootstrapping da Aplicação
document.addEventListener('DOMContentLoaded', async () => {
  console.log('[Agent Cockpit] Inicializando módulos desacoplados...');

  // 1. Inicializa navegação, sidebar e atalhos
  initSidebar();

  // 2. Inicializa workspace de terminais e explorador de arquivos
  terminalWorkspace.init();
  fileExplorerManager.init();

  // 3. Inicializa conexão WebSocket em tempo real
  initWebSocket();

  // 4. Carrega estado de projetos e subsistemas
  await loadProjects();
  checkAutostartStatus();
  loadLocalWorker();
  loadSettings();
  loadOmniRouteSettings();

  // 5. Inicializa listeners de eventos de configurações e local worker
  initLocalWorkerEvents();
  initSettingsEvents();
  initTerminalAndOmniEvents();

  console.log('[Agent Cockpit] Inicialização concluída com sucesso.');
});

// Exportações do entrypoint
export {
  terminalWorkspace,
  fileExplorerManager,
  switchProject,
  switchTab,
  renderWorktreeSidebar
};
