/**
 * OmniRoute Accounts Controller
 * Gestão de contas de provedores, teste de conexão, remoção e modal de cadastro.
 */

import { apiFetch } from '../state.js';
import { escapeHtml, showToast } from '../ui_utils.js';
import { renderOmniRouteDirectCards, switchOmniRouteModalTab } from './omniroute_oauth.js';

export const POPULAR_PROVIDERS = [
  { id: 'openai', name: 'OpenAI', icon: '🤖', defaultModel: 'gpt-4o', placeholderKey: 'sk-proj-...', needsBaseUrl: false },
  { id: 'anthropic', name: 'Anthropic', icon: '🧠', defaultModel: 'claude-3-5-sonnet-20241022', placeholderKey: 'sk-ant-...', needsBaseUrl: false },
  { id: 'gemini', name: 'Google Gemini', icon: '💎', defaultModel: 'gemini-1.5-pro', placeholderKey: 'AIzaSy...', needsBaseUrl: false },
  { id: 'groq', name: 'Groq', icon: '⚡', defaultModel: 'llama-3.3-70b-versatile', placeholderKey: 'gsk_...', needsBaseUrl: false },
  { id: 'openrouter', name: 'OpenRouter', icon: '🌐', defaultModel: 'auto', placeholderKey: 'sk-or-v1-...', needsBaseUrl: false },
  { id: 'mistral', name: 'Mistral AI', icon: '🌪️', defaultModel: 'mistral-large-latest', placeholderKey: '...', needsBaseUrl: false },
  { id: 'deepseek', name: 'DeepSeek', icon: '🐋', defaultModel: 'deepseek-chat', placeholderKey: 'sk-...', needsBaseUrl: false },
  { id: 'ollama', name: 'Ollama (Local)', icon: '🦙', defaultModel: 'llama3.2:latest', placeholderKey: 'opcional', needsBaseUrl: true, defaultUrl: 'http://localhost:11434/v1' },
  { id: 'custom', name: 'Personalizado (OpenAI-Compatible)', icon: '⚙️', defaultModel: '', placeholderKey: 'chave ou token', needsBaseUrl: true, defaultUrl: 'https://api.exemplo.com/v1' }
];

export let omniRouteAccounts = [];

export async function loadOmniRouteAccounts() {
  const countBadge = document.getElementById('ag-omniroute-accounts-count');
  try {
    const res = await apiFetch('/api/omniroute/accounts');
    if (res.ok) {
      const data = await res.json();
      omniRouteAccounts = Array.isArray(data.accounts) ? data.accounts : [];
      if (countBadge) {
        countBadge.textContent = `${omniRouteAccounts.length} ${omniRouteAccounts.length === 1 ? 'conta' : 'contas'}`;
        countBadge.className = omniRouteAccounts.length > 0 ? 'lw-badge active' : 'lw-badge';
      }
      renderOmniRouteAccounts(omniRouteAccounts);
      return omniRouteAccounts;
    }
  } catch (err) {
    console.warn('[OmniRoute] Falha ao carregar contas:', err);
  }
  renderOmniRouteAccounts([]);
  return [];
}

