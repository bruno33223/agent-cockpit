/**
 * Módulo de Gerenciamento do Local Worker & Ollama Manager
 * Gestão do ciclo de vida do servidor Ollama local, modelos, fila de inferência
 * e console web de telemetria e streaming de logs.
 */

import { escapeHtml } from './ui_utils.js';
import { apiFetch, currentProjectId } from './state.js';

export let isOllamaAutoScrollEnabled = true;
export const MAX_LOG_LINES = 200;
const MAX_DEDUP_CACHE_SIZE = 500;
const recentLogsCache = new Set();


export let localWorkerStatus = {
  online: false,
  running: false,
  pid: null,
  model: '',
  endpoint: 'http://127.0.0.1:11434',
  installed: [],
  recommended: []
};

// Elementos DOM do Local Worker & Ollama
let lwPillLed = null;
let lwTopbarSelect = null;
let btnTopbarPullModal = null;
let lwStatusBadge = null;
let lwSidebarSelect = null;
let lwEndpointDisplay = null;
let btnOpenPullModal = null;
let modalModelDownload = null;
let btnCloseModelModal = null;
let formCustomPull = null;
let inputCustomModel = null;
let btnStartPull = null;
let pullStatusBox = null;
let pullStatusMessage = null;
let pullFeedbackMsg = null;
let lwProcessStatus = null;
let lwProcessPid = null;
let terminalProcessStatus = null;
let terminalLogCounter = null;
let modalOllamaConsole = null;
let ollamaTerminalLogs = null;
let inputHfSearch = null;
let hfSearchResults = null;
let hfSearchSpinner = null;
let hfDebounceTimer = null;

export function resolveLocalWorkerElements() {
  if (typeof document === 'undefined') return;
  lwPillLed = document.getElementById('lw-pill-led');
  lwTopbarSelect = document.getElementById('lw-topbar-select');
  btnTopbarPullModal = document.getElementById('btn-topbar-pull-modal');
  lwStatusBadge = document.getElementById('lw-status-badge');
  lwSidebarSelect = document.getElementById('lw-sidebar-select');
  lwEndpointDisplay = document.getElementById('lw-endpoint-display');
  btnOpenPullModal = document.getElementById('btn-open-pull-modal');
  modalModelDownload = document.getElementById('modal-model-download');
  btnCloseModelModal = document.getElementById('btn-close-model-modal');
  formCustomPull = document.getElementById('form-custom-pull');
  inputCustomModel = document.getElementById('input-custom-model');
  btnStartPull = document.getElementById('btn-start-pull');
  pullStatusBox = document.getElementById('pull-status-box');
  pullStatusMessage = document.getElementById('pull-status-message');
  pullFeedbackMsg = document.getElementById('pull-feedback-msg');
  lwProcessStatus = document.getElementById('lw-process-status');
  lwProcessPid = document.getElementById('lw-process-pid');
  terminalProcessStatus = document.getElementById('terminal-process-status');
  terminalLogCounter = document.getElementById('terminal-log-counter');
  modalOllamaConsole = document.getElementById('modal-ollama-console');
  ollamaTerminalLogs = document.getElementById('ollama-terminal-logs');
  inputHfSearch = document.getElementById('input-hf-search') || document.getElementById('hf-search-input');
  hfSearchResults = document.getElementById('hf-search-results');
  hfSearchSpinner = document.getElementById('hf-search-spinner');
}

