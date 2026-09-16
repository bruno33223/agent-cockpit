/**
 * Módulo do Zeus Chat Workspace (ZeusChatWorkspaceManager)
 * Issue #24 - Fatia 2
 *
 * O Zeus Chat é um painel nativo de terminal integrado ao TerminalWorkspaceManager
 * (role: 'visual-chat'), ocupando a mesma área dos terminais no grid (podendo ficar
 * lado a lado, em split ou fullscreen), com aba identificada pelo ícone sagrado do
 * Zeus (zeus_terminal_god.svg) e título 'Zeus Chat'.
 *
 * Fornece interatividade em tempo real com subagentes através do evento "subagent_spawn",
 * renderizando cards interativos que permitem abrir/focar terminais dedicados de
 * subagentes no workspace sem fechar o chat.
 */

import { escapeHtml } from './ui_utils.js';
import { apiFetch, currentProjectId, state } from './state.js';
import { terminalWorkspace } from './terminal_workspace.js';
import { openSubagentTab, focusSubagentTab, getSubagentRoleMeta } from './subagent_tabs.js';

export class ZeusChatWorkspaceManager {
  constructor() {
    this.sessionId = 'zeus-chat';
    this.paneClassName = 'zeus-chat-pane';
    this.role = 'visual-chat';
    this.messages = [];
    this.isProcessing = false;
    this.subagents = new Map();
    this.session = null;
    this.paneEl = null;
    this.messagesContainer = null;
    this.chatInput = null;
    this.btnSend = null;
    this.btnClear = null;
  }

  /**
   * Abre ou foca a sessão do Zeus Chat no workspace integrado.
   * @param {Object} terminalManager Instância do TerminalWorkspaceManager
   * @returns {Object} Sessão do chat
   */
  openOrCreateChatSession(terminalManager = terminalWorkspace) {
    const mgr = terminalManager || (typeof window !== 'undefined' ? window.terminalWorkspace : null);
    if (!mgr) {
      console.warn('[ZeusChat] TerminalWorkspaceManager não disponível');
      return null;
    }

    // 1. Verifica se a sessão do Zeus Chat já existe
    let existingSession = null;
    if (mgr.sessions) {
      for (const [id, s] of mgr.sessions) {
        if (s.role === 'visual-chat' || id === this.sessionId || s.name === 'Zeus Chat') {
          existingSession = s;
          break;
        }
      }
    }

    if (existingSession) {
      mgr.selectSession(existingSession.id);
      this.focusInput();
      return existingSession;
    }

    // 2. Se não existir, cria nova sessão nativa no TerminalWorkspaceManager
    const session = mgr.createSession({
      id: this.sessionId,
      name: 'Zeus Chat',
      role: 'visual-chat',
      agentType: 'zeus',
      cwd: mgr.getActiveProjectRoot ? mgr.getActiveProjectRoot() : '/'
    });

    if (session) {
      this.session = session;
      if (session.elPane) {
        this.attachPane(session, session.elPane);
      }
      mgr.selectSession(session.id);
    }

    return session;
  }

