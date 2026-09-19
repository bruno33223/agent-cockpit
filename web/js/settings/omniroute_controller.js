/**
 * OmniRoute Controller
 * Fachada e orquestrador central de OmniRoute (conectores, contas, modelos e eventos).
 */

import { apiFetch } from '../state.js';
import { showToast } from '../ui_utils.js';

export * from './omniroute_connectors.js';
export * from './omniroute_oauth.js';
export * from './omniroute_accounts.js';
export * from './omniroute_models.js';

import {
  checkOmniRouteStatus,
  checkOmniRouteDaemon,
  startOmniRouteDaemonUI,
  loadOmniRouteConnectors,
  autofillOpenCodeCredentials
} from './omniroute_connectors.js';

import {
  switchOmniRouteModalTab
} from './omniroute_oauth.js';

import {
  openOmniRouteAccountModal,
  closeOmniRouteAccountModal,
  saveOmniRouteAccount,
  loadOmniRouteAccounts
} from './omniroute_accounts.js';

import {
  loadOmniRouteModels,
  renderOmniRouteModels,
  applyOmniRouteActiveModel
} from './omniroute_models.js';

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
      const res = await apiFetch('/api/omniroute/config', {
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
          feedback.textContent = 'Configurações salvas! Arquivo opencode.json sincronizado com sucesso.';
        }
        showToast('Configurações salvas e opencode.json sincronizado!', 'success');
        autofillOpenCodeCredentials(payload);
        checkOmniRouteDaemon();
        loadOmniRouteAccounts();
        loadOmniRouteModels();
      } else {
        if (feedback) {
          feedback.style.display = 'block';
          feedback.className = isAgModal ? 'ag-feedback-msg error' : 'omniroute-feedback error';
          feedback.textContent = `Erro ao salvar: ${result.message || 'Falha'}`;
        }
        showToast(`Erro ao salvar: ${result.message || 'Falha'}`, 'error');
      }
    } catch (err) {
      if (btn) btn.textContent = 'Salvar & Sincronizar opencode.json';
      if (feedback) {
        feedback.style.display = 'block';
        feedback.className = isAgModal ? 'ag-feedback-msg error' : 'omniroute-feedback error';
        feedback.textContent = `Erro de conexão: ${err.message}`;
      }
      showToast(`Erro de conexão: ${err.message}`, 'error');
    }
  };

  document.getElementById('btn-save-omniroute-config')?.addEventListener('click', () => saveHandler('tab-view'));
  document.getElementById('btn-ag-save-omniroute')?.addEventListener('click', () => saveHandler('ag-modal'));

  document.getElementById('btn-test-omniroute')?.addEventListener('click', async () => {
    const btnTestOmni = document.getElementById('btn-test-omniroute');
    const urlInput = document.getElementById('omniroute-url-input');
    const feedback = document.getElementById('omniroute-feedback-msg');
    const targetUrl = urlInput ? urlInput.value.trim() : 'http://localhost:20128/v1';

    try {
      if (btnTestOmni) btnTestOmni.textContent = 'Testando...';
      const res = await apiFetch(`/api/omniroute/status?base_url=${encodeURIComponent(targetUrl)}`);
      const data = await res.json();
      if (btnTestOmni) btnTestOmni.textContent = 'Testar Conexão OmniRoute';

      if (feedback) {
        feedback.style.display = 'block';
        if (data.online) {
          feedback.className = 'omniroute-feedback success';
          feedback.textContent = `OmniRoute ONLINE em ${data.endpoint}! Modelos detectados: ${data.models ? data.models.length : 0}`;
        } else {
          feedback.className = 'omniroute-feedback error';
          feedback.textContent = `OmniRoute OFFLINE: ${data.message}`;
        }
      }
      checkOmniRouteDaemon();
    } catch (err) {
      if (btnTestOmni) btnTestOmni.textContent = 'Testar Conexão OmniRoute';
      if (feedback) {
        feedback.style.display = 'block';
        feedback.className = 'omniroute-feedback error';
        feedback.textContent = `Erro ao testar: ${err.message}`;
      }
    }
  });

  document.getElementById('btn-ag-test-omniroute')?.addEventListener('click', async () => {
    const btnAgTestOmni = document.getElementById('btn-ag-test-omniroute');
    const urlInput = document.getElementById('ag-omniroute-url');
    const feedback = document.getElementById('ag-omniroute-feedback');
    const targetUrl = urlInput ? urlInput.value.trim() : 'http://localhost:20128/v1';

    try {
      if (btnAgTestOmni) {
        btnAgTestOmni.textContent = 'Testando...';
        btnAgTestOmni.disabled = true;
      }
      const res = await apiFetch(`/api/omniroute/status?base_url=${encodeURIComponent(targetUrl)}`);
      const data = await res.json();

      if (feedback) {
        feedback.style.display = 'block';
        if (data.online) {
          feedback.className = 'ag-feedback-msg success';
          feedback.textContent = `OmniRoute ONLINE em ${data.endpoint}! (${data.models ? data.models.length : 0} modelos)`;
          showToast(`OmniRoute ONLINE (${data.models ? data.models.length : 0} modelos)`, 'success');
        } else {
          feedback.className = 'ag-feedback-msg error';
          feedback.textContent = `OmniRoute OFFLINE: ${data.message || 'Verifique se o processo está em execução'}`;
          showToast('OmniRoute OFFLINE', 'error');
        }
      }
      checkOmniRouteDaemon();
      loadOmniRouteAccounts();
      loadOmniRouteModels();
    } catch (err) {
      if (feedback) {
        feedback.style.display = 'block';
        feedback.className = 'ag-feedback-msg error';
        feedback.textContent = `Erro de conexão: ${err.message}`;
      }
      showToast(`Erro de conexão: ${err.message}`, 'error');
    } finally {
      if (btnAgTestOmni) {
        btnAgTestOmni.textContent = 'Testar Conexão OmniRoute';
        btnAgTestOmni.disabled = false;
      }
    }
  });

  document.getElementById('btn-omni-refresh-status')?.addEventListener('click', async () => {
    await checkOmniRouteDaemon();
    await loadOmniRouteAccounts();
    await loadOmniRouteModels();
    showToast('Status do OmniRoute atualizado!', 'info');
  });

  document.getElementById('btn-omni-start-daemon')?.addEventListener('click', startOmniRouteDaemonUI);
  document.getElementById('tab-omni-direct')?.addEventListener('click', () => switchOmniRouteModalTab('direct'));
  document.getElementById('tab-omni-apikey')?.addEventListener('click', () => switchOmniRouteModalTab('apikey'));
  document.getElementById('btn-add-omniroute-account')?.addEventListener('click', openOmniRouteAccountModal);

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('#btn-add-omniroute-account, #btn-empty-add-account, [data-action="open-omniroute-account-modal"]');
    if (btn) {
      e.preventDefault();
      openOmniRouteAccountModal();
    }
  });

  document.getElementById('btn-close-omni-account-modal')?.addEventListener('click', closeOmniRouteAccountModal);
  document.getElementById('btn-cancel-omni-account')?.addEventListener('click', closeOmniRouteAccountModal);
  document.getElementById('btn-save-omni-account')?.addEventListener('click', saveOmniRouteAccount);

  const btnToggleKeyVis = document.getElementById('btn-omni-toggle-key-vis');
  const keyInput = document.getElementById('omni-account-key');
  if (btnToggleKeyVis && keyInput) {
    btnToggleKeyVis.addEventListener('click', () => {
      keyInput.type = keyInput.type === 'password' ? 'text' : 'password';
    });
  }

  const modalAccount = document.getElementById('modal-omniroute-account');
  if (modalAccount) {
    modalAccount.addEventListener('click', (e) => {
      if (e.target === modalAccount) closeOmniRouteAccountModal();
    });
  }

  document.getElementById('btn-ag-apply-model')?.addEventListener('click', applyOmniRouteActiveModel);
  document.getElementById('ag-omniroute-model-search')?.addEventListener('input', (e) => {
    renderOmniRouteModels(e.target.value);
  });

  window.addEventListener('omniroute-account-connected', () => {
    loadOmniRouteAccounts();
    loadOmniRouteModels();
  });
  window.addEventListener('omniroute-daemon-started', () => {
    loadOmniRouteAccounts();
    loadOmniRouteModels();
    loadOmniRouteConnectors();
  });
}
