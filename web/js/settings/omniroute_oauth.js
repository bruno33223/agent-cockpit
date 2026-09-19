/**
 * OmniRoute OAuth & Direct Connection Controller
 * Fluxos de autenticação sem chave: Browser OAuth, Device Code e Importação Local.
 */

import { apiFetch } from '../state.js';
import { escapeHtml, showToast } from '../ui_utils.js';

export const DIRECT_OAUTH_PROVIDERS = [
  {
    id: 'antigravity',
    name: 'Google Antigravity / Gemini',
    flow: 'browser',
    badge: 'Sem Chave • OAuth',
    badgeClass: '',
    icon: '🌐',
    desc: 'Login direto com Google no navegador. Acessa Gemini 2.5 Flash, Pro e modelos Claude integrados sem digitar chave.',
    btnLabel: 'Conectar Conta Google'
  },
  {
    id: 'claude-code',
    name: 'Anthropic Claude Code',
    flow: 'browser',
    badge: 'Sem Chave • OAuth',
    badgeClass: '',
    icon: '🤖',
    desc: 'Autenticação oficial via navegador com sua conta Anthropic Claude Code.',
    btnLabel: 'Conectar Claude Code'
  },
  {
    id: 'copilot',
    name: 'GitHub Copilot',
    flow: 'device',
    badge: 'Device Code',
    badgeClass: 'device',
    icon: '🐙',
    desc: 'Gera código de 8 dígitos para aprovar em github.com/login/device sem expor credenciais.',
    btnLabel: 'Gerar Device Code'
  },
  {
    id: 'cursor',
    name: 'Cursor IDE (Local)',
    flow: 'import',
    badge: 'Importação Local',
    badgeClass: 'import',
    icon: '💻',
    desc: 'Detecta e importa a sessão de login já configurada no Cursor instalado nesta máquina.',
    btnLabel: 'Importar do Cursor'
  },
  {
    id: 'codex',
    name: 'OpenAI Codex',
    flow: 'device',
    badge: 'Device Flow',
    badgeClass: 'device',
    icon: '⚡',
    desc: 'Conexão direta via ChatGPT / OpenAI com fluxo seguro.',
    btnLabel: 'Conectar OpenAI Codex'
  },
  {
    id: 'zed',
    name: 'Zed IDE (Local)',
    flow: 'import',
    badge: 'Importação Local',
    badgeClass: 'import',
    icon: '📝',
    desc: 'Importa credenciais locais armazenadas no chaveiro da máquina configuradas pelo Zed IDE.',
    btnLabel: 'Importar do Zed'
  }
];

let currentOAuthSession = null;

export function switchOmniRouteModalTab(tabMode) {
  const tabDirect = document.getElementById('tab-omni-direct');
  const tabApiKey = document.getElementById('tab-omni-apikey');
  const panelDirect = document.getElementById('omni-panel-direct');
  const panelApiKey = document.getElementById('omni-panel-apikey');
  const btnSave = document.getElementById('btn-save-omni-account');

  const isDirect = tabMode === 'direct';
  if (tabDirect) {
    tabDirect.classList.toggle('active', isDirect);
    tabDirect.style.borderBottomColor = isDirect ? 'var(--color-brand, #38bdf8)' : 'transparent';
    tabDirect.style.color = isDirect ? 'var(--text-primary)' : 'var(--text-secondary)';
    tabDirect.style.fontWeight = isDirect ? '600' : '500';
  }
  if (tabApiKey) {
    tabApiKey.classList.toggle('active', !isDirect);
    tabApiKey.style.borderBottomColor = !isDirect ? 'var(--color-brand, #38bdf8)' : 'transparent';
    tabApiKey.style.color = !isDirect ? 'var(--text-primary)' : 'var(--text-secondary)';
    tabApiKey.style.fontWeight = !isDirect ? '600' : '500';
  }
  if (panelDirect) panelDirect.style.display = isDirect ? 'flex' : 'none';
  if (panelApiKey) panelApiKey.style.display = !isDirect ? 'flex' : 'none';
  if (btnSave) btnSave.style.display = !isDirect ? 'inline-flex' : 'none';
}

export function renderOmniRouteDirectCards() {
  const container = document.getElementById('ag-omni-direct-cards');
  if (!container) return;

  container.innerHTML = DIRECT_OAUTH_PROVIDERS.map(p => `
    <div class="omni-direct-card" data-direct-provider="${p.id}">
      <div class="omni-direct-card-header">
        <div class="omni-direct-card-title">
          <span>${p.icon}</span>
          <span>${escapeHtml(p.name)}</span>
        </div>
        <span class="omni-direct-badge ${p.badgeClass}">${p.badge}</span>
      </div>
      <p class="omni-direct-card-desc">${escapeHtml(p.desc)}</p>
      <button type="button" class="btn btn-primary btn-sm omni-direct-card-btn" data-direct-action="${p.id}">
        ${escapeHtml(p.btnLabel)}
      </button>
    </div>
  `).join('');

  container.querySelectorAll('[data-direct-action]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      handleOmniDirectSelect(btn.dataset.directAction);
    });
  });

  container.querySelectorAll('.omni-direct-card').forEach(card => {
    card.addEventListener('click', () => {
      handleOmniDirectSelect(card.dataset.directProvider);
    });
  });
}

