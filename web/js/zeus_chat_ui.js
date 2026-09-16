/**
 * Zeus Chat UI - Interface de Chat Conversacional Avançada
 * Issue #24 (Fatia 3): Raciocínio Expansível, Tool Calls Especializados,
 * Seletor Contextual de Modelos, Popover de Skills & MCPs, STT com Microfone
 * e Anexos Multimodais com Validação de Visão.
 */

import { escapeHtml, showToast } from './ui_utils.js';
import { apiFetch, currentProjectId, state } from './state.js';

// Fallbacks seguros para ambientes de teste sem imports DOM
const safeEscapeHtml = (str) => {
  if (typeof escapeHtml === 'function') return escapeHtml(str);
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

const safeShowToast = (msg, type = 'info') => {
  if (typeof showToast === 'function') showToast(msg, type);
  else console.log(`[Toast ${type}] ${msg}`);
};

const safeApiFetch = async (endpoint, options) => {
  if (typeof apiFetch === 'function') {
    return apiFetch(endpoint, options);
  }
  return fetch(endpoint, options);
};

export class ZeusChatUI {
  constructor() {
    this.container = null;
    this.messagesContainer = null;
    this.chatInput = null;
    this.btnSend = null;
    this.btnClear = null;
    this.btnClose = null;
    this.statusBadge = null;

    // Novos Controles Issue #24
    this.modelSelect = null;
    this.btnSkills = null;
    this.skillsPopover = null;
    this.skillsBadgeCount = null;
    this.btnMic = null;
    this.btnAttach = null;
    this.fileInput = null;
    this.attachmentsPreview = null;
    this.modelWarning = null;

    // Estados internos
    this.isProcessing = false;
    this.isRecording = false;
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.attachedImages = [];
    this.selectedModel = 'gpt-4o';
    this.availableModels = [];
    this.selectedSkills = new Set();
    this.selectedMcps = new Set();
    this.messages = [];
    this.activeThinkingBox = null;
  }

  init() {
    // Busca por contêineres zeus ou fallback opencode para manter compatibilidade total
    this.container = document.getElementById('zeus-chat-container') || document.getElementById('opencode-visual-chat-container');
    this.messagesContainer = document.getElementById('zeus-chat-messages') || document.getElementById('opencode-chat-messages');
    this.chatInput = document.getElementById('zeus-chat-input') || document.getElementById('opencode-chat-input');
    this.btnSend = document.getElementById('btn-send-zeus-chat') || document.getElementById('btn-send-opencode-chat');
    this.btnClear = document.getElementById('btn-clear-zeus-chat') || document.getElementById('btn-clear-opencode-chat');
    this.btnClose = document.getElementById('btn-close-zeus-chat') || document.getElementById('btn-close-opencode-chat');
    this.statusBadge = document.getElementById('zeus-chat-status') || document.getElementById('opencode-chat-status');

    // Controles especializados da Issue #24
    this.modelSelect = document.getElementById('zeus-model-select');
    this.btnSkills = document.getElementById('btn-zeus-skills-mcps');
    this.skillsPopover = document.getElementById('zeus-skills-popover');
    this.skillsBadgeCount = document.getElementById('zeus-skills-badge-count');
    this.btnMic = document.getElementById('btn-zeus-mic') || document.querySelector('.zeus-btn-mic');
    this.btnAttach = document.getElementById('btn-zeus-attach-img');
    this.fileInput = document.getElementById('zeus-file-input');
    this.attachmentsPreview = document.getElementById('zeus-attachments-preview');
    this.modelWarning = document.getElementById('zeus-model-warning');

    if (!this.container) {
      return;
    }

    this._bindEvents();
    this.loadAvailableModels();
    this.loadCustomizations();

    // Mensagem inicial de boas-vindas se vazio
    if (this.messagesContainer && this.messagesContainer.children.length === 0) {
      this.renderMessage({
        role: 'assistant',
        author: 'ZEUS AGENT Core',
        content: '⚡ Olá! Sou o motor de IA e orquestração do ZEUS Agent. Envie instruções, anexe imagens ou use o microfone.',
        timestamp: new Date().toLocaleTimeString()
      });
    }
  }

  _bindEvents() {
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

      // Anexo por Clipboard Paste (Ctrl+V)
      this.chatInput.addEventListener('paste', (e) => this.handlePaste(e));
    }

    // Drag-and-drop de arquivos na área de chat
    if (this.container) {
      this.container.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.container.classList.add('drag-over');
      });

      this.container.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.container.classList.remove('drag-over');
      });

      this.container.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.container.classList.remove('drag-over');
        this.handleDrop(e);
      });
    }

    if (this.btnClear) {
      this.btnClear.addEventListener('click', () => this.clearMessages());
    }

    if (this.btnClose) {
      this.btnClose.addEventListener('click', () => this.close());
    }

    // Seletor de Modelo
    if (this.modelSelect) {
      this.modelSelect.addEventListener('change', (e) => {
        this.selectedModel = e.target.value;
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem('zeus_selected_model', this.selectedModel);
        }
        this.validateMultimodalInput();
      });
    }

    // Popover de Skills e MCPs
    if (this.btnSkills && this.skillsPopover) {
      this.btnSkills.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = this.skillsPopover.style.display === 'block';
        this.skillsPopover.style.display = isOpen ? 'none' : 'block';
      });

      document.addEventListener('click', (e) => {
        if (this.skillsPopover && !this.skillsPopover.contains(e.target) && e.target !== this.btnSkills) {
          this.skillsPopover.style.display = 'none';
        }
      });
    }

    // Microfone STT
    if (this.btnMic) {
      this.btnMic.addEventListener('click', () => this.toggleRecording());
    }

    // Botão de Anexo de Imagens
    if (this.btnAttach && this.fileInput) {
      this.btnAttach.addEventListener('click', () => {
        this.fileInput.click();
      });
    }

    if (this.fileInput) {
      this.fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
          Array.from(e.target.files).forEach(file => this.addAttachedImage(file));
          e.target.value = '';
        }
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

  openChat() {
    this.open();
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
        content: 'Histórico de mensagens limpo.',
        timestamp: new Date().toLocaleTimeString()
      });
    }
  }

  setStatus(statusText, type = 'ready') {
    if (this.statusBadge) {
      this.statusBadge.textContent = statusText;
      this.statusBadge.className = `zeus-chat-badge opencode-chat-badge status-${type}`;
    }
  }

  // ==========================================
  // SELETOR CONTEXTUAL DE MODELOS & VISÃO
  // ==========================================

  isVisionSupported(modelName) {
    if (!modelName) return false;
    const name = String(modelName).toLowerCase();

    // Modelos que explicitamente possuem suporte a visão multimodal
    const visionKeywords = [
      'gpt-4o',
      'gpt-4-turbo',
      'gemini',
      'claude-3',
      'claude-3-5',
      'claude-3-opus',
      'claude-3-sonnet',
      'claude-3-haiku',
      'llava',
      'bakllava',
      'vision',
      'multimodal',
      'pixtral',
      'qwen-vl',
      'minicpm-v',
      'llama-3.2-11b-vision',
      'llama-3.2-90b-vision'
    ];

    // Modelos puramente texto ou código que NÃO suportam visão
    const textOnlyKeywords = [
      'coder',
      'gpt-3.5',
      'gpt-35',
      'deepseek-chat',
      'deepseek-coder',
      'llama-3-8b',
      'llama-3-70b',
      'llama3:8b',
      'llama3:latest',
      'mistral:7b',
      'codellama',
      'qwen2.5-coder'
    ];

    for (const kw of textOnlyKeywords) {
      if (name.includes(kw) && !name.includes('vision')) {
        return false;
      }
    }

    for (const kw of visionKeywords) {
      if (name.includes(kw)) {
        return true;
      }
    }

    // Checagem no array de modelos carregados caso tenha flag explícita
    const found = this.availableModels.find(m => (m.id || m.name || '').toLowerCase() === name);
    if (found && (found.supports_vision || found.vision || (found.capabilities && found.capabilities.includes('vision')))) {
      return true;
    }

    return false;
  }

  async loadAvailableModels() {
    const modelsList = [];

    // 1. Modelos Cloud OmniRoute (/api/omniroute/connectors)
    try {
      const resOmni = await safeApiFetch('/api/omniroute/connectors');
      const data = typeof resOmni.json === 'function' ? await resOmni.json() : resOmni;
      const connectors = data.connectors || (Array.isArray(data) ? data : []);
      connectors.forEach(c => {
        if (c.models && Array.isArray(c.models)) {
          c.models.forEach(m => {
            const mId = typeof m === 'string' ? m : (m.id || m.name);
            const mName = typeof m === 'string' ? m : (m.name || m.id);
            const isVision = this.isVisionSupported(mId);
            modelsList.push({
              id: mId,
              name: `${mName} (${c.provider || c.name || 'Cloud'})`,
              provider: c.provider || 'OmniRoute',
              supports_vision: isVision
            });
          });
        }
      });
    } catch (e) {
      console.warn('[ZeusChatUI] Não foi possível carregar /api/omniroute/connectors:', e);
    }

    // 2. Modelos Locais Ollama / Local Worker (/api/local-worker/models)
    try {
      const resLocal = await safeApiFetch('/api/local-worker/models');
      const data = typeof resLocal.json === 'function' ? await resLocal.json() : resLocal;
      const localModels = data.models || (Array.isArray(data) ? data : []);
      localModels.forEach(m => {
        const mId = typeof m === 'string' ? m : (m.name || m.id);
        const isVision = this.isVisionSupported(mId);
        modelsList.push({
          id: mId,
          name: `${mId} (Local Worker)`,
          provider: 'Local Worker',
          supports_vision: isVision
        });
      });
    } catch (e) {
      console.warn('[ZeusChatUI] Não foi possível carregar /api/local-worker/models:', e);
    }

    // Se nenhum modelo foi retornado (ex: sem backend no teste), fornece catálogo padrão representativo
    if (modelsList.length === 0) {
      modelsList.push(
        { id: 'gpt-4o', name: 'GPT-4o (OpenAI Omni)', provider: 'OpenAI', supports_vision: true },
        { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet (Anthropic)', provider: 'Anthropic', supports_vision: true },
        { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro (Google)', provider: 'Google', supports_vision: true },
        { id: 'deepseek-coder:6.7b', name: 'DeepSeek Coder 6.7B (Local)', provider: 'Local Worker', supports_vision: false },
        { id: 'qwen2.5-coder:7b', name: 'Qwen 2.5 Coder 7B (Local)', provider: 'Local Worker', supports_vision: false }
      );
    }

    this.availableModels = modelsList;
    this.renderModelSelectorOptions();
  }

  renderModelSelectorOptions() {
    if (!this.modelSelect) return;

    const savedModel = (typeof localStorage !== 'undefined' && localStorage.getItem('zeus_selected_model')) || this.selectedModel || 'gpt-4o';
    this.modelSelect.innerHTML = '';

    const groupCloud = document.createElement('optgroup');
    groupCloud.label = 'Provedores OmniRoute / Cloud';

    const groupLocal = document.createElement('optgroup');
    groupLocal.label = 'Local Worker / Ollama';

    this.availableModels.forEach(model => {
      const opt = document.createElement('option');
      opt.value = model.id;
      const visionTag = model.supports_vision ? ' 👁️ [Visão]' : '';
      opt.textContent = `${model.name}${visionTag}`;
      opt.setAttribute('data-supports-vision', model.supports_vision ? 'true' : 'false');

      if (model.id === savedModel) {
        opt.selected = true;
        this.selectedModel = model.id;
      }

      if (model.provider === 'Local Worker') {
        groupLocal.appendChild(opt);
      } else {
        groupCloud.appendChild(opt);
      }
    });

    if (groupCloud.children.length > 0) this.modelSelect.appendChild(groupCloud);
    if (groupLocal.children.length > 0) this.modelSelect.appendChild(groupLocal);

    if (!this.selectedModel && this.availableModels.length > 0) {
      this.selectedModel = this.availableModels[0].id;
    }

    this.validateMultimodalInput();
  }

  // ==========================================
  // DROPDOWN / POPOVER DE SKILLS & MCPS
  // ==========================================

  async loadCustomizations() {
    try {
      const pId = typeof currentProjectId !== 'undefined' ? currentProjectId : 'default';
      const [resMcp, resSkills] = await Promise.all([
        safeApiFetch(`/api/customizations/mcp?project_id=${encodeURIComponent(pId)}`).catch(() => null),
        safeApiFetch(`/api/customizations/skills?project_id=${encodeURIComponent(pId)}`).catch(() => null)
      ]);

      let mcps = [];
      let skills = [];

      if (resMcp) {
        const dataMcp = typeof resMcp.json === 'function' ? await resMcp.json() : resMcp;
        mcps = dataMcp.mcp || (Array.isArray(dataMcp) ? dataMcp : []);
      }

      if (resSkills) {
        const dataSkills = typeof resSkills.json === 'function' ? await resSkills.json() : resSkills;
        skills = dataSkills.skills || (Array.isArray(dataSkills) ? dataSkills : []);
      }

      this.renderSkillsPopoverList(mcps, skills);
    } catch (e) {
      console.warn('[ZeusChatUI] Falha ao carregar customizações para popover:', e);
      // Fallback gracioso
      this.renderSkillsPopoverList([], []);
    }
  }

  renderSkillsPopoverList(mcps = [], skills = []) {
    if (!this.skillsPopover) return;

    this.skillsPopover.innerHTML = `
      <div class="zeus-popover-header">
        <span class="zeus-popover-title">⚡ Skills & Servidores MCP</span>
        <button type="button" class="zeus-popover-close" id="btn-close-zeus-popover">✕</button>
      </div>
      <div class="zeus-popover-body">
        <div class="zeus-popover-section">
          <div class="zeus-section-title">🛠️ Servidores MCP</div>
          <div class="zeus-checkbox-list" id="zeus-mcp-checkbox-list"></div>
        </div>
        <div class="zeus-popover-section">
          <div class="zeus-section-title">💡 Skills do Cockpit</div>
          <div class="zeus-checkbox-list" id="zeus-skills-checkbox-list"></div>
        </div>
      </div>
    `;

    const btnClose = this.skillsPopover.querySelector('#btn-close-zeus-popover');
    if (btnClose) {
      btnClose.addEventListener('click', () => {
        this.skillsPopover.style.display = 'none';
      });
    }

    const mcpListEl = this.skillsPopover.querySelector('#zeus-mcp-checkbox-list');
    const skillsListEl = this.skillsPopover.querySelector('#zeus-skills-checkbox-list');

    // Renderiza MCPs
    if (mcps.length === 0) {
      mcpListEl.innerHTML = '<div class="zeus-empty-text">Nenhum servidor MCP configurado</div>';
    } else {
      mcps.forEach(mcp => {
        const item = document.createElement('label');
        item.className = 'zeus-checkbox-item';
        const isChecked = mcp.enabled !== false;
        if (isChecked) this.selectedMcps.add(mcp.id || mcp.name);

        item.innerHTML = `
          <input type="checkbox" class="zeus-checkbox" data-mcp-id="${safeEscapeHtml(mcp.id || mcp.name)}" ${isChecked ? 'checked' : ''}>
          <span class="checkbox-label">${safeEscapeHtml(mcp.name || mcp.id)}</span>
        `;

        const chk = item.querySelector('input');
        chk.addEventListener('change', (e) => {
          const id = e.target.getAttribute('data-mcp-id');
          if (e.target.checked) this.selectedMcps.add(id);
          else this.selectedMcps.delete(id);
          this.updateSkillsBadgeCount();
        });

        mcpListEl.appendChild(item);
      });
    }

    // Renderiza Skills
    if (skills.length === 0) {
      skillsListEl.innerHTML = '<div class="zeus-empty-text">Nenhuma skill encontrada</div>';
    } else {
      skills.forEach(sk => {
        const item = document.createElement('label');
        item.className = 'zeus-checkbox-item';
        const isChecked = sk.enabled !== false;
        if (isChecked) this.selectedSkills.add(sk.name);

        item.innerHTML = `
          <input type="checkbox" class="zeus-checkbox" data-skill-name="${safeEscapeHtml(sk.name)}" ${isChecked ? 'checked' : ''}>
          <span class="checkbox-label">${safeEscapeHtml(sk.name)}</span>
        `;

        const chk = item.querySelector('input');
        chk.addEventListener('change', (e) => {
          const name = e.target.getAttribute('data-skill-name');
          if (e.target.checked) this.selectedSkills.add(name);
          else this.selectedSkills.delete(name);
          this.updateSkillsBadgeCount();
        });

        skillsListEl.appendChild(item);
      });
    }

    this.updateSkillsBadgeCount();
  }

  updateSkillsBadgeCount() {
    const total = this.selectedSkills.size + this.selectedMcps.size;
    if (this.skillsBadgeCount) {
      this.skillsBadgeCount.textContent = String(total);
      this.skillsBadgeCount.style.display = total > 0 ? 'inline-block' : 'none';
    }
  }

  getSelectedCustomizations() {
    return {
      skills: Array.from(this.selectedSkills),
      mcps: Array.from(this.selectedMcps)
    };
  }

  // ==========================================
  // CAPTURA DE ÁUDIO & STT COM MICROFONE
  // ==========================================

  async toggleRecording() {
    if (this.isRecording) {
      this.stopRecording();
    } else {
      await this.startRecording();
    }
  }

  async startRecording() {
    if (!navigator || !navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
      safeShowToast('Microfone não suportado pelo navegador.', 'error');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.audioChunks = [];
      this.mediaRecorder = new MediaRecorder(stream);

      this.mediaRecorder.addEventListener('dataavailable', (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      });

      this.mediaRecorder.addEventListener('stop', async () => {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        // Para todas as tracks do microfone
        stream.getTracks().forEach(t => t.stop());
        await this.sendAudioForTranscription(audioBlob);
      });

      this.mediaRecorder.start();
      this.isRecording = true;

      if (this.btnMic) {
        this.btnMic.classList.add('recording');
        this.btnMic.title = 'Gravando... Clique para parar';
      }
      this.setStatus('Gravando áudio...', 'busy');
    } catch (err) {
      console.error('[ZeusChatUI] Erro ao acessar microfone:', err);
      safeShowToast(`Erro ao acessar microfone: ${err.message}`, 'error');
      this.isRecording = false;
      if (this.btnMic) this.btnMic.classList.remove('recording');
      this.setStatus('Pronto', 'ready');
    }
  }

  stopRecording() {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();
      this.isRecording = false;
      if (this.btnMic) {
        this.btnMic.classList.remove('recording');
        this.btnMic.title = 'Gravar áudio (STT)';
      }
      this.setStatus('Processando transcrição...', 'busy');
    }
  }

  async sendAudioForTranscription(audioBlob) {
    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'prompt_audio.webm');
      if (typeof currentProjectId !== 'undefined') {
        formData.append('project_id', currentProjectId);
      }

      const res = await safeApiFetch('/api/audio/transcribe-and-optimize', {
        method: 'POST',
        body: formData
      });

      const data = typeof res.json === 'function' ? await res.json() : res;

      if (data && (data.optimized_prompt || data.prompt || data.text)) {
        const transcribedText = data.optimized_prompt || data.prompt || data.text;
        if (this.chatInput) {
          const currentVal = this.chatInput.value.trim();
          this.chatInput.value = currentVal ? `${currentVal} ${transcribedText}` : transcribedText;
          this.chatInput.focus();
        }
        safeShowToast('Áudio transcrito com sucesso!', 'success');
      } else if (data && data.error) {
        safeShowToast(`Erro na transcrição: ${data.error}`, 'error');
      }
    } catch (err) {
      console.warn('[ZeusChatUI] Falha na transcrição via /api/audio/transcribe-and-optimize:', err);
      safeShowToast(`Falha de comunicação no STT: ${err.message}`, 'error');
    } finally {
      this.setStatus('Pronto', 'ready');
    }
  }

  // ==========================================
  // MULTIMODALIDADE & ANEXO DE IMAGENS
  // ==========================================

  addAttachedImage(file) {
    if (!file || !file.type || !file.type.startsWith('image/')) {
      safeShowToast('Apenas arquivos de imagem são suportados.', 'warning');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target.result;
      const imgObj = {
        id: 'img_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5),
        name: file.name,
        size: file.size,
        dataUrl,
        file
      };
      this.attachedImages.push(imgObj);
      this.renderAttachmentsPreview();
      this.validateMultimodalInput();
    };
    reader.readAsDataURL(file);
  }

  removeAttachedImage(idOrIndex) {
    if (typeof idOrIndex === 'number') {
      this.attachedImages.splice(idOrIndex, 1);
    } else {
      this.attachedImages = this.attachedImages.filter(img => img.id !== idOrIndex);
    }
    this.renderAttachmentsPreview();
    this.validateMultimodalInput();
  }

  renderAttachmentsPreview() {
    if (!this.attachmentsPreview) return;

    this.attachmentsPreview.innerHTML = '';
    if (this.attachedImages.length === 0) {
      this.attachmentsPreview.style.display = 'none';
      return;
    }

    this.attachmentsPreview.style.display = 'flex';
    this.attachedImages.forEach((img, idx) => {
      const thumb = document.createElement('div');
      thumb.className = 'zeus-attachment-thumb';
      thumb.innerHTML = `
        <img src="${img.dataUrl}" alt="${safeEscapeHtml(img.name)}" class="thumb-img" />
        <button type="button" class="btn-remove-thumb zeus-thumb-remove" title="Remover imagem" data-index="${idx}">✕</button>
      `;

      const btnRemove = thumb.querySelector('.btn-remove-thumb');
      btnRemove.addEventListener('click', (e) => {
        e.stopPropagation();
        this.removeAttachedImage(img.id || idx);
      });

      this.attachmentsPreview.appendChild(thumb);
    });
  }

  validateMultimodalInput() {
    if (this.attachedImages.length > 0) {
      const modelSupportsVision = this.isVisionSupported(this.selectedModel);
      if (!modelSupportsVision) {
        if (this.modelWarning) {
          this.modelWarning.style.display = 'flex';
          this.modelWarning.className = 'zeus-model-warning zeus-vision-error badge-danger';
          this.modelWarning.innerHTML = `
            <span>⚠️ O modelo <strong>${safeEscapeHtml(this.selectedModel || 'atual')}</strong> não suporta visão. Escolha um modelo multimodal (ex: GPT-4o, Gemini ou Claude 3.5) ou remova a imagem para enviar.</span>
          `;
        }
        return {
          valid: false,
          reason: 'vision_not_supported',
          model: this.selectedModel
        };
      }
    }

    // Se estiver válido, oculta aviso
    if (this.modelWarning) {
      this.modelWarning.style.display = 'none';
      this.modelWarning.innerHTML = '';
    }
    return { valid: true };
  }

  handlePaste(e) {
    if (!e.clipboardData || !e.clipboardData.items) return;
    const items = e.clipboardData.items;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const file = items[i].getAsFile();
        if (file) {
          e.preventDefault();
          this.addAttachedImage(file);
          safeShowToast('Imagem colada da área de transferência!', 'info');
        }
      }
    }
  }

  handleDrop(e) {
    if (!e.dataTransfer || !e.dataTransfer.files) return;
    const files = Array.from(e.dataTransfer.files);
    let count = 0;
    files.forEach(file => {
      if (file.type && file.type.startsWith('image/')) {
        this.addAttachedImage(file);
        count++;
      }
    });
    if (count > 0) {
      safeShowToast(`${count} imagem(ns) adicionada(s) via arrastar e soltar.`, 'info');
    }
  }

  // ==========================================
  // RENDERIZAÇÃO: PENSAMENTOS & TOOL CALLS
  // ==========================================

  createThinkingBox(content = '', isStreaming = false) {
    const thinkBox = document.createElement('details');
    thinkBox.className = 'zeus-thinking-box opencode-thinking-box';

    // Auto-expansão durante streaming
    if (isStreaming) {
      thinkBox.open = true;
      thinkBox.setAttribute('open', '');
    }

    const thinkSummary = document.createElement('summary');
    thinkSummary.className = 'zeus-thinking-summary';
    thinkSummary.innerHTML = `
      <span class="think-icon">💭</span>
      <span class="think-title">Raciocínio / Pensamento interno</span>
      <span class="think-badge">${isStreaming ? 'Calculando...' : 'Expandir'}</span>
    `;

    const thinkContent = document.createElement('div');
    thinkContent.className = 'thinking-text';
    thinkContent.innerHTML = safeEscapeHtml(content);

    thinkBox.appendChild(thinkSummary);
    thinkBox.appendChild(thinkContent);
    return thinkBox;
  }

  appendThinkingChunk(chunkText) {
    if (!this.activeThinkingBox) return;
    const contentDiv = this.activeThinkingBox.querySelector('.thinking-text');
    if (contentDiv) {
      contentDiv.innerHTML += safeEscapeHtml(chunkText);
    }
    this.activeThinkingBox.open = true;
  }

  createToolCard(tool = {}) {
    const card = document.createElement('div');
    card.className = 'zeus-tool-card opencode-tool-card';

    const toolName = (tool.name || tool.tool || 'tool').toLowerCase();
    let badgeType = 'TOOL';
    let icon = '🔧';
    let typeClass = 'type-generic';

    if (toolName.includes('read') || toolName.includes('get') || toolName.includes('view') || toolName.includes('list')) {
      badgeType = 'READ';
      icon = '📖';
      typeClass = 'type-read';
    } else if (toolName.includes('write') || toolName.includes('edit') || toolName.includes('replace') || toolName.includes('create')) {
      badgeType = 'WRITE';
      icon = '✏️';
      typeClass = 'type-write';
    } else if (toolName.includes('bash') || toolName.includes('cmd') || toolName.includes('exec') || toolName.includes('command') || toolName.includes('terminal')) {
      badgeType = 'EXEC';
      icon = '⚡';
      typeClass = 'type-exec';
    }

    const status = tool.status || 'success';
    card.classList.add(typeClass);

    card.innerHTML = `
      <div class="zeus-tool-header">
        <span class="zeus-tool-icon">${icon}</span>
        <span class="zeus-tool-name">${safeEscapeHtml(tool.name || 'Tool')}</span>
        <span class="zeus-tool-badge tool-badge badge-${badgeType.toLowerCase()}">${badgeType}</span>
        <span class="zeus-tool-status tool-status status-${status}">${status.toUpperCase()}</span>
      </div>
      <div class="zeus-tool-detail">
        <code>${safeEscapeHtml(tool.detail || tool.path || tool.command || '')}</code>
      </div>
      ${tool.output ? `<div class="zeus-tool-output"><code>${safeEscapeHtml(tool.output)}</code></div>` : ''}
    `;

    return card;
  }

  renderMessage({
    role = 'assistant',
    author = 'ZEUS',
    content = '',
    thinking = null,
    tools = [],
    images = [],
    timestamp = ''
  }) {
    if (!this.messagesContainer) return;

    const msgObj = { role, author, content, thinking, tools, images, timestamp };
    this.messages.push(msgObj);

    const card = document.createElement('div');
    card.className = `zeus-chat-card opencode-chat-card role-${role}`;

    const header = document.createElement('div');
    header.className = 'zeus-card-header opencode-card-header';

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

    // Bloco de Raciocínio Expansível
    if (thinking) {
      const thinkBox = this.createThinkingBox(thinking, false);
      card.appendChild(thinkBox);
    }

    // Cards de Tool Calls
    if (Array.isArray(tools) && tools.length > 0) {
      const toolsBox = document.createElement('div');
      toolsBox.className = 'zeus-tools-container opencode-tools-box';
      tools.forEach(tool => {
        const toolCard = this.createToolCard(tool);
        toolsBox.appendChild(toolCard);
      });
      card.appendChild(toolsBox);
    }

    // Imagens anexadas na mensagem
    if (Array.isArray(images) && images.length > 0) {
      const imagesGrid = document.createElement('div');
      imagesGrid.className = 'zeus-message-images-grid';
      images.forEach(imgUrl => {
        const imgEl = document.createElement('img');
        imgEl.src = imgUrl;
        imgEl.className = 'zeus-message-image-preview';
        imgEl.alt = 'Imagem enviada';
        imagesGrid.appendChild(imgEl);
      });
      card.appendChild(imagesGrid);
    }

    // Corpo de texto
    const body = document.createElement('div');
    body.className = 'zeus-card-body opencode-card-body';
    body.innerHTML = safeEscapeHtml(content).replace(/\n/g, '<br>');
    card.appendChild(body);

    this.messagesContainer.appendChild(card);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }

  // ==========================================
  // DISPARO & FLUXO DE MENSAGENS
  // ==========================================

  async sendMessage() {
    if (!this.chatInput) return;
    const text = this.chatInput.value.trim();

    // Validação multimodal: se modelo não aceitar visão e houver imagem anexada, bloqueia
    const validation = this.validateMultimodalInput();
    if (!validation.valid) {
      safeShowToast('Modelo selecionado não suporta imagens. Escolha um modelo multimodal ou remova a imagem.', 'error');
      return;
    }

    if (!text && this.attachedImages.length === 0) return;
    if (this.isProcessing) return;

    // Preserva dados e limpa input
    const msgImages = this.attachedImages.map(img => img.dataUrl);
    this.chatInput.value = '';
    this.attachedImages = [];
    this.renderAttachmentsPreview();

    // Renderiza mensagem do usuário
    const timestamp = new Date().toLocaleTimeString();
    this.renderMessage({
      role: 'user',
      author: 'Você',
      content: text,
      images: msgImages,
      timestamp
    });

    this.isProcessing = true;
    this.setStatus('Pensando...', 'busy');

    try {
      const payload = {
        message: text,
        model: this.selectedModel,
        skills: Array.from(this.selectedSkills),
        mcp_servers: Array.from(this.selectedMcps),
        images: msgImages,
        project_id: typeof currentProjectId !== 'undefined' ? currentProjectId : null,
        timestamp: new Date().toISOString()
      };

      const response = await safeApiFetch('/api/opencode/headless/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = typeof response.json === 'function' ? await response.json() : response;

      if (data && (data.reply || data.message)) {
        this.renderMessage({
          role: 'assistant',
          author: data.author || 'ZEUS Agent',
          content: data.reply || data.message,
          thinking: data.thinking || null,
          tools: data.tools || [],
          timestamp: new Date().toLocaleTimeString()
        });
      } else if (data && data.error) {
        this.renderMessage({
          role: 'error',
          author: 'Erro Zeus',
          content: `❌ Erro: ${data.error}`,
          timestamp: new Date().toLocaleTimeString()
        });
      } else {
        this.renderMessage({
          role: 'assistant',
          author: 'ZEUS Agent',
          content: 'Instrução recebida e processada com sucesso.',
          timestamp: new Date().toLocaleTimeString()
        });
      }
    } catch (err) {
      console.warn('[ZeusChatUI] Erro ao enviar mensagem:', err);
      this.renderMessage({
        role: 'error',
        author: 'Falha de Comunicação',
        content: `Não foi possível conectar ao motor Zeus: ${err.message}`,
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
}

export const zeusChatUI = new ZeusChatUI();

export function initZeusChatUI() {
  zeusChatUI.init();
}

// Expõe globalmente para compatibilidade de testes, scripts e index.html
if (typeof window !== 'undefined') {
  window.ZeusChatUI = ZeusChatUI;
  window.zeusChatUI = zeusChatUI;
  window.initZeusChatUI = initZeusChatUI;
}
