/**
 * Módulo de Configurações, OmniRoute e Autostart (Settings)
 * Painel de configurações gerais, status de conexões OmniRoute e controle
 * do serviço de autostart com o sistema operacional.
 */

import { apiFetch, currentProjectId, state } from './state.js';
import { escapeHtml } from './ui_utils.js';

// AUTOSTART LOGIC
let autostartEnabled = false;

export async function checkAutostartStatus() {
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

export function getBtnAutostart() {
  return document.getElementById("btn-toggle-autostart") || document.getElementById("ag-btn-autostart-on");
}

export function updateAutostartUI(enabled) {
  autostartEnabled = !!enabled;
  const btnOn = document.getElementById('ag-btn-autostart-on');
  const btnOff = document.getElementById('ag-btn-autostart-off');
  if (btnOn && btnOff) {
    if (autostartEnabled) {
      btnOn.classList.add('active');
      btnOff.classList.remove('active');
    } else {
      btnOff.classList.add('active');
      btnOn.classList.remove('active');
    }
  }
}

export async function setSystemAutostart(enable) {
  try {
    const res = await apiFetch('/api/autostart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !!enable })
    });
    if (res.ok) {
      const data = await res.json();
      updateAutostartUI(data.enabled);
    }
  } catch (err) {
    console.error('[Autostart] Falha ao alterar autostart:', err);
  }
}

export function updateHumanGateUI(isApproved) {
  const badge = document.getElementById('ag-gate-badge');
  const btnApprove = document.getElementById('btn-ag-approve-gate');
  if (badge) {
    if (isApproved) {
      badge.className = 'gatekeeper-badge approved';
      badge.textContent = 'Gate: Liberado / Aprovado';
      if (btnApprove) btnApprove.style.display = 'none';
    } else {
      badge.className = 'gatekeeper-badge pending';
      badge.textContent = 'Gate: Pendente';
      if (btnApprove) btnApprove.style.display = 'inline-flex';
    }
  }
}

export async function approveHumanGate() {
  try {
    const btnApprove = document.getElementById('btn-ag-approve-gate');
    if (btnApprove) {
      btnApprove.disabled = true;
      btnApprove.innerHTML = 'Aprovando...';
    }
    const res = await apiFetch('/api/gates/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gate_name: 'gate_ship_approved', project_id: currentProjectId })
    });
    if (res.ok) {
      updateHumanGateUI(true);
    }
  } catch (err) {
    console.error('[HumanGate] Falha ao aprovar portão:', err);
  } finally {
    const btnApprove = document.getElementById('btn-ag-approve-gate');
    if (btnApprove) {
      btnApprove.disabled = false;
      btnApprove.innerHTML = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg> Aprovar Gate';
    }
  }
}

// ==========================================================================
// 8. CONFIGURAÇÕES GERAIS & HARNESS DE IA LOCAL
// ==========================================================================

export let currentSettings = {
  enable_local_ai: false,
  delegate_styles_to_cloud: true,
  model: 'deepseek-coder-v2:16b-q3_k_m',
  endpoint: 'http://127.0.0.1:11434',
  auto_start_ollama: false,
  circuit_breaker_threshold: 2,
  project_root: ''
};