export async function loadLocalWorker() {
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

export async function loadWorkerQueue() {
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

export function renderWorkerQueue(queueData) {
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

export async function loadLocalWorkerModels() {
  await loadLocalWorker();
}

export function renderLocalWorkerUI() {
  if (!lwStatusBadge) resolveLocalWorkerElements();
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

export async function selectLocalModel(modelName) {
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

export async function pullLocalModel(modelName) {
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

export function openModelModal() {
  if (!modalModelDownload) resolveLocalWorkerElements();
  if (modalModelDownload) {
    modalModelDownload.style.display = 'flex';
    if (pullFeedbackMsg) pullFeedbackMsg.style.display = 'none';
    if (pullStatusBox) pullStatusBox.style.display = 'none';
  }
}

export function closeModelModal() {
  if (!modalModelDownload) resolveLocalWorkerElements();
  if (modalModelDownload) {
    modalModelDownload.style.display = 'none';
  }
}

/**
 * Formata números de métricas para visualização simplificada (ex: 1.2k, 450k, 1.5M).
 */
function formatMetricNumber(num) {
  if (!num && num !== 0) return '0';
  const val = Number(num);
  if (isNaN(val)) return String(num);
  if (val >= 1000000) return (val / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (val >= 1000) return (val / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(val);
}

/**
 * Realiza pesquisa de modelos no Hugging Face através do endpoint /api/local-worker/hf-search.
 */
export async function searchHuggingFaceModels(query) {
  const q = (query || '').trim();
  if (!hfSearchResults) {
    hfSearchResults = document.getElementById('hf-search-results');
  }
  if (!hfSearchResults) return;

  if (!q) {
    hfSearchResults.innerHTML = `
      <div class="hf-search-placeholder">
        <p>Digite o nome de um modelo ou repositório para pesquisar no Hugging Face (ex: Qwen, DeepSeek, Llama)...</p>
      </div>
    `;
    return;
  }

  hfSearchResults.innerHTML = `
    <div class="hf-search-loading">
      <span class="pull-spinner">⏳</span> Buscando modelos "${escapeHtml(q)}" no Hugging Face...
    </div>
  `;

  try {
    const res = await apiFetch(`/api/local-worker/hf-search?query=${encodeURIComponent(q)}&project_id=${encodeURIComponent(currentProjectId)}`);
    if (!res.ok) {
      throw new Error(`Erro ${res.status}: Não foi possível consultar o Hugging Face`);
    }
    const data = await res.json();
    const models = Array.isArray(data) ? data : (data.models || data.results || []);
    renderHfSearchResults(models);
  } catch (err) {
    console.error('[LocalWorker] Erro ao buscar modelos no Hugging Face:', err);
    if (hfSearchResults) {
      hfSearchResults.innerHTML = `
        <div class="hf-search-error">
          <p>⚠️ Falha na busca Hugging Face: ${escapeHtml(err.message || 'Erro de rede')}</p>
        </div>
      `;
    }
  }
}

/**
 * Renderiza os cards de resultados do Hugging Face no container #hf-search-results.
 * Exibe título, autor, métricas (downloads, likes), badges de quantização (GGUF, Q4_K_M, etc.)
 * e botão de ação 'Baixar Modelo' chamando pullLocalModel(tag).
 */
export function renderHfSearchResults(models) {
  if (!hfSearchResults) {
    hfSearchResults = document.getElementById('hf-search-results');
  }
  if (!hfSearchResults) return;

  if (!models || models.length === 0) {
    hfSearchResults.innerHTML = `
      <div class="hf-search-empty">
        <p>Nenhum modelo encontrado no Hugging Face para os critérios informados.</p>
      </div>
    `;
    return;
  }

  const cardsHtml = models.map(m => {
    const modelId = m.id || m.name || m.model_id || 'unknown/model';
    const parts = modelId.split('/');
    const author = m.author || (parts.length > 1 ? parts[0] : 'Hugging Face');
    const title = m.title || (parts.length > 1 ? parts.slice(1).join('/') : modelId);
    const downloads = formatMetricNumber(m.downloads || m.download_count || 0);
    const likes = formatMetricNumber(m.likes || m.likes_count || 0);
    const desc = m.description || m.summary || m.pipeline_tag || '';

    // Quantizações e tags
    let quants = m.quantizations || m.quants || [];
    if (typeof quants === 'string') {
      quants = [quants];
    } else if (!Array.isArray(quants)) {
      quants = [];
    }
    if (quants.length === 0 && (modelId.toLowerCase().includes('gguf') || (m.tags && m.tags.includes('gguf')))) {
      quants = ['GGUF', 'Q4_K_M'];
    }

    const quantBadges = quants.length > 0
      ? quants.map(q => `<span class="hf-badge quant" title="Quantização ${escapeHtml(q)}">${escapeHtml(q)}</span>`).join('')
      : `<span class="hf-badge quant default">GGUF</span>`;

    // Identificador para Ollama pull
    const modelTag = m.ollama_tag || m.tag || (modelId.startsWith('hf.co/') ? modelId : `hf.co/${modelId}`);

    return `
      <div class="hf-model-card" data-model="${escapeHtml(modelTag)}">
        <div class="hf-model-card-header">
          <div class="hf-model-title-box">
            <span class="hf-model-author">${escapeHtml(author)}</span>
            <h5 class="hf-model-title" title="${escapeHtml(modelId)}">${escapeHtml(title)}</h5>
          </div>
          <div class="hf-model-metrics">
            <span class="hf-metric downloads" title="${downloads} downloads">📥 ${escapeHtml(downloads)} downloads</span>
            <span class="hf-metric likes" title="${likes} likes">❤️ ${escapeHtml(likes)} likes</span>
          </div>
        </div>
        ${desc ? `<p class="hf-model-desc">${escapeHtml(desc)}</p>` : ''}
        <div class="hf-model-card-footer">
          <div class="hf-quant-badges">
            ${quantBadges}
          </div>
          <button class="action-btn primary btn-sm btn-hf-pull" data-model="${escapeHtml(modelTag)}">
            Baixar Modelo
          </button>
        </div>
      </div>
    `;
  }).join('');

  hfSearchResults.innerHTML = `
    <div class="hf-cards-grid">
      ${cardsHtml}
    </div>
  `;

  // Vincula evento de clique no botão 'Baixar Modelo' de cada card
  hfSearchResults.querySelectorAll('.btn-hf-pull').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const tag = btn.getAttribute('data-model');
      if (tag) {
        pullLocalModel(tag);
      }
    });
  });
}

export async function startOllamaServer() {
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

export async function stopOllamaServer() {
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

export function openOllamaConsole() {
  if (!modalOllamaConsole) resolveLocalWorkerElements();
  if (modalOllamaConsole) {
    modalOllamaConsole.style.display = 'flex';
    fetchOllamaLogs();
    if (!ollamaLogsPollingInterval) {
      ollamaLogsPollingInterval = setInterval(fetchOllamaLogs, 3000);
    }
  }
}

export function closeOllamaConsole() {
  if (!modalOllamaConsole) resolveLocalWorkerElements();
  if (modalOllamaConsole) {
    modalOllamaConsole.style.display = 'none';
  }
  if (ollamaLogsPollingInterval) {
    clearInterval(ollamaLogsPollingInterval);
    ollamaLogsPollingInterval = null;
  }
}

export async function fetchOllamaLogs() {
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

export function renderOllamaLogLine(line) {
  const terminal = document.getElementById('ollama-terminal-logs');
  const inpageTerminal = document.getElementById('inpage-ollama-logs');
  if (!terminal && !inpageTerminal) return;

  let text = '';
  let timestamp = '';

  if (typeof line === 'string') {
    text = line;
  } else if (line && typeof line === 'object') {
    text = line.message || line.text || line.line || JSON.stringify(line);
    timestamp = line.timestamp || line.time || '';
  }

  // Deduplicação: evita inserções redundantes simultâneas entre WebSocket e polling
  const dedupKey = `${timestamp}::${text}`;
  if (recentLogsCache.has(dedupKey)) {
    return;
  }
  recentLogsCache.add(dedupKey);
  if (recentLogsCache.size > MAX_DEDUP_CACHE_SIZE) {
    const oldestKey = recentLogsCache.values().next().value;
    if (oldestKey !== undefined) {
      recentLogsCache.delete(oldestKey);
    }
  }

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
    // Poda FIFO no container de logs para garantir buffer circular estrito de 200 linhas
    while (terminal.childElementCount > MAX_LOG_LINES) {
      if (terminal.firstElementChild) {
        terminal.firstElementChild.remove();
      } else {
        break;
      }
    }
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
    // Poda FIFO no container de logs da página do worker
    while (inpageTerminal.childElementCount > MAX_LOG_LINES) {
      if (inpageTerminal.firstElementChild) {
        inpageTerminal.firstElementChild.remove();
      } else {
        break;
      }
    }
    if (isOllamaAutoScrollEnabled) {
      inpageTerminal.scrollTop = inpageTerminal.scrollHeight;
    }
  }
}

export function initLocalWorkerEvents() {
  resolveLocalWorkerElements();

  const btnStartOllama = document.getElementById('btn-start-ollama');
  const btnStopOllama = document.getElementById('btn-stop-ollama');
  const btnOpenOllamaConsole = document.getElementById('btn-open-ollama-console');
  const btnCloseOllamaConsole = document.getElementById('btn-close-ollama-console');
  const btnClearOllamaLogs = document.getElementById('btn-clear-ollama-logs');
  const btnToggleAutoscroll = document.getElementById('btn-toggle-autoscroll');

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
      recentLogsCache.clear();
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
      recentLogsCache.clear();
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

  // Hugging Face: busca de modelos com debounce
  if (inputHfSearch) {
    inputHfSearch.addEventListener('input', (e) => {
      const val = e.target.value;
      if (hfDebounceTimer) {
        clearTimeout(hfDebounceTimer);
      }
      hfDebounceTimer = setTimeout(() => {
        searchHuggingFaceModels(val);
      }, 350);
    });
  }

  // Hugging Face: delegação de clique em 'Baixar Modelo' nos cards
  if (hfSearchResults) {
    hfSearchResults.addEventListener('click', (e) => {
      const pullBtn = e.target.closest('.btn-hf-pull');
      if (pullBtn) {
        e.preventDefault();
        const modelTag = pullBtn.getAttribute('data-model');
        if (modelTag) {
          pullLocalModel(modelTag);
        }
      }
    });
  }
}