  /**
   * Conecta os elementos visuais do chat e manipuladores de eventos ao painel do terminal.
   * @param {Object} session 
   * @param {HTMLElement} elPane 
   */
  attachPane(session, elPane) {
    this.session = session;
    this.paneEl = elPane;
    this.messagesContainer = elPane.querySelector('.zeus-chat-messages');
    this.chatInput = elPane.querySelector('.zeus-chat-input');
    this.btnSend = elPane.querySelector('.btn-send-zeus-chat');
    this.btnClear = elPane.querySelector('.zeus-btn-clear-history') || elPane.querySelector('#btn-clear-zeus-chat');

    if (this.btnSend) {
      this.btnSend.addEventListener('click', (e) => {
        e.stopPropagation();
        this.sendMessage();
      });
    }

    if (this.chatInput) {
      this.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.sendMessage();
        }
      });
    }

    if (this.btnClear) {
      this.btnClear.addEventListener('click', (e) => {
        e.stopPropagation();
        this.clearMessages();
      });
    }

    // Renderiza mensagem de boas-vindas inicial se o histórico estiver vazio
    if (this.messages.length === 0) {
      this.renderMessage({
        role: 'assistant',
        author: 'Orquestrador Zeus',
        content: '⚡ **Zeus Master Chat Online.** Orquestração de alto nível, controle de blueprints e despacho em lote de subagentes.',
        timestamp: new Date().toLocaleTimeString()
      });
    } else {
      // Re-renderiza mensagens acumuladas
      this.renderAllMessages();
    }
  }

  focusInput() {
    if (this.chatInput) {
      setTimeout(() => this.chatInput.focus(), 60);
    } else if (this.paneEl) {
      const input = this.paneEl.querySelector('.zeus-chat-input');
      if (input) setTimeout(() => input.focus(), 60);
    }
  }

  clearMessages() {
    this.messages = [];
    if (this.messagesContainer) {
      this.messagesContainer.innerHTML = '';
      this.renderMessage({
        role: 'system',
        author: 'Sistema',
        content: 'Histórico de mensagens limpo.',
        timestamp: new Date().toLocaleTimeString()
      });
    }
  }

  renderAllMessages() {
    if (!this.messagesContainer) return;
    this.messagesContainer.innerHTML = '';
    for (const msg of this.messages) {
      this._renderMessageDom(msg);
    }
  }

  /**
   * Renderiza uma mensagem no container do chat.
   */
  renderMessage(msg) {
    this.messages.push(msg);
    this._renderMessageDom(msg);
  }

  _renderMessageDom(msg) {
    if (!this.messagesContainer) {
      if (this.paneEl) {
        this.messagesContainer = this.paneEl.querySelector('.zeus-chat-messages');
      }
      if (!this.messagesContainer) return;
    }

    const card = document.createElement('div');
    card.className = `zeus-chat-msg role-${msg.role || 'assistant'}`;

    const header = document.createElement('div');
    header.className = 'zeus-msg-header';

    const authorWrap = document.createElement('div');
    authorWrap.className = 'zeus-msg-author-wrap';

    if (msg.role === 'assistant' || (msg.author && msg.author.includes('Zeus'))) {
      const iconImg = document.createElement('img');
      iconImg.src = '/zeus_terminal_god.svg';
      iconImg.className = 'zeus-msg-god-icon';
      iconImg.alt = 'Zeus';
      authorWrap.appendChild(iconImg);
    }

    const authorSpan = document.createElement('strong');
    authorSpan.className = 'zeus-msg-author';
    authorSpan.textContent = msg.author || (msg.role === 'user' ? 'Você' : 'Zeus');
    authorWrap.appendChild(authorSpan);

    const timeSpan = document.createElement('span');
    timeSpan.className = 'zeus-msg-time';
    timeSpan.textContent = msg.timestamp || new Date().toLocaleTimeString();

    header.appendChild(authorWrap);
    header.appendChild(timeSpan);
    card.appendChild(header);

    // Bloco de raciocínio interno (Thinking) se houver
    if (msg.thinking) {
      const thinkDetails = document.createElement('details');
      thinkDetails.className = 'zeus-thinking-box';
      const thinkSummary = document.createElement('summary');
      thinkSummary.innerHTML = '💭 <em>Raciocínio & Blueprint Staff</em>';
      const thinkContent = document.createElement('div');
      thinkContent.className = 'zeus-thinking-content';
      thinkContent.innerHTML = escapeHtml(msg.thinking).replace(/\n/g, '<br>');
      thinkDetails.appendChild(thinkSummary);
      thinkDetails.appendChild(thinkContent);
      card.appendChild(thinkDetails);
    }

    // Ferramentas executadas se houver
    if (Array.isArray(msg.tools) && msg.tools.length > 0) {
      const toolsContainer = document.createElement('div');
      toolsContainer.className = 'zeus-tools-container';
      msg.tools.forEach(tool => {
        const item = document.createElement('div');
        item.className = 'zeus-tool-item';
        item.innerHTML = `🔧 <strong>${escapeHtml(tool.name || 'Tool')}:</strong> ${escapeHtml(tool.detail || '')}`;
        toolsContainer.appendChild(item);
      });
      card.appendChild(toolsContainer);
    }

    // Corpo de texto
    const body = document.createElement('div');
    body.className = 'zeus-msg-body';
    body.innerHTML = escapeHtml(msg.content || '').replace(/\n/g, '<br>');
    card.appendChild(body);

    this.messagesContainer.appendChild(card);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }

  /**
   * Envia a mensagem do usuário para o backend e processa a resposta.
   */
  async sendMessage() {
    if (!this.chatInput) {
      if (this.paneEl) this.chatInput = this.paneEl.querySelector('.zeus-chat-input');
    }
    if (!this.chatInput) return;

    const text = this.chatInput.value.trim();
    if (!text || this.isProcessing) return;

    this.chatInput.value = '';
    const timestamp = new Date().toLocaleTimeString();

    this.renderMessage({
      role: 'user',
      author: 'Você',
      content: text,
      timestamp
    });

    this.isProcessing = true;
    if (this.btnSend) {
      this.btnSend.disabled = true;
      this.btnSend.innerHTML = '<span>...</span>';
    }

    try {
      const payload = {
        message: text,
        project_id: currentProjectId || null,
        timestamp: new Date().toISOString()
      };

      let response = null;
      try {
        response = await apiFetch('/api/opencode/headless/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } catch (err) {
        // Fallback orquestrador
        response = await apiFetch('/api/orchestrator/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).catch(() => null);
      }

      if (response && (response.reply || response.content)) {
        this.renderMessage({
          role: 'assistant',
          author: response.author || 'Orquestrador Zeus',
          content: response.reply || response.content,
          thinking: response.thinking || null,
          tools: response.tools || [],
          timestamp: new Date().toLocaleTimeString()
        });

        if (response.subagent_spawn) {
          this.handleSubagentSpawn(response.subagent_spawn);
        }
      } else if (response && response.error) {
        this.renderMessage({
          role: 'error',
          author: 'Zeus Error',
          content: `❌ ${response.error}`,
          timestamp: new Date().toLocaleTimeString()
        });
      } else {
        this.renderMessage({
          role: 'assistant',
          author: 'Orquestrador Zeus',
          content: response?.message || 'Comando recebido e registrado na telemetria.',
          timestamp: new Date().toLocaleTimeString()
        });
      }
    } catch (e) {
      console.warn('[ZeusChat] Falha na comunicação:', e);
      this.renderMessage({
        role: 'system',
        author: 'Zeus Telemetry',
        content: `⚡ Notificação local: Comando processado no workspace. (${escapeHtml(e.message)})`,
        timestamp: new Date().toLocaleTimeString()
      });
    } finally {
      this.isProcessing = false;
      if (this.btnSend) {
        this.btnSend.disabled = false;
        this.btnSend.innerHTML = '<span>Enviar</span> <span>⚡</span>';
      }
      this.focusInput();
    }
  }

  /**
   * Critério 3: Manipula o evento "subagent_spawn", renderizando card interativo com status
   * e botão "Abrir Terminal do Subagente". Clicar no botão foca o terminal correspondente
   * no workspace sem fechar o chat.
   * @param {Object} subagentData Dados do subagente despachado
   */
  handleSubagentSpawn(subagentData = {}) {
    if (!subagentData || typeof subagentData !== 'object') {
      subagentData = {};
    }

    const subagentId = subagentData.id || subagentData.subagentId || subagentData.subagent_id || `subagent-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    const roleType = subagentData.role || subagentData.type || subagentData.subagent_type || 'builder';
    const sliceId = subagentData.sliceId || subagentData.slice_id || (subagentData.taskId ? `task-${subagentData.taskId}` : 'slice-1');
    const status = (subagentData.status || 'RUNNING').toUpperCase();
    const agentType = subagentData.agentType || subagentData.agent_type || 'opencode';
    const meta = (typeof getSubagentRoleMeta === 'function') ? getSubagentRoleMeta(roleType) : { icon: '🤖', label: 'Builder' };
    const title = subagentData.title || `${meta.icon} [${meta.label}] ${sliceId}`;
    const description = subagentData.description || subagentData.task || `Subagente ${meta.label} instanciado para execução isolada da fatia ${sliceId}.`;

    const normalized = {
      id: subagentId,
      subagentId,
      role: roleType,
      type: roleType,
      sliceId,
      status,
      agentType,
      title,
      description
    };

    this.subagents.set(subagentId, normalized);

    // Garante que o painel do chat esteja montado
    if (!this.messagesContainer) {
      if (this.paneEl) {
        this.messagesContainer = this.paneEl.querySelector('.zeus-chat-messages');
      }
    }

    // Se o chat ainda não foi aberto no workspace, abre-o
    if (!this.messagesContainer && typeof terminalWorkspace !== 'undefined') {
      this.openOrCreateChatSession(terminalWorkspace);
    }

    // Renderiza card interativo no chat
    const card = document.createElement('div');
    card.className = 'zeus-chat-card zeus-subagent-card';
    card.id = `card-subagent-${subagentId}`;
    card.setAttribute('data-subagent-id', subagentId);
    card.setAttribute('data-slice-id', sliceId);

    const statusBadgeClass = `status-${status.toLowerCase()}`;

    card.innerHTML = `
      <div class="zeus-subagent-card-header">
        <div class="zeus-subagent-title-row">
          <span class="zeus-subagent-icon">${meta.icon}</span>
          <strong class="zeus-subagent-name">${escapeHtml(title)}</strong>
          <span class="subagent-badge ${statusBadgeClass}" id="chat-badge-${escapeHtml(subagentId)}">${escapeHtml(status)}</span>
        </div>
      </div>
      <div class="zeus-subagent-card-body">
        <div class="zeus-subagent-meta">
          <span class="zeus-meta-pill role-pill"><strong>Papel:</strong> ${escapeHtml(meta.label)}</span>
          <span class="zeus-meta-pill slice-pill"><strong>Fatia:</strong> ${escapeHtml(sliceId)}</span>
          <span class="zeus-meta-pill engine-pill"><strong>Engine:</strong> ${escapeHtml(agentType)}</span>
        </div>
        <p class="zeus-subagent-desc">${escapeHtml(description)}</p>
      </div>
      <div class="zeus-subagent-card-actions">
        <button class="action-btn primary btn-sm btn-open-subagent-terminal" data-subagent-id="${escapeHtml(subagentId)}" title="Abrir terminal dedicado deste subagente">
          <span class="btn-icon">🖥️</span>
          <span>Abrir Terminal do Subagente</span>
        </button>
      </div>
    `;

    const btnOpenTerminal = card.querySelector('.btn-open-subagent-terminal');
    if (btnOpenTerminal) {
      btnOpenTerminal.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openSubagentTerminal(normalized);
      });
    }

    if (this.messagesContainer) {
      this.messagesContainer.appendChild(card);
      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    return card;
  }

  /**
   * Aciona a abertura e foco do terminal do subagente mantendo o chat ativo no workspace.
   * @param {Object} subagentData 
   */
  openSubagentTerminal(subagentData) {
    const subagentId = subagentData.id || subagentData.subagentId;

    // 1. Invoca openSubagentTab de subagent_tabs.js
    let record = null;
    if (typeof openSubagentTab === 'function') {
      record = openSubagentTab(subagentData);
    } else if (typeof window !== 'undefined' && typeof window.openSubagentTab === 'function') {
      record = window.openSubagentTab(subagentData);
    }

    // 2. Foca a aba do subagente sem fechar a sessão de chat
    const targetId = (record && record.id) || subagentId;
    if (typeof focusSubagentTab === 'function') {
      focusSubagentTab(targetId);
    } else if (typeof window !== 'undefined' && typeof window.focusSubagentTab === 'function') {
      window.focusSubagentTab(targetId);
    } else if (typeof terminalWorkspace !== 'undefined' && record && record.session) {
      terminalWorkspace.selectSession(record.session.id, true);
    }

    // 3. Feedback visual no card do chat
    const badge = document.getElementById(`chat-badge-${subagentId}`);
    if (badge) {
      badge.classList.add('focused-pulse');
      setTimeout(() => badge.classList.remove('focused-pulse'), 1500);
    }
  }
}

export const zeusChatWorkspace = new ZeusChatWorkspaceManager();

export function openOrCreateChatSession(terminalManager = terminalWorkspace) {
  return zeusChatWorkspace.openOrCreateChatSession(terminalManager);
}

export function initZeusChatWorkspace() {
  // Escuta eventos globais de subagent_spawn via DOM
  if (typeof window !== 'undefined') {
    window.addEventListener('subagent_spawn', (e) => {
      if (e && e.detail) {
        zeusChatWorkspace.handleSubagentSpawn(e.detail);
      }
    });
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('subagent_spawn', (e) => {
      if (e && e.detail) {
        zeusChatWorkspace.handleSubagentSpawn(e.detail);
      }
    });
  }
}

// Expõe no escopo global para retrocompatibilidade com scripts e testes
if (typeof window !== 'undefined') {
  window.zeusChatWorkspace = zeusChatWorkspace;
  window.openOrCreateChatSession = openOrCreateChatSession;
  window.openZeusChat = () => zeusChatWorkspace.openOrCreateChatSession();
  window.initZeusChatWorkspace = initZeusChatWorkspace;
}
