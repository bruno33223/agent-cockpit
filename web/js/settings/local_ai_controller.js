/**
 * Local AI Controller
 * Gestão de IA Local (Ollama), preferências de hardware, limites de workers e circuit breaker.
 */

import { apiFetch, currentProjectId } from '../state.js';

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
}
