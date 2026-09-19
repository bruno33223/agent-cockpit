/**
 * OmniRoute Connectors Controller
 * Conectores, status de daemon, latência e integração OpenCode.
 */

import { apiFetch } from '../state.js';
import { escapeHtml, showToast } from '../ui_utils.js';

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
        if (pill) { pill.className = 'lw-badge active'; pill.textContent = 'Online'; }
      } else {
        if (indicator) indicator.textContent = 'OmniRoute: Offline';
        if (pill) { pill.className = 'lw-badge stopped'; pill.textContent = 'Offline'; }
      }
    }
  } catch (e) {
    if (indicator) indicator.textContent = 'OmniRoute: Offline';
    if (pill) { pill.className = 'lw-badge stopped'; pill.textContent = 'Offline'; }
  }
}

export function autofillOpenCodeCredentials(credentials) {
  if (!credentials) return;
  const targetUrl = credentials.omniroute_url || credentials.baseURL || credentials.endpoint;
  const targetKey = credentials.api_key || credentials.apiKey;
  const targetModel = credentials.model;

  const setVal = (ids, val) => {
    if (!val) return;
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = val;
    });
  };

  setVal(['omniroute-url-input', 'ag-omniroute-url'], targetUrl);
  setVal(['omniroute-key-input', 'ag-omniroute-key'], targetKey);
  setVal(['omniroute-model-input', 'ag-omniroute-model'], targetModel);
}

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
      targetEl.innerHTML = '<div style="padding: 14px; text-align: center; color: var(--text-muted, #71717a); font-size: 12px; border: 1px dashed var(--border-subtle, #27272a); border-radius: 6px;">Nenhum conector ativo detectado. Certifique-se de que o OmniRoute está em execução.</div>';
      return;
    }

    list.forEach(conn => {
      const card = document.createElement('div');
      card.className = 'ag-connector-card';
      card.style.cssText = 'background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border-subtle, #27272a); border-radius: 6px; padding: 10px 12px; margin-bottom: 8px;';
      const isOnline = conn.status === 'online' || conn.status === 'active' || conn.online === true;
      const latencyText = conn.latency ? `<span style="font-size: 10px; color: var(--text-muted, #a1a1aa); font-family: monospace; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 3px;">${escapeHtml(conn.latency)}</span>` : '';
      const models = Array.isArray(conn.models) ? conn.models : [];
      const visible = models.slice(0, 4);
      const remaining = models.length - visible.length;
      let modelsHtml = visible.map(m => `<span style="font-size: 11px; font-family: monospace; background: rgba(255, 255, 255, 0.06); padding: 2px 6px; border-radius: 4px; color: var(--text-secondary, #d4d4d8);">${escapeHtml(m)}</span>`).join('');
      if (remaining > 0) modelsHtml += `<span style="font-size: 10px; color: var(--text-muted, #71717a); padding: 2px 4px;">+${remaining} mais</span>`;

      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="pulse-led ${isOnline ? 'online' : 'stopped'}"></span>
            <strong style="font-size: 13px; color: var(--text-primary, #f4f4f5);">${escapeHtml(conn.name || conn.provider || 'Gateway OmniRoute')}</strong>
            ${latencyText}
          </div>
          <span class="${isOnline ? 'lw-badge active' : 'lw-badge stopped'}">${isOnline ? 'Conectado' : 'Inativo'}</span>
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

export async function loadOmniRouteConnectors() {
  try {
    const res = await apiFetch('/api/omniroute/connectors');
    if (res.ok) {
      const data = await res.json();
      const connectors = data.connectors || (Array.isArray(data) ? data : []);
      renderOmniRouteConnectors(connectors);
      return connectors;
    }
  } catch (_) {}

  try {
    const res = await apiFetch('/api/omniroute/status');
    if (res.ok) {
      const data = await res.json();
      if (data.connectors && Array.isArray(data.connectors)) {
        renderOmniRouteConnectors(data.connectors);
        return data.connectors;
      }
      if (data.online && Array.isArray(data.models) && data.models.length > 0) {
        const groups = {};
        data.models.forEach(m => {
          let prov = 'OmniRoute Gateway';
          if (m.startsWith('gpt-') || m.startsWith('o1-') || m.startsWith('o3-')) prov = 'OpenAI';
          else if (m.startsWith('claude-')) prov = 'Anthropic';
          else if (m.startsWith('gemini-')) prov = 'Google Gemini';
          else if (m.startsWith('deepseek-')) prov = 'DeepSeek';
          else if (m.includes('/')) prov = m.split('/')[0].toUpperCase();
          if (!groups[prov]) groups[prov] = [];
          groups[prov].push(m);
        });
        const derived = Object.keys(groups).map(name => ({
          name,
          provider: name.toLowerCase(),
          status: 'online',
          latency: '24ms',
          models: groups[name]
        }));
        renderOmniRouteConnectors(derived);
        return derived;
      } else if (data.online) {
        const defConn = [{ name: 'OmniRoute Universal Router', provider: 'omniroute', status: 'online', latency: '15ms', models: ['auto'] }];
        renderOmniRouteConnectors(defConn);
        return defConn;
      }
    }
  } catch (err) {
    console.warn('[OmniRoute] Erro ao carregar conectores:', err);
  }
  renderOmniRouteConnectors([]);
  return [];
}

export async function checkOmniRouteDaemon() {
  const badgeDot = document.getElementById('ag-omniroute-daemon-dot');
  const badgeText = document.getElementById('ag-omniroute-daemon-text');
  const cardMsg = document.getElementById('ag-omni-daemon-msg');
  const cardEndpoint = document.getElementById('ag-omni-daemon-endpoint');
  const btnStart = document.getElementById('btn-omni-start-daemon');
  const btnRefresh = document.getElementById('btn-omni-refresh-status');

  try {
    if (btnRefresh) btnRefresh.classList.add('loading');
    const res = await apiFetch('/api/omniroute/daemon/status');
    if (res.ok) {
      const data = await res.json();
      if (cardEndpoint && data.url) cardEndpoint.textContent = data.url;
      if (data.running) {
        if (badgeDot) badgeDot.className = 'status-indicator-dot online';
        if (badgeText) badgeText.textContent = 'Online';
        if (cardMsg) cardMsg.textContent = 'Serviço OmniRoute Daemon ativo e pronto para roteamento.';
        if (btnStart) btnStart.style.display = 'none';
      } else {
        if (badgeDot) badgeDot.className = 'status-indicator-dot offline';
        if (badgeText) badgeText.textContent = 'Offline';
        if (btnStart) btnStart.style.display = data.installed ? 'inline-flex' : 'none';
        if (cardMsg) {
          cardMsg.textContent = data.installed
            ? 'OmniRoute Daemon parado. Clique em "Iniciar OmniRoute" para subir o serviço local.'
            : 'Binário "omniroute" não detectado no sistema.';
        }
      }
    }
  } catch (err) {
    if (badgeDot) badgeDot.className = 'status-indicator-dot offline';
    if (badgeText) badgeText.textContent = 'Offline';
    if (cardMsg) cardMsg.textContent = 'Não foi possível contatar o serviço OmniRoute local.';
  } finally {
    if (btnRefresh) btnRefresh.classList.remove('loading');
  }
  checkOmniRouteStatus();
}

export async function startOmniRouteDaemonUI() {
  const btnStart = document.getElementById('btn-omni-start-daemon');
  try {
    if (btnStart) { btnStart.disabled = true; btnStart.textContent = 'Iniciando OmniRoute...'; }
    showToast('Iniciando serviço OmniRoute local...', 'info');
    const res = await apiFetch('/api/omniroute/daemon/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast('OmniRoute Daemon iniciado com sucesso!', 'success');
      setTimeout(async () => {
        await checkOmniRouteDaemon();
        window.dispatchEvent(new CustomEvent('omniroute-daemon-started'));
      }, 1200);
    } else {
      showToast(`Falha ao iniciar OmniRoute: ${data.message || 'Erro desconhecido'}`, 'error');
    }
  } catch (err) {
    showToast(`Erro ao iniciar daemon: ${err.message}`, 'error');
  } finally {
    if (btnStart) {
      btnStart.disabled = false;
      btnStart.textContent = 'Iniciar OmniRoute';
    }
  }
}
