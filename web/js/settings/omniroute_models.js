/**
 * OmniRoute Models Controller
 * Catálogo de modelos vivos, seleção de modelo ativo e sincronização de configurações.
 */

import { apiFetch } from '../state.js';
import { showToast } from '../ui_utils.js';
import { autofillOpenCodeCredentials, checkOmniRouteDaemon, loadOmniRouteConnectors } from './omniroute_connectors.js';
import { loadOmniRouteAccounts } from './omniroute_accounts.js';

export let omniRouteModels = [];
export let omniRouteActiveModel = 'auto';

export async function loadOmniRouteModels() {
  const countBadge = document.getElementById('ag-omniroute-models-count');
  try {
    const res = await apiFetch('/api/omniroute/models');
    if (res.ok) {
      const data = await res.json();
      omniRouteModels = Array.isArray(data.models) ? data.models : [];
      if (data.active_model) omniRouteActiveModel = data.active_model;
      if (countBadge) {
        countBadge.textContent = `${omniRouteModels.length} ${omniRouteModels.length === 1 ? 'modelo disponível' : 'modelos disponíveis'}`;
        countBadge.className = omniRouteModels.length > 0 ? 'lw-badge active' : 'lw-badge';
      }
      const searchInput = document.getElementById('ag-omniroute-model-search');
      renderOmniRouteModels(searchInput ? searchInput.value.trim() : '');
      return omniRouteModels;
    }
  } catch (err) {
    console.warn('[OmniRoute] Falha ao carregar catálogo de modelos:', err);
  }
  renderOmniRouteModels();
  return [];
}

export function renderOmniRouteModels(filterQuery = '') {
  const selectEl = document.getElementById('ag-omniroute-active-model-select');
  if (!selectEl) return;

  const q = (filterQuery || '').toLowerCase().trim();
  const list = Array.isArray(omniRouteModels) ? omniRouteModels : [];
  const filtered = list.filter(m => !q || m.toLowerCase().includes(q));

  selectEl.innerHTML = '';
  const autoOpt = document.createElement('option');
  autoOpt.value = 'auto';
  autoOpt.textContent = 'auto (Roteamento Automático OmniRoute)';
  if (omniRouteActiveModel === 'auto') autoOpt.selected = true;
  selectEl.appendChild(autoOpt);

  const groups = {};
  filtered.forEach(m => {
    if (m === 'auto') return;
    let group = 'Outros Modelos';
    if (m.startsWith('auto/')) group = 'OmniRoute Auto Routing';
    else if (m.includes('/')) group = m.split('/')[0].toUpperCase();
    else if (m.startsWith('gpt-') || m.startsWith('o1-') || m.startsWith('o3-')) group = 'OpenAI';
    else if (m.startsWith('claude-')) group = 'Anthropic';
    else if (m.startsWith('gemini-')) group = 'Google Gemini';
    else if (m.startsWith('deepseek-')) group = 'DeepSeek';
    else if (m.startsWith('llama-') || m.startsWith('mixtral-')) group = 'Meta / Groq';
    else if (m.startsWith('qwen-')) group = 'Alibaba Qwen';

    if (!groups[group]) groups[group] = [];
    groups[group].push(m);
  });

  const sortedGroups = Object.keys(groups).sort((a, b) => {
    if (a.includes('Auto Routing')) return -1;
    if (b.includes('Auto Routing')) return 1;
    return a.localeCompare(b);
  });

  sortedGroups.forEach(groupName => {
    const optGroup = document.createElement('optgroup');
    optGroup.label = groupName;
    groups[groupName].forEach(modelName => {
      const opt = document.createElement('option');
      opt.value = modelName;
      opt.textContent = modelName;
      if (modelName === omniRouteActiveModel) opt.selected = true;
      optGroup.appendChild(opt);
    });
    selectEl.appendChild(optGroup);
  });

  if (omniRouteActiveModel && omniRouteActiveModel !== 'auto' && !filtered.includes(omniRouteActiveModel)) {
    const activeOpt = document.createElement('option');
    activeOpt.value = omniRouteActiveModel;
    activeOpt.textContent = `${omniRouteActiveModel} (Ativo)`;
    activeOpt.selected = true;
    selectEl.insertBefore(activeOpt, selectEl.children[1] || null);
  }

  if (list.length === 0 || (list.length === 1 && list[0] === 'auto')) {
    const hintOpt = document.createElement('option');
    hintOpt.value = '';
    hintOpt.disabled = true;
    hintOpt.textContent = '(Nenhum modelo conectado no OmniRoute - Inicie o daemon ou conecte contas)';
    selectEl.appendChild(hintOpt);
  }
}