export function renderOmniRouteAccounts(accounts) {
  const container = document.getElementById('ag-omniroute-accounts-list');
  if (!container) return;
  container.innerHTML = '';
  const list = Array.isArray(accounts) ? accounts : [];

  if (list.length === 0) {
    container.innerHTML = `
      <div class="ag-omni-empty-accounts">
        <strong style="color: var(--text-primary); font-size: 13px;">Nenhuma conta de provedor conectada</strong>
        <p style="color: var(--text-muted); font-size: 12px; margin: 4px 0 8px 0;">Conecte contas (OpenAI, Anthropic, Gemini, Groq, Ollama...) para habilitar o roteamento.</p>
        <button class="btn btn-primary btn-sm" id="btn-empty-add-account">Conectar Primeira Conta</button>
      </div>
    `;
    document.getElementById('btn-empty-add-account')?.addEventListener('click', openOmniRouteAccountModal);
    return;
  }

  list.forEach(acc => {
    const card = document.createElement('div');
    card.className = 'ag-omni-account-card';
    const provInfo = POPULAR_PROVIDERS.find(p => p.id === acc.provider);
    const icon = provInfo ? provInfo.icon : '⚡';
    const provDisplayName = provInfo ? provInfo.name : (acc.provider ? acc.provider.toUpperCase() : 'Provedor');
    const isActive = acc.isActive !== false;
    const testStatus = acc.testStatus || 'unknown';

    let testStatusBadge = '<span class="lw-badge" style="font-size: 10px; opacity: 0.7;">Não testado</span>';
    if (testStatus === 'success') testStatusBadge = '<span class="lw-badge active" style="font-size: 10px;">Conexão OK</span>';
    else if (testStatus === 'error' || testStatus === 'failed') testStatusBadge = '<span class="lw-badge stopped" style="font-size: 10px;">Falha</span>';

    card.innerHTML = `
      <div class="ag-omni-account-header">
        <div class="ag-omni-account-title-wrap">
          <div class="ag-omni-account-icon">${icon}</div>
          <div>
            <div class="ag-omni-account-name">${escapeHtml(acc.name || provDisplayName)}</div>
            <div class="ag-omni-account-provider-tag">${escapeHtml(provDisplayName)}</div>
          </div>
        </div>
        <span class="lw-badge ${isActive ? 'active' : 'stopped'}">${isActive ? 'Ativo' : 'Inativo'}</span>
      </div>
      <div class="ag-omni-account-body">
        <div style="display: flex; justify-content: space-between;"><span style="color: var(--text-muted);">Modelo padrão:</span><span style="font-family: monospace; font-size: 11px;">${escapeHtml(acc.defaultModel || 'auto')}</span></div>
        <div style="display: flex; justify-content: space-between;"><span style="color: var(--text-muted);">Autenticação:</span><span style="font-size: 11px;">${escapeHtml(acc.authType || 'API Key')}</span></div>
        <div style="display: flex; justify-content: space-between;"><span style="color: var(--text-muted);">Validação:</span>${testStatusBadge}</div>
      </div>
      <div class="ag-omni-account-footer">
        <button class="action-btn secondary btn-sm btn-omni-test-acc" data-id="${escapeHtml(acc.id)}" data-name="${escapeHtml(acc.name || provDisplayName)}">Testar</button>
        <button class="action-btn danger btn-sm btn-omni-delete-acc" data-id="${escapeHtml(acc.id)}" data-name="${escapeHtml(acc.name || provDisplayName)}">Remover</button>
      </div>
    `;
    container.appendChild(card);
  });

  container.querySelectorAll('.btn-omni-test-acc').forEach(btn => {
    btn.addEventListener('click', () => testOmniRouteAccount(btn.dataset.id, btn));
  });
  container.querySelectorAll('.btn-omni-delete-acc').forEach(btn => {
    btn.addEventListener('click', () => deleteOmniRouteAccount(btn.dataset.id, btn.dataset.name));
  });
}

export async function testOmniRouteAccount(accountId, btnEl) {
  if (!accountId) return;
  const originalText = btnEl ? btnEl.innerHTML : '';
  try {
    if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Testando...'; }
    const res = await apiFetch(`/api/omniroute/accounts/${encodeURIComponent(accountId)}/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.valid) {
      showToast(`Conexão validada com sucesso! ${data.message || ''}`, 'success');
    } else {
      showToast(`Falha no teste da conta: ${data.message || 'Erro desconhecido'}`, 'error');
    }
    await loadOmniRouteAccounts();
  } catch (err) {
    showToast(`Erro ao testar conta: ${err.message}`, 'error');
  } finally {
    if (btnEl) { btnEl.disabled = false; btnEl.innerHTML = originalText; }
  }
}

export async function deleteOmniRouteAccount(accountId, accountName) {
  if (!accountId) return;
  const nameDisplay = accountName || accountId;
  if (typeof confirm === 'function' && !confirm(`Deseja realmente remover a conta "${nameDisplay}" do OmniRoute?`)) return;
  try {
    const res = await apiFetch(`/api/omniroute/accounts/${encodeURIComponent(accountId)}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(`Conta "${nameDisplay}" removida com sucesso!`, 'info');
      await loadOmniRouteAccounts();
      window.dispatchEvent(new CustomEvent('omniroute-account-deleted'));
    }
  } catch (err) {
    showToast(`Erro de comunicação: ${err.message}`, 'error');
  }
}

export function openOmniRouteAccountModal() {
  const modal = document.getElementById('modal-omniroute-account');
  if (!modal) return;

  const feedback = document.getElementById('modal-omni-account-feedback');
  if (feedback) { feedback.style.display = 'none'; feedback.textContent = ''; }
  const actionBox = document.getElementById('omni-direct-action-box');
  if (actionBox) actionBox.style.display = 'none';

  const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
  setVal('omni-account-name', '');
  const keyInput = document.getElementById('omni-account-key');
  if (keyInput) { keyInput.value = ''; keyInput.type = 'password'; }
  setVal('omni-account-baseurl', '');
  setVal('omni-account-default-model', '');

  const pillsContainer = document.getElementById('ag-omni-provider-pills');
  if (pillsContainer) {
    pillsContainer.innerHTML = POPULAR_PROVIDERS.map((p, idx) => `
      <button type="button" class="ag-omni-provider-pill ${idx === 0 ? 'active' : ''}" data-provider="${p.id}">
        <span>${p.icon}</span>
        <span>${escapeHtml(p.name)}</span>
      </button>
    `).join('');

    pillsContainer.querySelectorAll('.ag-omni-provider-pill').forEach(pill => {
      pill.addEventListener('click', () => selectOmniRouteProviderPill(pill.dataset.provider));
    });
  }

  renderOmniRouteDirectCards();
  switchOmniRouteModalTab('direct');
  selectOmniRouteProviderPill('openai');

  modal.classList.add('active');
  modal.style.display = 'flex';
}

