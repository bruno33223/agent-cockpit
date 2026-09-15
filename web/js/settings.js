/**
 * Módulo de Configurações, OmniRoute e Autostart (Settings)
 * Painel de configurações gerais, status de conexões OmniRoute e controle
 * do serviço de autostart com o sistema operacional.
 */

import { apiFetch } from './state.js';
import { escapeHtml } from './ui_utils.js';

// AUTOSTART LOGIC
const btnAutostart = document.getElementById('btn-autostart');
let autostartEnabled = false;

async export function checkAutostartStatus() {
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

export function updateAutostartUI(enabled) {
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


async export function loadSettings() {
  try {
    const res = await apiFetch(`/api/settings?project_id=${encodeURIComponent(currentProjectId)}`);
    if (res.ok) {
      const data = await res.json();
      currentSettings = Object.assign(currentSettings, data);
      applySettingsToUI(currentSettings);
    }
    const modelsRes = await apiFetch(`/api/local-worker/models?project_id=${encodeURIComponent(currentProjectId)}`);
    if (modelsRes.ok) {
      const modelsData = await modelsRes.json();
      populateSettingsModelSelect(modelsData.installed || [], currentSettings.model);
    }
  } catch (err) {
    console.warn('[Settings] Falha ao carregar configurações:', err);
  }
}

export function applySettingsToUI(settings) {
  if (!settings) return;

  const toggleLocalAi = document.getElementById('toggle-enable-local-ai');
  const localAiLabel = document.getElementById('enable-local-ai-status-label');
  const localAiCard = document.getElementById('local-ai-card');

  if (toggleLocalAi) {
    toggleLocalAi.checked = !!settings.enable_local_ai;
  }

  if (localAiLabel) {
    if (settings.enable_local_ai) {
      localAiLabel.textContent = 'Ativado (Atenção: Uso Experimental)';
      localAiLabel.classList.add('active');
    } else {
      localAiLabel.textContent = 'Desativado por Padrão (100% Nuvem Frontier)';
      localAiLabel.classList.remove('active');
    }
  }

  if (localAiCard) {
    localAiCard.classList.toggle('active', !!settings.enable_local_ai);
  }

  const toggleStyles = document.getElementById('toggle-delegate-styles');
  const stylesLabel = document.getElementById('delegate-styles-status-label');
  const highlightCard = document.querySelector('.settings-card.highlight-card:not(.experimental-card)');

  if (toggleStyles) {
    toggleStyles.checked = !!settings.delegate_styles_to_cloud;
  }

  if (stylesLabel) {
    if (settings.delegate_styles_to_cloud) {
      stylesLabel.textContent = 'Ativado (Design de Nuvem)';
      stylesLabel.classList.add('active');
    } else {
      stylesLabel.textContent = 'Desativado (100% Local GPU)';
      stylesLabel.classList.remove('active');
    }
  }

  if (highlightCard) {
    highlightCard.classList.toggle('active', !!settings.delegate_styles_to_cloud);
  }

  const breakerInput = document.getElementById('settings-breaker-threshold');
  if (breakerInput && settings.circuit_breaker_threshold !== undefined) {
    breakerInput.value = settings.circuit_breaker_threshold;
  }

  const autoStartToggle = document.getElementById('toggle-auto-start-ollama');
  if (autoStartToggle && settings.auto_start_ollama !== undefined) {
    autoStartToggle.checked = !!settings.auto_start_ollama;
  }

  const projectRootInput = document.getElementById('settings-project-root-input');
  if (projectRootInput && settings.project_root !== undefined) {
    projectRootInput.value = settings.project_root || '';
  }

  if (settings.model) {
    const modelSelect = document.getElementById('settings-model-select');
    if (modelSelect && modelSelect.value !== settings.model) {
      modelSelect.value = settings.model;
    }
  }
}

export function populateSettingsModelSelect(installedModels, currentModel) {
  const modelSelect = document.getElementById('settings-model-select');
  if (!modelSelect) return;

  modelSelect.innerHTML = '';

  if (installedModels.length === 0) {
    const opt = document.createElement('option');
    opt.value = currentModel || 'qwen2.5-coder:7b-instruct-q4_k_m';
    opt.textContent = `${currentModel || 'qwen2.5-coder:7b'} (Ativo)`;
    modelSelect.appendChild(opt);
    return;
  }

  installedModels.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m === currentModel ? `${m} (Ativo)` : m;
    if (m === currentModel) opt.selected = true;
    modelSelect.appendChild(opt);
  });

  if (currentModel && !installedModels.includes(currentModel)) {
    const opt = document.createElement('option');
    opt.value = currentModel;
    opt.textContent = `${currentModel} (Não listado)`;
    opt.selected = true;
    modelSelect.appendChild(opt);
  }
}