export async function handleOmniDirectSelect(providerId) {
  const p = DIRECT_OAUTH_PROVIDERS.find(item => item.id === providerId);
  if (!p) return;

  document.querySelectorAll('.omni-direct-card').forEach(c => {
    c.classList.toggle('selected', c.dataset.directProvider === providerId);
  });

  const actionBox = document.getElementById('omni-direct-action-box');
  const actionContent = document.getElementById('omni-direct-action-content');
  if (!actionBox || !actionContent) return;

  actionBox.style.display = 'flex';
  actionContent.innerHTML = `<div style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-secondary);"><span class="loading-spinner" style="width: 14px; height: 14px;"></span><span>Preparando conexão com ${escapeHtml(p.name)}...</span></div>`;

  if (p.flow === 'import') {
    actionContent.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <strong style="font-size: 13px; color: var(--text-primary);">Importar Sessão Local: ${escapeHtml(p.name)}</strong>
        <p style="margin: 0; font-size: 12px; color: var(--text-secondary);">O OmniRoute buscará automaticamente as credenciais salvas no seu sistema operacional.</p>
        <button type="button" class="btn btn-primary btn-sm" id="btn-run-local-import" style="align-self: flex-start;">🚀 Confirmar Importação Local</button>
      </div>
    `;
    document.getElementById('btn-run-local-import')?.addEventListener('click', async () => {
      try {
        const res = await apiFetch('/api/omniroute/oauth/import-local', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: p.id })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          showToast(data.message || 'Conta importada com sucesso!', 'success');
          window.dispatchEvent(new CustomEvent('omniroute-account-connected'));
          const modal = document.getElementById('modal-omniroute-account');
          if (modal) modal.style.display = 'none';
        } else {
          actionContent.innerHTML = `<div style="color: var(--color-danger, #ef4444); font-size: 12px;">⚠️ ${escapeHtml(data.message || 'Falha ao importar sessão.')}</div>`;
        }
      } catch (err) {
        actionContent.innerHTML = `<div style="color: var(--color-danger, #ef4444); font-size: 12px;">⚠️ Erro: ${escapeHtml(err.message)}</div>`;
      }
    });
    return;
  }

  try {
    const res = await apiFetch('/api/omniroute/oauth/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: p.id })
    });
    const data = await res.json();
    if (data.status !== 'ok') {
      actionContent.innerHTML = `<div style="color: var(--color-danger, #ef4444); font-size: 12px;">⚠️ ${escapeHtml(data.message || 'Erro ao iniciar autorização.')}</div>`;
      return;
    }

    if (data.flow === 'browser') {
      currentOAuthSession = { provider: p.id, code_verifier: data.code_verifier, state: data.state, redirect_uri: data.redirect_uri };
      actionContent.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong style="font-size: 13px; color: var(--text-primary);">Autorização: ${escapeHtml(p.name)}</strong>
            <span class="lw-badge active" style="font-size: 10px;">Aguardando Código</span>
          </div>
          <p style="margin: 0; font-size: 12px; color: var(--text-secondary); line-height: 1.4;">
            1. Clique no botão abaixo para abrir a autorização no seu navegador.<br>
            2. Conceda permissão na sua conta e cole a URL de retorno (ou código) abaixo:
          </p>
          <div style="display: flex; gap: 8px; align-items: center;">
            <a href="${escapeHtml(data.auth_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-sm" style="text-decoration: none; display: inline-flex; align-items: center; gap: 6px;">🔗 Abrir Login no Navegador</a>
            <button type="button" class="btn btn-secondary btn-sm" id="btn-omni-paste-oauth">📋 Colar</button>
          </div>
          <div class="oauth-loopback-hint" style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 6px; padding: 8px 10px; font-size: 11px; line-height: 1.4; color: var(--text-secondary);">
            💡 Redirecionamento na porta 8080: se o navegador exibir erro na URL <code>http://localhost:8080/callback?code=...</code>, copie o link completo da barra de endereços e cole abaixo:
          </div>
          <div style="display: flex; gap: 6px;">
            <input type="text" id="omni-oauth-code-input" class="ag-input" placeholder="Cole a URL inteira ou código aqui..." style="flex: 1; padding: 6px 8px; font-size: 12px;">
            <button type="button" class="btn btn-primary btn-sm" id="btn-omni-finish-oauth">Concluir</button>
          </div>
          <div id="omni-oauth-code-feedback" style="display: none; font-size: 11px; color: var(--color-brand, #38bdf8);">✓ URL com código de autorização detectada!</div>
        </div>
      `;

      const inputCode = document.getElementById('omni-oauth-code-input');
      const codeFeedback = document.getElementById('omni-oauth-code-feedback');
      if (inputCode && codeFeedback) {
        inputCode.addEventListener('input', () => {
          const val = inputCode.value.trim();
          if (val.includes('code=') || val.includes('state=')) {
            codeFeedback.style.display = 'block';
            codeFeedback.textContent = '✓ URL com código de autorização detectada!';
          } else if (val.length > 8) {
            codeFeedback.style.display = 'block';
            codeFeedback.textContent = '✓ Código de autenticação detectado!';
          } else {
            codeFeedback.style.display = 'none';
          }
        });
      }

      document.getElementById('btn-omni-paste-oauth')?.addEventListener('click', async () => {
        try {
          const clipText = await navigator.clipboard.readText();
          if (clipText && inputCode) {
            inputCode.value = clipText.trim();
            inputCode.dispatchEvent(new Event('input'));
          }
        } catch (_) {
          if (inputCode) inputCode.focus();
        }
      });

      try { window.open(data.auth_url, '_blank'); } catch (_) {}

      document.getElementById('btn-omni-finish-oauth')?.addEventListener('click', async () => {
        const inputCode = document.getElementById('omni-oauth-code-input');
        const rawCode = inputCode ? inputCode.value.trim() : '';
        if (!rawCode) { showToast('Por favor, cole a URL de callback ou código.', 'warning'); return; }

        let parsedCode = rawCode;
        let parsedState = currentOAuthSession?.state;
        try {
          const urlToParse = rawCode.includes('://') ? rawCode : `http://${rawCode}`;
          const urlObj = new URL(urlToParse);
          if (urlObj.searchParams.has('code')) parsedCode = urlObj.searchParams.get('code');
          if (urlObj.searchParams.has('state')) parsedState = urlObj.searchParams.get('state');
        } catch (_) {}

        try {
          const finishRes = await apiFetch('/api/omniroute/oauth/finish', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              provider: currentOAuthSession.provider,
              code: parsedCode,
              code_verifier: currentOAuthSession.code_verifier,
              redirect_uri: currentOAuthSession.redirect_uri,
              state: parsedState
            })
          });
          const finishData = await finishRes.json();
          if (finishData.status === 'ok') {
            showToast('Conta conectada com sucesso no OmniRoute!', 'success');
            window.dispatchEvent(new CustomEvent('omniroute-account-connected'));
            const modal = document.getElementById('modal-omniroute-account');
            if (modal) modal.style.display = 'none';
          } else {
            showToast(`Falha na autorização: ${finishData.message || 'Código inválido'}`, 'error');
          }
        } catch (err) {
          showToast(`Erro na troca de token: ${err.message}`, 'error');
        }
      });
    } else if (data.flow === 'device') {
      const userCode = data.user_code || data.device_code || '';
      const verifyUri = data.verification_uri || 'https://github.com/login/device';
      actionContent.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong style="font-size: 13px; color: var(--text-primary);">Código do Dispositivo: ${escapeHtml(p.name)}</strong>
            <span class="lw-badge active" style="font-size: 10px;">Device Code</span>
          </div>
          <div class="omni-device-code-display" id="omni-device-code-val" style="font-size: 18px; font-weight: bold; letter-spacing: 2px; text-align: center; padding: 10px; background: rgba(0,0,0,0.3); border-radius: 6px;">${escapeHtml(userCode)}</div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap;">
            <button type="button" class="btn btn-secondary btn-sm" id="btn-copy-device-code">📋 Copiar Código</button>
            <a href="${escapeHtml(verifyUri)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-sm" style="text-decoration: none;">🔗 Abrir Autorização</a>
            <button type="button" class="btn btn-secondary btn-sm" id="btn-check-device-auth">🔄 Já autorizei</button>
          </div>
        </div>
      `;

      document.getElementById('btn-copy-device-code')?.addEventListener('click', () => {
        navigator.clipboard.writeText(userCode);
        showToast('Código copiado!', 'success');
      });

      document.getElementById('btn-check-device-auth')?.addEventListener('click', async () => {
        window.dispatchEvent(new CustomEvent('omniroute-check-device', { detail: { provider: p.id } }));
      });
    }
  } catch (err) {
    actionContent.innerHTML = `<div style="color: var(--color-danger, #ef4444); font-size: 12px;">⚠️ Falha na comunicação: ${escapeHtml(err.message)}</div>`;
  }
}