export async function applyOmniRouteActiveModel() {
  const selectEl = document.getElementById('ag-omniroute-active-model-select');
  const btnApply = document.getElementById('btn-ag-apply-model');
  const feedback = document.getElementById('ag-omniroute-model-feedback');
  const selectedModel = selectEl ? selectEl.value : 'auto';

  try {
    if (btnApply) { btnApply.disabled = true; btnApply.textContent = 'Aplicando...'; }
    const currentUrl = document.getElementById('ag-omniroute-url')?.value || 'http://localhost:20128/v1';
    const currentKey = document.getElementById('ag-omniroute-key')?.value || 'omniroute-local';

    const res = await apiFetch('/api/omniroute/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: selectedModel,
        omniroute_url: currentUrl,
        api_key: currentKey
      })
    });
    const data = await res.json();
    if (data.status === 'success') {
      omniRouteActiveModel = selectedModel;
      const agModelInput = document.getElementById('ag-omniroute-model');
      const omniModelInput = document.getElementById('omniroute-model-input');
      if (agModelInput) agModelInput.value = selectedModel;
      if (omniModelInput) omniModelInput.value = selectedModel;

      showToast(`Modelo ativo definido como "${selectedModel}"!`, 'success');
      if (feedback) {
        feedback.style.display = 'block';
        feedback.className = 'ag-feedback-msg success';
        feedback.textContent = `Modelo ativo definido como "${selectedModel}" e sincronizado no opencode.json!`;
        setTimeout(() => { feedback.style.display = 'none'; }, 4000);
      }
    } else {
      showToast(`Erro ao aplicar modelo: ${data.message || 'Falha'}`, 'error');
    }
  } catch (err) {
    showToast(`Erro de conexão: ${err.message}`, 'error');
  } finally {
    if (btnApply) {
      btnApply.disabled = false;
      btnApply.textContent = 'Aplicar Modelo Ativo';
    }
  }
}

export async function loadOmniRouteSettings() {
  const setVal = (ids, val) => {
    if (!val) return;
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = val;
    });
  };

  try {
    const res = await apiFetch('/api/omniroute/config');
    if (res.ok) {
      const cfg = await res.json();
      autofillOpenCodeCredentials(cfg);
      setVal(['omniroute-url-input', 'ag-omniroute-url'], cfg.omniroute_url);
      setVal(['omniroute-key-input', 'ag-omniroute-key'], cfg.api_key);
      setVal(['omniroute-model-input', 'ag-omniroute-model'], cfg.model);
      if (cfg.model) omniRouteActiveModel = cfg.model;
    }
  } catch (e) {
    console.warn('Erro ao carregar configurações do OmniRoute:', e);
  }

  try {
    const openCodeRes = await apiFetch('/api/opencode/detect');
    if (openCodeRes.ok) {
      const ocData = await openCodeRes.json();
      if (ocData?.credentials) autofillOpenCodeCredentials(ocData.credentials);
    }
  } catch (_) {}

  await Promise.allSettled([
    checkOmniRouteDaemon(),
    loadOmniRouteAccounts(),
    loadOmniRouteModels(),
    loadOmniRouteConnectors()
  ]);
}