async export function saveSettingUpdate(updates, successNotice = 'Configuração salva com sucesso!') {
  try {
    const payload = Object.assign({ project_id: currentProjectId }, updates);
    const res = await apiFetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const data = await res.json();
      currentSettings = Object.assign(currentSettings, data);
      applySettingsToUI(currentSettings);
      console.log(`[Settings] ${successNotice}`);
    }
  } catch (err) {
    console.error('[Settings] Falha ao atualizar configuração:', err);
  }
}

export function initSettingsEvents() {
  const toggleLocalAi = document.getElementById('toggle-enable-local-ai');
  if (toggleLocalAi) {
    toggleLocalAi.addEventListener('change', () => {
      const isChecked = toggleLocalAi.checked;
      saveSettingUpdate(
        { enable_local_ai: isChecked },
        isChecked ? 'Worker Local ativado (Experimental)! Recomendado apenas para funções mecânicas/auxiliares.' : 'Worker Local desativado. Geração 100% direta via Nuvem Frontier.'
      );
    });
  }

  const toggleStyles = document.getElementById('toggle-delegate-styles');
  if (toggleStyles) {
    toggleStyles.addEventListener('change', () => {
      const isChecked = toggleStyles.checked;
      saveSettingUpdate(
        { delegate_styles_to_cloud: isChecked },
        isChecked ? 'Estilos delegados para a nuvem ativados!' : 'Estilos 100% locais restaurados.'
      );
    });
  }

  const btnRefreshSettings = document.getElementById('btn-refresh-settings');
  if (btnRefreshSettings) {
    btnRefreshSettings.addEventListener('click', () => loadSettings());
  }

  const btnSaveModel = document.getElementById('btn-save-model-choice');
  if (btnSaveModel) {
    btnSaveModel.addEventListener('click', () => {
      const modelSelect = document.getElementById('settings-model-select');
      if (modelSelect && modelSelect.value) {
        saveSettingUpdate({ model: modelSelect.value }, `Modelo alterado para ${modelSelect.value}`);
      }
    });
  }

  const btnSaveBreaker = document.getElementById('btn-save-breaker-threshold');
  if (btnSaveBreaker) {
    btnSaveBreaker.addEventListener('click', () => {
      const breakerInput = document.getElementById('settings-breaker-threshold');
      if (breakerInput && breakerInput.value) {
        const val = parseInt(breakerInput.value, 10);
        if (!isNaN(val) && val >= 1) {
          saveSettingUpdate({ circuit_breaker_threshold: val }, `Circuit breaker ajustado para ${val} tentativas`);
        }
      }
    });
  }

  const autoStartToggle = document.getElementById('toggle-auto-start-ollama');
  if (autoStartToggle) {
    autoStartToggle.addEventListener('change', () => {
      saveSettingUpdate(
        { auto_start_ollama: autoStartToggle.checked },
        autoStartToggle.checked ? 'Autostart do Ollama habilitado' : 'Autostart do Ollama desabilitado'
      );
    });
  }

  const btnSaveRoot = document.getElementById('btn-save-project-root');
  if (btnSaveRoot) {
    btnSaveRoot.addEventListener('click', () => {
      const rootInput = document.getElementById('settings-project-root-input');
      if (rootInput && rootInput.value.trim()) {
        saveSettingUpdate({ project_root: rootInput.value.trim() }, 'Raiz do projeto atualizada!');
      }
    });
  }
}

// =========================================================================
// TERMINAL PTY & OPENCODE / OMNIROUTE RUNNER (ORCA WORKBENCH)

async export function checkOmniRouteStatus() {
  const indicator = document.getElementById('terminal-omni-indicator');
  const pill = document.getElementById('omniroute-status-pill');
  try {
    const res = await apiFetch('/api/omniroute/status');
    if (res.ok) {
      const data = await res.json();
      if (data.online) {
        const text = `OmniRoute: Online (${data.models ? data.models.length : 0} modelos)`;
        if (indicator) indicator.textContent = text;
        if (pill) {
          pill.className = 'lw-badge active';
          pill.textContent = 'Online';
        }
      } else {
        const text = 'OmniRoute: Offline';
        if (indicator) indicator.textContent = text;
        if (pill) {
          pill.className = 'lw-badge stopped';
          pill.textContent = 'Offline';
        }
      }
    }
  } catch (e) {
    if (indicator) indicator.textContent = 'OmniRoute: Offline';
    if (pill) {
      pill.className = 'lw-badge stopped';
      pill.textContent = 'Offline';
    }
  }
}