export function closeOmniRouteAccountModal() {
  const modal = document.getElementById('modal-omniroute-account');
  if (modal) {
    modal.classList.remove('active');
    modal.style.display = 'none';
  }
}

export function selectOmniRouteProviderPill(providerId) {
  const pillsContainer = document.getElementById('ag-omni-provider-pills');
  if (pillsContainer) {
    pillsContainer.querySelectorAll('.ag-omni-provider-pill').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.provider === providerId);
    });
  }

  const hiddenInput = document.getElementById('omni-account-provider-id');
  if (hiddenInput) hiddenInput.value = providerId;

  const prov = POPULAR_PROVIDERS.find(p => p.id === providerId) || { id: providerId, name: providerId, defaultModel: '', placeholderKey: 'sk-...', needsBaseUrl: false };
  const nameInput = document.getElementById('omni-account-name');
  const keyInput = document.getElementById('omni-account-key');
  const keyGroup = document.getElementById('omni-account-key-group');
  const baseUrlInput = document.getElementById('omni-account-baseurl');
  const baseUrlGroup = document.getElementById('omni-account-baseurl-group');
  const defaultModelInput = document.getElementById('omni-account-default-model');

  if (nameInput && (!nameInput.value || POPULAR_PROVIDERS.some(p => p.name === nameInput.value))) nameInput.value = prov.name;
  if (keyInput) keyInput.placeholder = prov.placeholderKey || 'sk-...';
  if (defaultModelInput && !defaultModelInput.value) defaultModelInput.value = prov.defaultModel || '';

  if (baseUrlGroup) {
    baseUrlGroup.style.display = prov.needsBaseUrl ? 'block' : 'none';
    if (prov.needsBaseUrl && baseUrlInput && !baseUrlInput.value) baseUrlInput.value = prov.defaultUrl || '';
  }
  if (keyGroup) {
    keyGroup.style.display = providerId === 'ollama' ? 'none' : 'block';
  }
}

export async function saveOmniRouteAccount() {
  const providerId = document.getElementById('omni-account-provider-id')?.value || 'openai';
  const name = document.getElementById('omni-account-name')?.value?.trim() || '';
  const apiKey = document.getElementById('omni-account-key')?.value?.trim() || '';
  const baseUrl = document.getElementById('omni-account-baseurl')?.value?.trim() || '';
  const defaultModel = document.getElementById('omni-account-default-model')?.value?.trim() || '';
  const feedback = document.getElementById('modal-omni-account-feedback');
  const btnSave = document.getElementById('btn-save-omni-account');
  const prov = POPULAR_PROVIDERS.find(p => p.id === providerId);

  if (!name) {
    if (feedback) {
      feedback.style.display = 'block';
      feedback.className = 'ag-feedback-msg error';
      feedback.textContent = 'Por favor, informe um nome ou identificador para a conta.';
    }
    return;
  }
  if (providerId !== 'ollama' && !apiKey) {
    if (feedback) {
      feedback.style.display = 'block';
      feedback.className = 'ag-feedback-msg error';
      feedback.textContent = 'A chave de API (API Key) é obrigatória para este provedor.';
    }
    return;
  }
  if (prov?.needsBaseUrl && !baseUrl) {
    if (feedback) {
      feedback.style.display = 'block';
      feedback.className = 'ag-feedback-msg error';
      feedback.textContent = 'O endpoint Base URL é obrigatório para provedores locais ou personalizados.';
    }
    return;
  }

  const payload = { provider: providerId, name, api_key: apiKey || undefined, default_model: defaultModel || undefined, url: baseUrl || undefined };
  try {
    if (btnSave) { btnSave.disabled = true; btnSave.textContent = 'Conectando...'; }
    const res = await apiFetch('/api/omniroute/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(`Conta "${name}" conectada com sucesso!`, 'success');
      closeOmniRouteAccountModal();
      await loadOmniRouteAccounts();
      window.dispatchEvent(new CustomEvent('omniroute-account-connected'));
    } else if (feedback) {
      feedback.style.display = 'block';
      feedback.textContent = `Erro: ${data.message || 'Falha'}`;
    }
  } catch (err) {
    if (feedback) { feedback.style.display = 'block'; feedback.textContent = `Erro: ${err.message}`; }
  } finally {
    if (btnSave) { btnSave.disabled = false; btnSave.textContent = 'Conectar Conta'; }
  }
}
