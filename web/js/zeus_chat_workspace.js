/**
 * Módulo do Zeus Chat Workspace (ZeusChatWorkspaceManager)
 * Issue #24 - Fatia 2 & Melhoria de Streaming Real e Travamento
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

    // Controles ricos contextuais
    this.modelSelect = null;
    this.btnAttach = null;
    this.fileInput = null;
    this.btnMic = null;
    this.attachmentsPreview = null;
    this.btnSkills = null;
    this.attachedImages = [];
    this.selectedModel = 'auto';
    this.isRecording = false;
    this.mediaRecorder = null;
    this.audioChunks = [];
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

    // Controles contextuais adicionais
    this.modelSelect = elPane.querySelector('.zeus-pane-model-select') || elPane.querySelector('.zeus-model-select');
    this.btnAttach = elPane.querySelector('.zeus-btn-attach');
    this.fileInput = elPane.querySelector('.zeus-file-input');
    this.btnMic = elPane.querySelector('.zeus-btn-mic');
    this.attachmentsPreview = elPane.querySelector('.zeus-attachments-preview');
    this.btnSkills = elPane.querySelector('.zeus-pane-btn-skills') || elPane.querySelector('.zeus-btn-skills');

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

      // Suporte a colar imagens (Ctrl+V)
      this.chatInput.addEventListener('paste', (e) => {
        const items = (e.clipboardData || e.originalEvent?.clipboardData)?.items;
        if (items) {
          for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
              const file = items[i].getAsFile();
              if (file) {
                e.preventDefault();
                this.addAttachedImage(file);
              }
            }
          }
        }
      });
    }

    if (this.btnClear) {
      this.btnClear.addEventListener('click', (e) => {
        e.stopPropagation();
        this.clearMessages();
      });
    }

    // Seletor de modelos
    if (this.modelSelect) {
      this.initModelSelector();
      this.modelSelect.addEventListener('change', () => {
        this.selectedModel = this.modelSelect.value;
      });
    }

    // Anexo de arquivos
    if (this.btnAttach && this.fileInput) {
      this.btnAttach.addEventListener('click', (e) => {
        e.stopPropagation();
        this.fileInput.click();
      });
      this.fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
          Array.from(e.target.files).forEach(file => this.addAttachedImage(file));
          e.target.value = '';
        }
      });
    }

    // Microfone STT
    if (this.btnMic) {
      this.btnMic.addEventListener('click', (e) => {
        e.stopPropagation();
        this.toggleRecording();
      });
    }

    // Botão Skills & MCPs
    if (this.btnSkills) {
      this.btnSkills.addEventListener('click', (e) => {
        e.stopPropagation();
        const globalBtn = document.getElementById('btn-zeus-skills-mcps');
        if (globalBtn) globalBtn.click();
      });
    }

    // Renderiza mensagem de boas-vindas inicial se o histórico estiver vazio
    if (this.messages.length === 0) {
      this.renderMessage({
        role: 'assistant',
        author: 'Orquestrador Zeus',
        content: '⚡ **Zeus Master Chat Online.** Orquestração de alto nível, streaming em tempo real e controle de subagentes.',
        timestamp: new Date().toLocaleTimeString()
      });
    } else {
      this.renderAllMessages();
    }
  }

  async initModelSelector() {
    if (!this.modelSelect) return;
    try {
      const [omniRes, localRes] = await Promise.all([
        fetch('/api/omniroute/connectors').then(r => r.json()).catch(() => ({ models: [] })),
        fetch('/api/local-worker/models').then(r => r.json()).catch(() => ({ models: [] }))
      ]);

      const models = [];
      if (omniRes && Array.isArray(omniRes.models)) {
        omniRes.models.forEach(m => models.push({ id: m.id || m.name, name: m.name || m.id, group: 'Cloud' }));
      }
      if (localRes && Array.isArray(localRes.models)) {
        localRes.models.forEach(m => models.push({ id: m.name || m.id, name: m.name || m.id, group: 'Local' }));
      }

      if (models.length === 0) {
        models.push(
          { id: 'gpt-4o', name: 'GPT-4o (OpenAI)', group: 'Cloud' },
          { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet', group: 'Cloud' },
          { id: 'deepseek-coder:6.7b', name: 'DeepSeek Coder 6.7B (Local)', group: 'Local' }
        );
      }

      this.modelSelect.innerHTML = '';
      models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `[${m.group}] ${m.name}`;
        this.modelSelect.appendChild(opt);
      });
      this.selectedModel = this.modelSelect.value;
    } catch (e) {
      console.warn('[ZeusChat] Erro ao carregar modelos para o seletor:', e);
    }
  }

  addAttachedImage(file) {
    if (!file || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      this.attachedImages.push(e.target.result);
      this.renderAttachmentsPreview();
    };
    reader.readAsDataURL(file);
  }

  renderAttachmentsPreview() {
    if (!this.attachmentsPreview) return;
    if (!this.attachedImages || this.attachedImages.length === 0) {
      this.attachmentsPreview.style.display = 'none';
      this.attachmentsPreview.innerHTML = '';
      return;
    }
    this.attachmentsPreview.style.display = 'flex';
    this.attachmentsPreview.innerHTML = '';
    this.attachedImages.forEach((dataUrl, idx) => {
      const thumb = document.createElement('div');
      thumb.className = 'zeus-attachment-thumb';
      thumb.innerHTML = `
        <img src="${dataUrl}" alt="Anexo" />
        <button type="button" class="zeus-thumb-remove" title="Remover imagem">&times;</button>
      `;
      thumb.querySelector('.zeus-thumb-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        this.attachedImages.splice(idx, 1);
        this.renderAttachmentsPreview();
      });
      this.attachmentsPreview.appendChild(thumb);
    });
  }

  async toggleRecording() {
    if (this.isRecording) {
      this.stopRecording();
    } else {
      this.startRecording();
    }
  }

  async startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert('Navegador não suporta gravação de áudio.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.audioChunks = [];
      this.mediaRecorder = new MediaRecorder(stream);
      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) this.audioChunks.push(e.data);
      };
      this.mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        await this.sendAudioToSTT(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };
      this.mediaRecorder.start();
      this.isRecording = true;
      if (this.btnMic) this.btnMic.classList.add('recording');
    } catch (e) {
      console.warn('[ZeusChat] Falha ao acessar microfone:', e);
    }
  }

  stopRecording() {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();
      this.isRecording = false;
      if (this.btnMic) this.btnMic.classList.remove('recording');
    }
  }

  async sendAudioToSTT(blob) {
    try {
      const reader = new FileReader();
      reader.onload = async () => {
        const base64Audio = reader.result.split(',')[1];
        const res = await fetch('/api/audio/transcribe-and-optimize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ audio_base64: base64Audio })
        });
        const data = await res.json();
        if (data && (data.optimized_prompt || data.transcription)) {
          const val = data.optimized_prompt || data.transcription;
          if (this.chatInput) {
            this.chatInput.value = this.chatInput.value ? `${this.chatInput.value} ${val}` : val;
            this.focusInput();
          }
        }
      };
      reader.readAsDataURL(blob);
    } catch (err) {
      console.warn('[ZeusChat] Erro no STT:', err);
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
      thinkDetails.innerHTML = `
        <summary class="zeus-thinking-summary">
          <span>💭 Raciocínio & Reflexão</span>
          <span class="think-badge">CONCLUÍDO</span>
        </summary>
        <div class="zeus-thinking-content thinking-text">${escapeHtml(msg.thinking).replace(/\n/g, '<br>')}</div>
      `;
      card.appendChild(thinkDetails);
    }

    // Ferramentas executadas se houver
    if (Array.isArray(msg.tools) && msg.tools.length > 0) {
      const toolsContainer = document.createElement('div');
      toolsContainer.className = 'zeus-tools-container';
      msg.tools.forEach(tool => {
        const item = document.createElement('div');
        item.className = 'zeus-tool-card type-exec';
        item.innerHTML = `
          <div class="zeus-tool-header">
            <span class="zeus-tool-name">🔧 ${escapeHtml(tool.name || 'Tool')}</span>
            <span class="zeus-tool-badge badge-exec">EXEC</span>
            <span class="zeus-tool-status status-success">OK</span>
          </div>
          <div class="zeus-tool-detail"><code>${escapeHtml(tool.detail || '')}</code></div>
        `;
        toolsContainer.appendChild(item);
      });
      card.appendChild(toolsContainer);
    }

    // Imagens se houver
    if (Array.isArray(msg.images) && msg.images.length > 0) {
      const grid = document.createElement('div');
      grid.className = 'zeus-message-images-grid';
      msg.images.forEach(dataUrl => {
        const img = document.createElement('img');
        img.src = dataUrl;
        img.className = 'zeus-message-image-preview';
        grid.appendChild(img);
      });
      card.appendChild(grid);
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
   * Envia a mensagem do usuário via streaming Server-Sent Events (SSE) real.
   * Trava o chat e o botão de envio durante o processamento, renderizando
   * blocos expansíveis de pensamento e ações de ferramentas em tempo real.
   */
  async sendMessage() {
    if (!this.chatInput) {
      if (this.paneEl) this.chatInput = this.paneEl.querySelector('.zeus-chat-input');
    }
    if (!this.chatInput) return;

    const text = this.chatInput.value.trim();
    if (!text && (!this.attachedImages || this.attachedImages.length === 0)) return;
    if (this.isProcessing) return;

    const attachedImgs = Array.isArray(this.attachedImages) ? [...this.attachedImages] : [];
    this.attachedImages = [];
    this.renderAttachmentsPreview();

    // 1. Trava o input e altera placeholder
    this.chatInput.value = '';
    this.chatInput.disabled = true;
    this.chatInput.placeholder = '⚡ Zeus pensando e orquestrando resposta...';

    // 2. Trava o botão de envio com spinner/indicador
    this.isProcessing = true;
    if (this.btnSend) {
      this.btnSend.disabled = true;
      this.btnSend.innerHTML = '<span>Pensando...</span> <span>⏳</span>';
    }

    const timestamp = new Date().toLocaleTimeString();

    // 3. Renderiza mensagem do usuário no chat
    this.renderMessage({
      role: 'user',
      author: 'Você',
      content: text,
      images: attachedImgs,
      timestamp
    });

    // 4. Cria o card do assistente em streaming ao vivo
    const liveMsg = this._createLiveAssistantCard();

    try {
      const selectedModel = this.selectedModel ||
        (this.modelSelect ? this.modelSelect.value : null) ||
        (typeof window !== 'undefined' && window.zeusChatUI ? window.zeusChatUI.selectedModel : 'auto') ||
        'auto';

      const payload = {
        message: text,
        session_id: this.sessionId || 'zeus-chat',
        model_id: selectedModel,
        images: attachedImgs,
        project_id: (typeof currentProjectId !== 'undefined' ? currentProjectId : null) || 'default',
        timestamp: new Date().toISOString()
      };

      const response = await fetch('/api/zeus-chat/message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `Erro HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let fullContent = '';
      let fullThinking = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;
          const jsonStr = trimmed.substring(5).trim();
          if (!jsonStr || jsonStr === '[DONE]') continue;

          try {
            const event = JSON.parse(jsonStr);
            this._handleLiveStreamEvent(event, liveMsg, {
              onThinking: (chunk) => { fullThinking += chunk; },
              onContent: (chunk) => { fullContent += chunk; }
            });
          } catch (err) {
            console.warn('[ZeusChat] Falha ao processar chunk SSE:', err, jsonStr);
          }
        }
      }

      this._finalizeLiveAssistantCard(liveMsg, fullContent, fullThinking);

    } catch (e) {
      console.warn('[ZeusChat] Falha no streaming:', e);
      if (liveMsg && liveMsg.body) {
        liveMsg.body.innerHTML = `<span style="color: var(--destructive, #ff6568); font-weight: 500;">❌ Erro: ${escapeHtml(e.message)}</span>`;
      }
      this.messages.push({
        role: 'error',
        author: 'Zeus Error',
        content: `❌ ${e.message}`,
        timestamp: new Date().toLocaleTimeString()
      });
    } finally {
      // 5. Destrava o chat e restaura o botão de envio
      this.isProcessing = false;
      if (this.chatInput) {
        this.chatInput.disabled = false;
        this.chatInput.placeholder = 'Comunique-se com o Orquestrador Zeus ou despache subagentes...';
      }
      if (this.btnSend) {
        this.btnSend.disabled = false;
        this.btnSend.innerHTML = '<span>Enviar</span> <span>⚡</span>';
      }
      this.focusInput();
    }
  }

  _createLiveAssistantCard() {
    if (!this.messagesContainer) {
      if (this.paneEl) this.messagesContainer = this.paneEl.querySelector('.zeus-chat-messages');
      if (!this.messagesContainer) return null;
    }

    const card = document.createElement('div');
    card.className = 'zeus-chat-msg role-assistant live-streaming';

    const header = document.createElement('div');
    header.className = 'zeus-msg-header';

    const authorWrap = document.createElement('div');
    authorWrap.className = 'zeus-msg-author-wrap';

    const iconImg = document.createElement('img');
    iconImg.src = '/zeus_terminal_god.svg';
    iconImg.className = 'zeus-msg-god-icon';
    iconImg.alt = 'Zeus';
    authorWrap.appendChild(iconImg);

    const authorSpan = document.createElement('strong');
    authorSpan.className = 'zeus-msg-author';
    authorSpan.textContent = 'Orquestrador Zeus';
    authorWrap.appendChild(authorSpan);

    const timeSpan = document.createElement('span');
    timeSpan.className = 'zeus-msg-time';
    timeSpan.textContent = new Date().toLocaleTimeString();

    header.appendChild(authorWrap);
    header.appendChild(timeSpan);
    card.appendChild(header);

    // Bloco retrátil de reflexão (Thinking)
    const thinkDetails = document.createElement('details');
    thinkDetails.className = 'zeus-thinking-box';
    thinkDetails.open = true;
    thinkDetails.style.display = 'none';

    const thinkSummary = document.createElement('summary');
    thinkSummary.className = 'zeus-thinking-summary';
    thinkSummary.innerHTML = `<span>💭 Raciocínio & Reflexão</span> <span class="think-badge">STREAMING</span>`;

    const thinkContent = document.createElement('div');
    thinkContent.className = 'zeus-thinking-content thinking-text';

    thinkDetails.appendChild(thinkSummary);
    thinkDetails.appendChild(thinkContent);
    card.appendChild(thinkDetails);

    // Container de Tools
    const toolsContainer = document.createElement('div');
    toolsContainer.className = 'zeus-tools-container';
    toolsContainer.style.display = 'none';
    card.appendChild(toolsContainer);

    // Corpo da mensagem
    const body = document.createElement('div');
    body.className = 'zeus-msg-body';
    body.innerHTML = '<span class="typing-indicator" style="opacity:0.7; font-style:italic;">⚡ Processando instrução...</span>';
    card.appendChild(body);

    this.messagesContainer.appendChild(card);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;

    return { card, thinkDetails, thinkSummary, thinkContent, toolsContainer, body, startedContent: false, toolsList: [] };
  }

  _handleLiveStreamEvent(event, liveMsg, callbacks) {
    if (!liveMsg || !event) return;

    if (event.type === 'thinking') {
      liveMsg.thinkDetails.style.display = 'block';
      liveMsg.thinkContent.textContent += event.text || '';
      if (callbacks.onThinking) callbacks.onThinking(event.text || '');
      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    } else if (event.type === 'tool_call') {
      liveMsg.toolsContainer.style.display = 'flex';
      liveMsg.toolsContainer.style.flexDirection = 'column';
      liveMsg.toolsContainer.style.gap = '6px';
      liveMsg.toolsContainer.style.margin = '6px 0';

      const toolEl = document.createElement('div');
      toolEl.className = 'zeus-tool-card type-exec';
      toolEl.innerHTML = `
        <div class="zeus-tool-header">
          <span class="zeus-tool-name">🔧 ${escapeHtml(event.tool || 'Ação')}</span>
          <span class="zeus-tool-badge badge-exec">EXEC</span>
          <span class="zeus-tool-status status-running">OK</span>
        </div>
        <div class="zeus-tool-detail"><code>${escapeHtml(JSON.stringify(event.params || {}))}</code></div>
      `;
      liveMsg.toolsContainer.appendChild(toolEl);
      liveMsg.toolsList.push({ name: event.tool, detail: JSON.stringify(event.params || {}) });
      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    } else if (event.type === 'subagent_spawn') {
      this.handleSubagentSpawn(event);
    } else if (event.type === 'content') {
      if (!liveMsg.startedContent) {
        liveMsg.body.innerHTML = '';
        liveMsg.startedContent = true;
      }
      liveMsg.body.innerHTML += escapeHtml(event.text || '').replace(/\n/g, '<br>');
      if (callbacks.onContent) callbacks.onContent(event.text || '');
      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    } else if (event.type === 'done') {
      const badge = liveMsg.thinkSummary.querySelector('.think-badge');
      if (badge) badge.textContent = 'CONCLUÍDO';
      if (liveMsg.thinkContent.textContent.trim()) {
        liveMsg.thinkDetails.open = false;
      }
      const metricsDiv = document.createElement('div');
      metricsDiv.className = 'zeus-msg-metrics';
      metricsDiv.style.cssText = 'font-size: 11px; color: var(--text-muted, #71717a); margin-top: 8px; opacity: 0.85; font-family: monospace;';
      metricsDiv.textContent = `⚡ Concluído em ${event.duration_seconds || '0.1'}s · ${event.tokens || 0} tokens · backend: ${event.backend || 'zeus'}`;
      liveMsg.card.appendChild(metricsDiv);
      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    } else if (event.type === 'error') {
      liveMsg.body.innerHTML += `<div style="color: var(--destructive, #ff6568); font-weight: 600; margin-top: 6px;">❌ ${escapeHtml(event.message || 'Erro no processamento.')}</div>`;
    }
  }

  _finalizeLiveAssistantCard(liveMsg, fullContent, fullThinking) {
    if (!liveMsg) return;
    liveMsg.card.classList.remove('live-streaming');
    this.messages.push({
      role: 'assistant',
      author: 'Orquestrador Zeus',
      content: fullContent || (liveMsg.body ? liveMsg.body.textContent : ''),
      thinking: fullThinking || (liveMsg.thinkContent ? liveMsg.thinkContent.textContent : null),
      tools: liveMsg.toolsList || [],
      timestamp: new Date().toLocaleTimeString()
    });
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
      description,
      meta,
      timestamp: new Date().toLocaleTimeString()
    };

    this.subagents.set(subagentId, normalized);

    if (this.messagesContainer) {
      let existingCard = document.getElementById(`subagent-card-${subagentId}`);
      if (!existingCard) {
        existingCard = document.createElement('div');
        existingCard.id = `subagent-card-${subagentId}`;
        existingCard.className = 'zeus-subagent-card';
        this.messagesContainer.appendChild(existingCard);
      }

      existingCard.innerHTML = `
        <div class="zeus-subagent-card-header">
          <div class="subagent-title-wrap">
            <span class="subagent-icon">${meta.icon}</span>
            <strong class="subagent-name">${escapeHtml(title)}</strong>
            <span class="subagent-badge role-${roleType}">${escapeHtml(roleType.toUpperCase())}</span>
          </div>
          <span class="subagent-status status-${status.toLowerCase()}" id="chat-badge-${subagentId}">${status}</span>
        </div>
        <div class="zeus-subagent-card-body">
          <p class="subagent-task-desc">${escapeHtml(description)}</p>
          <div class="subagent-meta-info">
            <span class="meta-tag">⚡ Fatia: <code>${escapeHtml(sliceId)}</code></span>
            <span class="meta-tag">🛠️ Motor: <code>${escapeHtml(agentType)}</code></span>
          </div>
        </div>
        <div class="zeus-subagent-card-actions">
          <button type="button" class="action-btn primary btn-sm btn-open-subagent-terminal" data-subagent-id="${subagentId}" title="Focar ou abrir aba dedicada do subagente sem fechar a sessão de chat">
            <span>Terminal do Subagente</span>
            <span>↗</span>
          </button>
        </div>
      `;

      const btnOpen = existingCard.querySelector('.btn-open-subagent-terminal');
      if (btnOpen) {
        btnOpen.addEventListener('click', (e) => {
          e.stopPropagation();
          this.navigateToSubagentTab(normalized);
        });
      }

      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
  }

  navigateToSubagentTab(subagentData) {
    const subagentId = subagentData.id || subagentData.subagentId;
    let record = null;
    if (typeof openSubagentTab === 'function') {
      record = openSubagentTab(subagentData);
    } else if (typeof window !== 'undefined' && typeof window.openSubagentTab === 'function') {
      record = window.openSubagentTab(subagentData);
    }

    const targetId = (record && record.id) || subagentId;
    if (typeof focusSubagentTab === 'function') {
      focusSubagentTab(targetId);
    } else if (typeof window !== 'undefined' && typeof window.focusSubagentTab === 'function') {
      window.focusSubagentTab(targetId);
    } else if (typeof terminalWorkspace !== 'undefined' && record && record.session) {
      terminalWorkspace.selectSession(record.session.id, true);
    }

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

if (typeof window !== 'undefined') {
  window.zeusChatWorkspace = zeusChatWorkspace;
  window.openOrCreateChatSession = openOrCreateChatSession;
  window.openZeusChat = () => zeusChatWorkspace.openOrCreateChatSession();
  window.initZeusChatWorkspace = initZeusChatWorkspace;
}