async export function loadOmniRouteSettings() {
  const urlInput = document.getElementById('omniroute-url-input');
  const keyInput = document.getElementById('omniroute-key-input');
  const modelInput = document.getElementById('omniroute-model-input');

  try {
    const res = await apiFetch('/api/omniroute/config');
    if (res.ok) {
      const cfg = await res.json();
      if (urlInput && cfg.omniroute_url) urlInput.value = cfg.omniroute_url;
      if (keyInput && cfg.api_key) keyInput.value = cfg.api_key;
      if (modelInput && cfg.model) modelInput.value = cfg.model;
    }
  } catch (e) {
    console.warn('Erro ao carregar configurações do OmniRoute:', e);
  }

  checkOmniRouteStatus();
}

export function initTerminalAndOmniEvents() {
  const btnSaveOmni = document.getElementById('btn-save-omniroute-config');
  if (btnSaveOmni) {
    btnSaveOmni.addEventListener('click', async () => {
      const urlInput = document.getElementById('omniroute-url-input');
      const keyInput = document.getElementById('omniroute-key-input');
      const modelInput = document.getElementById('omniroute-model-input');
      const feedback = document.getElementById('omniroute-feedback-msg');

      const payload = {
        omniroute_url: urlInput ? urlInput.value.trim() : 'http://localhost:20128/v1',
        api_key: keyInput ? keyInput.value.trim() : 'omniroute-local',
        model: modelInput ? modelInput.value.trim() : 'auto'
      };

      try {
        btnSaveOmni.textContent = 'Salvando...';
        const res = await fetch('/api/omniroute/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        btnSaveOmni.textContent = 'Salvar & Sincronizar opencode.json';

        if (result.status === 'success') {
          if (feedback) {
            feedback.style.display = 'block';
            feedback.className = 'omniroute-feedback success';
            feedback.textContent = 'Configurações salvas! Arquivo opencode.json sincronizado com MCP do Cockpit com sucesso.';
          }
          checkOmniRouteStatus();
        } else {
          if (feedback) {
            feedback.style.display = 'block';
            feedback.className = 'omniroute-feedback error';
            feedback.textContent = `Erro ao salvar: ${result.message || 'Falha'}`;
          }
        }
      } catch (err) {
        btnSaveOmni.textContent = 'Salvar & Sincronizar opencode.json';
        if (feedback) {
          feedback.style.display = 'block';
          feedback.className = 'omniroute-feedback error';
          feedback.textContent = `Erro de conexão: ${err.message}`;
        }
      }
    });
  }

  const btnTestOmni = document.getElementById('btn-test-omniroute');
  if (btnTestOmni) {
    btnTestOmni.addEventListener('click', async () => {
      const urlInput = document.getElementById('omniroute-url-input');
      const feedback = document.getElementById('omniroute-feedback-msg');
      const targetUrl = urlInput ? urlInput.value.trim() : 'http://localhost:20128/v1';

      try {
        btnTestOmni.textContent = 'Testando...';
        const res = await apiFetch(`/api/omniroute/status?base_url=${encodeURIComponent(targetUrl)}`);
        const data = await res.json();
        btnTestOmni.textContent = 'Testar Conexão OmniRoute';

        if (feedback) {
          feedback.style.display = 'block';
          if (data.online) {
            feedback.className = 'omniroute-feedback success';
            feedback.textContent = `OmniRoute ONLINE em ${data.endpoint}! Modelos detectados: ${data.models.length > 0 ? data.models.slice(0, 5).join(', ') + (data.models.length > 5 ? '...' : '') : 'Nenhum modelo retornado'}`;
          } else {
            feedback.className = 'omniroute-feedback error';
            feedback.textContent = `OmniRoute OFFLINE em ${data.endpoint}. Verifique se o processo "omniroute" foi iniciado no terminal. (${data.message})`;
          }
        }
        checkOmniRouteStatus();
      } catch (err) {
        btnTestOmni.textContent = 'Testar Conexão OmniRoute';
        if (feedback) {
          feedback.style.display = 'block';
          feedback.className = 'omniroute-feedback error';
          feedback.textContent = `Erro ao testar: ${err.message}`;
        }
      }
    });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 12. ORCA RIGHT SIDEBAR & FILE EXPLORER MANAGER