export async function loadSettings() {
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

export async function saveSettingUpdate(updates, successNotice = 'Configuração salva com sucesso!') {
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

  const btnOn = document.getElementById("ag-btn-autostart-on");
  if (btnOn) {
    btnOn.addEventListener("click", () => setSystemAutostart(true));
  }
  const btnOff = document.getElementById("ag-btn-autostart-off");
  if (btnOff) {
    btnOff.addEventListener("click", () => setSystemAutostart(false));
  }

  const btnAutostart = getBtnAutostart();
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
}

// =========================================================================
// TERMINAL PTY & OPENCODE / OMNIROUTE RUNNER (ORCA WORKBENCH)

export async function checkOmniRouteStatus() {
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

/**
 * Auto-preenche credenciais detectadas do OpenCode ou do OmniRoute nos inputs correspondentes
 */
export function autofillOpenCodeCredentials(credentials) {
  if (!credentials) return;

  const urlInput = document.getElementById('omniroute-url-input');
  const keyInput = document.getElementById('omniroute-key-input');
  const modelInput = document.getElementById('omniroute-model-input');

  const agUrlInput = document.getElementById('ag-omniroute-url');
  const agKeyInput = document.getElementById('ag-omniroute-key');
  const agModelInput = document.getElementById('ag-omniroute-model');

  const targetUrl = credentials.omniroute_url || credentials.baseURL || credentials.endpoint;
  const targetKey = credentials.api_key || credentials.apiKey;
  const targetModel = credentials.model;

  if (targetUrl) {
    if (urlInput) urlInput.value = targetUrl;
    if (agUrlInput) agUrlInput.value = targetUrl;
  }
  if (targetKey) {
    if (keyInput) keyInput.value = targetKey;
    if (agKeyInput) agKeyInput.value = targetKey;
  }
  if (targetModel) {
    if (modelInput) modelInput.value = targetModel;
    if (agModelInput) agModelInput.value = targetModel;
  }
}

/**
 * Renderiza a lista de conectores e modelos do OmniRoute
 */
export function renderOmniRouteConnectors(connectors) {
  const container = document.getElementById('ag-omniroute-connectors-list');
  const countBadge = document.getElementById('ag-omniroute-connectors-count');
  const tabList = document.getElementById('omniroute-connectors-list');

  const list = Array.isArray(connectors) ? connectors : [];
  if (countBadge) {
    countBadge.textContent = `${list.length} ${list.length === 1 ? 'conector' : 'conectores'}`;
    countBadge.className = list.length > 0 ? 'lw-badge active' : 'lw-badge';
  }

  const renderContent = (targetEl) => {
    if (!targetEl) return;
    targetEl.innerHTML = '';

    if (list.length === 0) {
      targetEl.innerHTML = `
        <div style="padding: 14px; text-align: center; color: var(--text-muted, #71717a); font-size: 12px; background: rgba(255,255,255,0.02); border-radius: 6px; border: 1px dashed var(--border-subtle, #27272a);">
          Nenhum conector ativo detectado. Certifique-se de que o OmniRoute está em execução.
        </div>
      `;
      return;
    }

    list.forEach(conn => {
      const card = document.createElement('div');
      card.className = 'ag-connector-card';
      card.style.cssText = 'background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border-subtle, #27272a); border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; transition: border-color 0.2s ease;';

      const isOnline = conn.status === 'online' || conn.status === 'active' || conn.online === true;
      const statusClass = isOnline ? 'online' : 'stopped';
      const statusBadge = isOnline ? 'lw-badge active' : 'lw-badge stopped';
      const statusText = isOnline ? 'Conectado' : 'Inativo';
      const latencyText = conn.latency ? `<span style="font-size: 10px; color: var(--text-muted, #a1a1aa); font-family: var(--font-mono, monospace); background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 3px;">${escapeHtml(conn.latency)}</span>` : '';

      const models = Array.isArray(conn.models) ? conn.models : [];
      const visibleModels = models.slice(0, 4);
      const remainingCount = models.length - visibleModels.length;

      let modelsHtml = visibleModels.map(m =>
        `<span style="font-size: 11px; font-family: var(--font-mono, monospace); background: rgba(255, 255, 255, 0.06); padding: 2px 6px; border-radius: 4px; color: var(--text-secondary, #d4d4d8);">${escapeHtml(m)}</span>`
      ).join('');

      if (remainingCount > 0) {
        modelsHtml += `<span style="font-size: 10px; color: var(--text-muted, #71717a); padding: 2px 4px;">+${remainingCount} mais</span>`;
      }

      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="pulse-led ${statusClass}"></span>
            <strong style="font-size: 13px; color: var(--text-primary, #f4f4f5);">${escapeHtml(conn.name || conn.provider || 'Gateway OmniRoute')}</strong>
            ${latencyText}
          </div>
          <span class="${statusBadge}">${statusText}</span>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-top: 6px;">
          <span style="font-size: 11px; color: var(--text-muted, #71717a); margin-right: 4px;">Modelos:</span>
          ${modelsHtml || '<span style="font-size: 11px; color: var(--text-muted, #71717a); font-style: italic;">Roteamento dinâmico (auto)</span>'}
        </div>
      `;
      targetEl.appendChild(card);
    });
  };

  renderContent(container);
  renderContent(tabList);
}

/**
 * Carrega a lista de conectores do OmniRoute via API REST
 */
export async function loadOmniRouteConnectors() {
  try {
    const res = await apiFetch('/api/omniroute/connectors');
    if (res.ok) {
      const data = await res.json();
      const connectors = data.connectors || (Array.isArray(data) ? data : []);
      renderOmniRouteConnectors(connectors);
      return connectors;
    }
  } catch (e) {
    // Fallback silencioso para status
  }

  try {
    const res = await apiFetch('/api/omniroute/status');
    if (res.ok) {
      const data = await res.json();
      if (data.connectors && Array.isArray(data.connectors)) {
        renderOmniRouteConnectors(data.connectors);
        return data.connectors;
      }
      if (data.online && Array.isArray(data.models) && data.models.length > 0) {
        const providerGroups = {};
        data.models.forEach(m => {
          let prov = 'OmniRoute Gateway';
          if (m.startsWith('gpt-') || m.startsWith('o1-') || m.startsWith('o3-') || m.startsWith('text-')) prov = 'OpenAI';
          else if (m.startsWith('claude-')) prov = 'Anthropic';
          else if (m.startsWith('gemini-')) prov = 'Google Gemini';
          else if (m.startsWith('deepseek-')) prov = 'DeepSeek';
          else if (m.startsWith('llama-') || m.startsWith('mixtral-')) prov = 'Meta / Groq';
          else if (m.startsWith('qwen-')) prov = 'Alibaba Qwen';
          else if (m.includes('/')) prov = m.split('/')[0].toUpperCase();

          if (!providerGroups[prov]) providerGroups[prov] = [];
          providerGroups[prov].push(m);
        });

        const derivedConnectors = Object.keys(providerGroups).map(name => ({
          name,
          provider: name.toLowerCase(),
          status: 'online',
          latency: '24ms',
          models: providerGroups[name]
        }));
        renderOmniRouteConnectors(derivedConnectors);
        return derivedConnectors;
      } else if (data.online) {
        const defaultConn = [{
          name: 'OmniRoute Universal Router',
          provider: 'omniroute',
          status: 'online',
          latency: '15ms',
          models: ['auto']
        }];
        renderOmniRouteConnectors(defaultConn);
        return defaultConn;
      } else {
        renderOmniRouteConnectors([]);
        return [];
      }
    }
  } catch (err) {
    console.warn('[OmniRoute] Erro ao carregar conectores:', err);
    renderOmniRouteConnectors([]);
  }
  return [];
}

export async function loadOmniRouteSettings() {
  const urlInput = document.getElementById('omniroute-url-input');
  const keyInput = document.getElementById('omniroute-key-input');
  const modelInput = document.getElementById('omniroute-model-input');

  const agUrlInput = document.getElementById('ag-omniroute-url');
  const agKeyInput = document.getElementById('ag-omniroute-key');
  const agModelInput = document.getElementById('ag-omniroute-model');

  try {
    const res = await apiFetch('/api/omniroute/config');
    if (res.ok) {
      const cfg = await res.json();
      autofillOpenCodeCredentials(cfg);
      if (urlInput && cfg.omniroute_url) urlInput.value = cfg.omniroute_url;
      if (keyInput && cfg.api_key) keyInput.value = cfg.api_key;
      if (modelInput && cfg.model) modelInput.value = cfg.model;
      if (agUrlInput && cfg.omniroute_url) agUrlInput.value = cfg.omniroute_url;
      if (agKeyInput && cfg.api_key) agKeyInput.value = cfg.api_key;
      if (agModelInput && cfg.model) agModelInput.value = cfg.model;
    }
  } catch (e) {
    console.warn('Erro ao carregar configurações do OmniRoute:', e);
  }

  // Tenta auto-detectar credenciais do OpenCode via rota de detecção se disponível
  try {
    const openCodeRes = await apiFetch('/api/opencode/detect');
    if (openCodeRes.ok) {
      const ocData = await openCodeRes.json();
      if (ocData && ocData.credentials) {
        autofillOpenCodeCredentials(ocData.credentials);
      }
    }
  } catch (e) {
    // Rota opcional, tratada com resiliência
  }

  checkOmniRouteStatus();
  loadOmniRouteConnectors();
}

export function initTerminalAndOmniEvents() {
  const saveHandler = async (source) => {
    const isAgModal = source === 'ag-modal';
    const urlInput = isAgModal ? document.getElementById('ag-omniroute-url') : document.getElementById('omniroute-url-input');
    const keyInput = isAgModal ? document.getElementById('ag-omniroute-key') : document.getElementById('omniroute-key-input');
    const modelInput = isAgModal ? document.getElementById('ag-omniroute-model') : document.getElementById('omniroute-model-input');
    const feedback = isAgModal ? document.getElementById('ag-omniroute-feedback') : document.getElementById('omniroute-feedback-msg');
    const btn = isAgModal ? document.getElementById('btn-ag-save-omniroute') : document.getElementById('btn-save-omniroute-config');

    const payload = {
      omniroute_url: urlInput ? urlInput.value.trim() : 'http://localhost:20128/v1',
      api_key: keyInput ? keyInput.value.trim() : 'omniroute-local',
      model: modelInput ? modelInput.value.trim() : 'auto'
    };

    try {
      if (btn) btn.textContent = 'Salvando...';
      const res = await fetch('/api/omniroute/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const result = await res.json();
      if (btn) btn.textContent = 'Salvar & Sincronizar opencode.json';

      if (result.status === 'success') {
        if (feedback) {
          feedback.style.display = 'block';
          feedback.className = isAgModal ? 'ag-feedback-msg success' : 'omniroute-feedback success';
          feedback.textContent = 'Configurações salvas! Arquivo opencode.json sincronizado com MCP do Cockpit com sucesso.';
        }
        // Sincroniza ambos os conjuntos de inputs
        autofillOpenCodeCredentials(payload);
        checkOmniRouteStatus();
        loadOmniRouteConnectors();
      } else {
        if (feedback) {
          feedback.style.display = 'block';
          feedback.className = isAgModal ? 'ag-feedback-msg error' : 'omniroute-feedback error';
          feedback.textContent = `Erro ao salvar: ${result.message || 'Falha'}`;
        }
      }
    } catch (err) {
      if (btn) btn.textContent = 'Salvar & Sincronizar opencode.json';
      if (feedback) {
        feedback.style.display = 'block';
        feedback.className = isAgModal ? 'ag-feedback-msg error' : 'omniroute-feedback error';
        feedback.textContent = `Erro de conexão: ${err.message}`;
      }
    }
  };

  const btnSaveOmni = document.getElementById('btn-save-omniroute-config');
  if (btnSaveOmni) {
    btnSaveOmni.addEventListener('click', () => saveHandler('tab-view'));
  }

  const btnAgSaveOmni = document.getElementById('btn-ag-save-omniroute');
  if (btnAgSaveOmni) {
    btnAgSaveOmni.addEventListener('click', () => saveHandler('ag-modal'));
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
        const agFeedback = document.getElementById('ag-omniroute-feedback');
        if (agFeedback) {
          agFeedback.style.display = 'block';
          agFeedback.style.background = data.online ? 'rgba(0, 255, 102, 0.1)' : 'rgba(239, 68, 68, 0.15)';
          agFeedback.style.color = data.online ? '#00ff66' : '#ef4444';
          agFeedback.textContent = data.online
            ? `OmniRoute ONLINE em ${data.endpoint}! Modelos: ${data.models ? data.models.slice(0, 4).join(', ') : ''}`
            : `OmniRoute OFFLINE: ${data.message || 'Verifique se o processo está em execução'}`;
        }
        checkOmniRouteStatus();
        loadOmniRouteConnectors();
      } catch (err) {
        btnTestOmni.textContent = 'Testar Conexão OmniRoute';
        if (feedback) {
          feedback.style.display = 'block';
          feedback.className = 'omniroute-feedback error';
          feedback.textContent = `Erro ao testar: ${err.message}`;
        }
        const agFeedback = document.getElementById('ag-omniroute-feedback');
        if (agFeedback) {
          agFeedback.style.display = 'block';
          agFeedback.style.background = 'rgba(239, 68, 68, 0.15)';
          agFeedback.style.color = '#ef4444';
          agFeedback.textContent = `Erro de conexão: ${err.message}`;
        }
      }
    });
  }
}

// =========================================================================
// GOVERNANÇA REAL & OPENCODE (ISSUE #12)
// =========================================================================

export let currentGovernance = {
  autostart_slices: false,
  security_preset: 'standard',
  human_gate_policy: 'always',
  artifact_review_policy: 'strict'
};

export async function loadGovernanceSettings() {
  try {
    const res = await apiFetch(`/api/governance?project_id=${encodeURIComponent(currentProjectId)}`);
    if (res.ok) {
      const data = await res.json();
      currentGovernance = Object.assign(currentGovernance, data);
      applyGovernanceToUI(currentGovernance);
    }
  } catch (err) {
    console.warn('[Governance] Falha ao carregar governança:', err);
  }
}

export function applyGovernanceToUI(gov) {
  if (!gov) return;
  const btnAutoOn = document.getElementById('ag-toggle-autostart-on');
  const btnAutoOff = document.getElementById('ag-toggle-autostart-off');
  if (btnAutoOn && btnAutoOff) {
    btnAutoOn.classList.toggle('active', !!gov.autostart_slices);
    btnAutoOff.classList.toggle('active', !gov.autostart_slices);
  }

  const secPreset = document.getElementById('ag-security-preset');
  if (secPreset && gov.security_preset) {
    secPreset.value = gov.security_preset;
  }

  const gatePolicy = document.getElementById('ag-gate-policy');
  if (gatePolicy && gov.human_gate_policy) {
    gatePolicy.value = gov.human_gate_policy;
  }

  const artifactPolicy = document.getElementById('ag-artifact-policy');
  if (artifactPolicy && gov.artifact_review_policy) {
    artifactPolicy.value = gov.artifact_review_policy;
  }
}

export async function saveGovernanceSetting(updates) {
  try {
    const payload = Object.assign({ project_id: currentProjectId }, updates);
    const res = await apiFetch('/api/governance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const data = await res.json();
      currentGovernance = Object.assign(currentGovernance, data);
      applyGovernanceToUI(currentGovernance);
      console.log('[Governance] Configurações de governança atualizadas com sucesso.');
    }
  } catch (err) {
    console.error('[Governance] Falha ao atualizar governança:', err);
  }
}

export function initGovernanceEvents() {
  // Autostart com o Sistema Operacional
  const btnSystemAutoOn = document.getElementById('ag-btn-autostart-on');
  const btnSystemAutoOff = document.getElementById('ag-btn-autostart-off');
  if (btnSystemAutoOn && btnSystemAutoOff) {
    btnSystemAutoOn.addEventListener('click', () => {
      setSystemAutostart(true);
    });
    btnSystemAutoOff.addEventListener('click', () => {
      setSystemAutostart(false);
    });
  }

  // Aprovação Manual de Human Gate
  const btnApproveGate = document.getElementById('btn-ag-approve-gate');
  if (btnApproveGate) {
    btnApproveGate.addEventListener('click', () => {
      approveHumanGate();
    });
  }

  // Autostart de fatias (Orquestrador)
  const btnAutoOn = document.getElementById('ag-toggle-autostart-on');
  const btnAutoOff = document.getElementById('ag-toggle-autostart-off');
  if (btnAutoOn && btnAutoOff) {
    btnAutoOn.addEventListener('click', () => {
      btnAutoOn.classList.add('active');
      btnAutoOff.classList.remove('active');
      saveGovernanceSetting({ autostart_slices: true });
    });
    btnAutoOff.addEventListener('click', () => {
      btnAutoOff.classList.add('active');
      btnAutoOn.classList.remove('active');
      saveGovernanceSetting({ autostart_slices: false });
    });
  }

  const secPreset = document.getElementById('ag-security-preset');
  if (secPreset) {
    secPreset.addEventListener('change', () => {
      saveGovernanceSetting({ security_preset: secPreset.value });
    });
  }

  const gatePolicy = document.getElementById('ag-gate-policy');
  if (gatePolicy) {
    gatePolicy.addEventListener('change', () => {
      saveGovernanceSetting({ human_gate_policy: gatePolicy.value });
    });
  }

  const artifactPolicy = document.getElementById('ag-artifact-policy');
  if (artifactPolicy) {
    artifactPolicy.addEventListener('change', () => {
      saveGovernanceSetting({ artifact_review_policy: artifactPolicy.value });
    });
  }

  // Carrega status inicial
  checkAutostartStatus();
  if (typeof state !== "undefined" && state && state.human_gates) {
    updateHumanGateUI(state.human_gates.gate_ship_approved);
  }
}

// =========================================================================
// SISTEMA DE TEMAS & TIPOGRAFIA REATIVA (ISSUE #13)
// =========================================================================

export function initThemeAndFontSettings() {
  const savedTheme = localStorage.getItem('ag_theme') || 'dark';
  const savedScale = localStorage.getItem('ag_font_scale') || '1';

  document.documentElement.setAttribute('data-theme', savedTheme);
  document.documentElement.style.setProperty('--app-font-scale', savedScale);

  const themeSelect = document.getElementById('ag-theme-select');
  if (themeSelect) {
    themeSelect.value = savedTheme;
    themeSelect.addEventListener('change', () => {
      const selected = themeSelect.value;
      document.documentElement.setAttribute('data-theme', selected);
      localStorage.setItem('ag_theme', selected);
      window.dispatchEvent(new CustomEvent('theme-changed', { detail: { theme: selected } }));
    });
  }

  const fontSelect = document.getElementById('ag-font-size-select');
  if (fontSelect) {
    fontSelect.value = savedScale;
    fontSelect.addEventListener('change', () => {
      const selected = fontSelect.value;
      document.documentElement.style.setProperty('--app-font-scale', selected);
      localStorage.setItem('ag_font_scale', selected);
    });
  }
}

// Auto-inicializa governança e temas
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initThemeAndFontSettings();
      initGovernanceEvents();
      loadGovernanceSettings();
    });
  } else {
    initThemeAndFontSettings();
    initGovernanceEvents();
    loadGovernanceSettings();
  }
}
