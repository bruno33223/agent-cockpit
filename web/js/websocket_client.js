/**
 * Módulo de Cliente WebSocket / SSE (WebSocket Client)
 * Gerencia ciclo de vida da conexão bidirecional, reconexão com backoff e despacho de eventos.
 */

import {
  WS_BASE,
  currentProjectId,
  state,
  setState,
  knownProjects,
  setKnownProjects,
  setCurrentProjectId,
  renderProjectSelectOptions
} from './state.js';
import {
  renderAll,
  updateDrawerContent,
  renderChatMessages,
  loadHandoff
} from './slices_chat.js';
import { renderWorktreeSidebar } from './sidebar.js';
import {
  renderOllamaLogLine,
  localWorkerStatus,
  renderLocalWorkerUI,
  renderWorkerQueue,
  loadLocalWorker,
  loadLocalWorkerModels
} from './local_worker.js';
import {
  currentSettings,
  applySettingsToUI
} from './settings.js';
import { fileExplorerManager } from './file_explorer.js';
import { terminalWorkspace } from './terminal_workspace.js';

export let socket = null;

const getWsStatusText = () => document.getElementById('ws-status-text');
const getWsStatusPill = () => document.getElementById('ws-status');
const getPullFeedbackMsg = () => document.getElementById('pull-feedback-msg');

export function initWebSocket() {
  const wsStatusText = getWsStatusText();
  const wsStatusPill = getWsStatusPill();
  if (wsStatusText) wsStatusText.textContent = 'WS Conectando...';
  const led = wsStatusPill ? wsStatusPill.querySelector('.pulse-led') : null;
  if (led) led.className = 'pulse-led offline';

  try {
    socket = new WebSocket(WS_BASE);
  } catch (err) {
    console.error('[WebSocket] Erro ao instanciar:', err);
    setTimeout(initWebSocket, 3000);
    return;
  }

  socket.onopen = () => {
    const wsStatusText = getWsStatusText();
    const wsStatusPill = getWsStatusPill();
    const led = wsStatusPill ? wsStatusPill.querySelector('.pulse-led') : null;
    if (led) led.className = 'pulse-led online';
    if (wsStatusText) wsStatusText.textContent = 'WS Online';
    
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
        setKnownProjects(data.payload || []);
        renderProjectSelectOptions();
        renderWorktreeSidebar();
      } else if (data.event === 'STATE_FULL') {
        const incomingPid = data.project_id || (data.payload && (data.payload.active_project_id || data.payload.project_id));
        if (!incomingPid || incomingPid === currentProjectId) {
          const incomingState = data.payload || {};
          incomingState.active_project_id = currentProjectId;
          setState(incomingState);
          renderAll();
          loadLocalWorker();
          if (typeof fileExplorerManager !== 'undefined' && fileExplorerManager) {
            fileExplorerManager.updateProjectHeader();
          }
        }
      } else if (data.event === 'PROJECT_ROOT_UPDATED' || data.event === 'PROJECT_SWITCHED') {
        if (!data.project_id || data.project_id === currentProjectId) {
          if (typeof fileExplorerManager !== 'undefined' && fileExplorerManager) {
            fileExplorerManager.loadFileTree(currentProjectId, true);
          }
        }
      } else if (data.event === 'SETTINGS_UPDATED') {
        if (!data.project_id || data.project_id === currentProjectId) {
          Object.assign(currentSettings, data.payload || {});
          applySettingsToUI(currentSettings);
        }
      } else if (data.event === 'LOCAL_WORKER_CONFIG_UPDATED' || data.event === 'LOCAL_WORKER_STATUS_CHANGED' || data.event === 'ollama_status' || data.type === 'ollama_status') {
        if (!data.project_id || data.project_id === currentProjectId) {
          if (data.payload && typeof data.payload === 'object') {
            const p = data.payload;
            if (p.running !== undefined) localWorkerStatus.running = !!p.running;
            if (p.pid !== undefined) localWorkerStatus.pid = p.pid || null;
            if (p.enabled !== undefined) {
              currentSettings.enable_local_ai = !!p.enabled;
              applySettingsToUI(currentSettings);
            }
            if (p.delegate_styles_to_cloud !== undefined) {
              currentSettings.delegate_styles_to_cloud = !!p.delegate_styles_to_cloud;
              applySettingsToUI(currentSettings);
            }
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
        const pullFeedbackMsg = getPullFeedbackMsg();

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
        const pullFeedbackMsg = getPullFeedbackMsg();

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
      } else if (data.event === 'subagent_spawn' || data.type === 'subagent_spawn' || data.event === 'SUBAGENT_SPAWN') {
        const subPayload = data.payload || data;
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('subagent_spawn', { detail: subPayload }));
        }
      }
    } catch (e) {
      console.error('Erro processando mensagem WebSocket:', e);
    }
  };

  socket.onclose = () => {
    const wsStatusText = getWsStatusText();
    const wsStatusPill = getWsStatusPill();
    const led = wsStatusPill ? wsStatusPill.querySelector('.pulse-led') : null;
    if (led) led.className = 'pulse-led offline';
    if (wsStatusText) wsStatusText.textContent = 'WS Desconectado';
    setTimeout(initWebSocket, 2000);
  };

  socket.onerror = () => {
    if (socket) socket.close();
  };
}
