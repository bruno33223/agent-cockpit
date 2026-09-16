/**
 * Módulo de Chat Visual OpenCode (OpenCode Visual Chat Interpreter)
 * Issue #18 - Interface de chat conversacional em background com cards de pensamento,
 * ações/ferramentas, status de subagentes e streaming.
 */

import { escapeHtml, showToast } from './ui_utils.js';
import { apiFetch, currentProjectId, state } from './state.js';

class OpenCodeChatManager {
  constructor() {
    this.container = null;
    this.messagesContainer = null;
    this.chatInput = null;
    this.btnSend = null;
    this.btnClear = null;
    this.btnClose = null;
    this.statusBadge = null;
    this.isProcessing = false;
    this.messages = [];
  }

  init() {
    this.container = document.getElementById('opencode-visual-chat-container');
    this.messagesContainer = document.getElementById('opencode-chat-messages');
    this.chatInput = document.getElementById('opencode-chat-input');
    this.btnSend = document.getElementById('btn-send-opencode-chat');
    this.btnClear = document.getElementById('btn-clear-opencode-chat');
    this.btnClose = document.getElementById('btn-close-opencode-chat');
    this.statusBadge = document.getElementById('opencode-chat-status');

    if (!this.container || !this.messagesContainer) {
      return;
    }

    if (this.btnSend) {
      this.btnSend.addEventListener('click', () => this.sendMessage());
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
      this.btnClear.addEventListener('click', () => this.clearMessages());
    }

    if (this.btnClose) {
      this.btnClose.addEventListener('click', () => this.close());
    }

    // Inicializa mensagem de boas-vindas se estiver vazio
    if (this.messages.length === 0 && this.messagesContainer.children.length === 0) {
      this.renderMessage({
        role: 'assistant',
        author: 'OpenCode Engine',
        content: '👋 Olá! Sou o motor headless do OpenCode. Envie uma instrução ou objetivo para iniciar.',
        timestamp: new Date().toLocaleTimeString()
      });
    }
  }

  open() {
    if (!this.container) this.init();
    if (this.container) {
      this.container.style.display = 'flex';
      if (this.chatInput) {
        this.chatInput.focus();
      }
    }
  }

  close() {
    if (this.container) {
      this.container.style.display = 'none';
    }
  }

  clearMessages() {
    this.messages = [];
    if (this.messagesContainer) {
      this.messagesContainer.innerHTML = '';
      this.renderMessage({
        role: 'system',
        author: 'Sistema',
        content: 'Histórico de chat limpo.',
        timestamp: new Date().toLocaleTimeString()
      });
    }
  }

  setStatus(statusText, type = 'ready') {
    if (this.statusBadge) {
      this.statusBadge.textContent = statusText;
      this.statusBadge.className = `opencode-chat-badge status-${type}`;
    }
  }

  async sendMessage() {
    if (!this.chatInput) return;
    const text = this.chatInput.value.trim();
    if (!text || this.isProcessing) return;

    // Limpa campo de input
    this.chatInput.value = '';

    // Adiciona mensagem do usuário
    const timestamp = new Date().toLocaleTimeString();
    this.renderMessage({
      role: 'user',
      author: 'Você',
      content: text,
      timestamp
    });

    this.isProcessing = true;
    this.setStatus('Pensando...', 'busy');

    try {
      const payload = {
        message: text,
        project_id: currentProjectId || null,
        timestamp: new Date().toISOString()
      };

      const response = await apiFetch('/api/opencode/headless/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (response && response.reply) {
        this.renderMessage({
          role: 'assistant',
          author: response.author || 'OpenCode',
          content: response.reply,
          thinking: response.thinking || null,
          tools: response.tools || [],
          timestamp: new Date().toLocaleTimeString()
        });
      } else if (response && response.error) {
        this.renderMessage({
          role: 'error',
          author: 'OpenCode Error',
          content: `❌ Erro: ${response.error}`,
          timestamp: new Date().toLocaleTimeString()
        });
      } else {
        this.renderMessage({
          role: 'assistant',
          author: 'OpenCode',
          content: response?.message || 'Instrução recebida pelo motor em segundo plano.',
          timestamp: new Date().toLocaleTimeString()
        });
      }
    } catch (err) {
      console.warn('[OpenCode Chat] Erro ao enviar mensagem:', err);
      this.renderMessage({
        role: 'error',
        author: 'Falha de Comunicação',
        content: `Não foi possível conectar ao endpoint /api/opencode/headless/message: ${err.message}`,
        timestamp: new Date().toLocaleTimeString()
      });
    } finally {
      this.isProcessing = false;
      this.setStatus('Pronto', 'ready');
      if (this.chatInput) {
        this.chatInput.focus();
      }
    }
  }

  renderMessage({ role = 'assistant', author = 'Agente', content = '', thinking = null, tools = [], timestamp = '' }) {
    if (!this.messagesContainer) return;

    const msgObj = { role, author, content, thinking, tools, timestamp };
    this.messages.push(msgObj);

    const card = document.createElement('div');
    card.className = `opencode-chat-card role-${role}`;

    const header = document.createElement('div');
    header.className = 'opencode-card-header';

    const roleBadge = document.createElement('span');
    roleBadge.className = `role-badge badge-${role}`;
    roleBadge.textContent = role.toUpperCase();

    const authorSpan = document.createElement('span');
    authorSpan.className = 'card-author';
    authorSpan.textContent = author;

    const timeSpan = document.createElement('span');
    timeSpan.className = 'card-timestamp';
    timeSpan.textContent = timestamp || new Date().toLocaleTimeString();

    header.appendChild(roleBadge);
    header.appendChild(authorSpan);
    header.appendChild(timeSpan);
    card.appendChild(header);

    // Seção de pensamento ("Thinking") se houver
    if (thinking) {
      const thinkBox = document.createElement('details');
      thinkBox.className = 'opencode-thinking-box';
      const thinkSummary = document.createElement('summary');
      thinkSummary.innerHTML = '💭 <em>Pensamento / Raciocínio interno</em>';
      const thinkContent = document.createElement('div');
      thinkContent.className = 'thinking-text';
      thinkContent.innerHTML = escapeHtml(thinking);
      thinkBox.appendChild(thinkSummary);
      thinkBox.appendChild(thinkContent);
      card.appendChild(thinkBox);
    }

    // Seção de Tools se houver
    if (Array.isArray(tools) && tools.length > 0) {
      const toolsBox = document.createElement('div');
      toolsBox.className = 'opencode-tools-box';
      tools.forEach(tool => {
        const toolItem = document.createElement('div');
        toolItem.className = 'tool-item';
        toolItem.innerHTML = `🔧 <strong>${escapeHtml(tool.name || 'Tool')}:</strong> ${escapeHtml(tool.detail || '')}`;
        toolsBox.appendChild(toolItem);
      });
      card.appendChild(toolsBox);
    }

    // Corpo da mensagem com escapeHtml seguro
    const body = document.createElement('div');
    body.className = 'opencode-card-body';
    body.innerHTML = escapeHtml(content).replace(/\n/g, '<br>');
    card.appendChild(body);

    this.messagesContainer.appendChild(card);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }
}

export const openCodeChat = new OpenCodeChatManager();

export function initOpenCodeChat() {
  openCodeChat.init();
}

// Expõe globalmente para compatibilidade de testes e scripts
if (typeof window !== 'undefined') {
  window.openCodeChat = openCodeChat;
  window.initOpenCodeChat = initOpenCodeChat;
}
