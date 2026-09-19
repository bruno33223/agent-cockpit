/**
 * ZeusChatUI - Casca leve do painel flutuante/modal do Zeus Chat.
 * Issue #34 (Deduplicação e Arquitetura Modular do Zeus Chat)
 */

import { escapeHtml, showToast } from './ui_utils.js';
import { apiFetch, currentProjectId } from './state.js';
import { ZeusChatCore } from './chat/zeus_chat_core.js';
import { MessageRenderer } from './chat/message_renderer.js';
import { SubagentCardRenderer } from './chat/subagent_card_renderer.js';

export class ZeusChatUI {
  constructor() {
    this.container = null;
    this.messagesContainer = null;
    this.chatInput = null;
    this.btnSend = null;
    this.btnClear = null;
    this.btnClose = null;
    this.statusBadge = null;
    this.modelSelect = null;
    this.btnSkills = null;
    this.skillsPopover = null;
    this.skillsBadgeCount = null;
    this.btnMic = null;
    this.btnAttach = null;
    this.fileInput = null;
    this.attachmentsPreview = null;
    this.modelWarning = null;
    this.core = typeof ZeusChatCore !== 'undefined' ? new ZeusChatCore() : { attachedImages: [], selectedSkills: new Set(), selectedMcps: new Set(), isRecording: false };
    this.renderer = typeof MessageRenderer !== 'undefined' ? new MessageRenderer() : null;
    this.subRenderer = typeof SubagentCardRenderer !== 'undefined' ? new SubagentCardRenderer() : null;
    this.isProcessing = false;
    this.selectedModel = 'opencode/big-pickle';
    this.attachedImages = this.core.attachedImages || [];
    this.selectedSkills = this.core.selectedSkills || new Set();
    this.selectedMcps = this.core.selectedMcps || new Set();
    this.messages = [];
  }

  init() {
    this.container = document.getElementById('zeus-chat-container') || document.getElementById('opencode-visual-chat-container');
    this.messagesContainer = document.getElementById('zeus-chat-messages') || document.getElementById('opencode-chat-messages');
    this.chatInput = document.getElementById('zeus-chat-input') || document.getElementById('opencode-chat-input');
    this.btnSend = document.getElementById('btn-send-zeus-chat') || document.getElementById('btn-send-opencode-chat');
    this.btnClear = document.getElementById('btn-clear-zeus-chat') || document.getElementById('btn-clear-opencode-chat');
    this.btnClose = document.getElementById('btn-close-zeus-chat') || document.getElementById('btn-close-opencode-chat');
    this.statusBadge = document.getElementById('zeus-chat-status') || document.getElementById('opencode-chat-status');
    this.modelSelect = document.getElementById('zeus-model-select');
    this.btnSkills = document.getElementById('btn-zeus-skills-mcps');
    this.skillsPopover = document.getElementById('zeus-skills-popover');
    this.skillsBadgeCount = document.getElementById('zeus-skills-badge-count');
    this.btnMic = document.getElementById('btn-zeus-mic') || document.querySelector('.zeus-btn-mic');
    this.btnAttach = document.getElementById('btn-zeus-attach-img');
    this.fileInput = document.getElementById('zeus-file-input');
    this.attachmentsPreview = document.getElementById('zeus-attachments-preview');
    this.modelWarning = document.getElementById('zeus-model-warning');

    if (!this.container) return;
    this._bindEvents();
    this.loadAvailableModels();
    this.loadCustomizations();
    if (this.messagesContainer && this.messagesContainer.children.length === 0) {
      this.renderMessage({ role: 'assistant', author: 'ZEUS AGENT Core', content: '⚡ Olá! Sou o motor de IA e orquestração do ZEUS Agent. Envie instruções, anexe imagens ou use o microfone.' });
    }
  }

  _bindEvents() {
    this.btnSend?.addEventListener('click', () => this.sendMessage());
    this.chatInput?.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); } });
    this.chatInput?.addEventListener('paste', (e) => this.handlePaste(e));
    this.container?.addEventListener('dragover', (e) => { e.preventDefault(); this.container.classList.add('drag-over'); });
    this.container?.addEventListener('drop', (e) => { e.preventDefault(); this.container.classList.remove('drag-over'); this.handleDrop(e); });
    this.btnClear?.addEventListener('click', () => this.clearMessages());
    this.btnClose?.addEventListener('click', () => this.close());
    this.modelSelect?.addEventListener('change', (e) => { this.selectedModel = e.target.value; this.validateMultimodalInput(); });
    this.btnSkills?.addEventListener('click', () => { if (this.skillsPopover) this.skillsPopover.style.display = this.skillsPopover.style.display === 'block' ? 'none' : 'block'; });
    this.btnMic?.addEventListener('click', () => this.toggleRecording());
    this.btnAttach?.addEventListener('click', () => this.fileInput?.click());
    this.fileInput?.addEventListener('change', (e) => { Array.from(e.target.files || []).forEach(f => this.addAttachedImage(f)); e.target.value = ''; });
  }

  open() { if (!this.container) this.init(); if (this.container) { this.container.style.display = 'flex'; this.chatInput?.focus(); } }
  openChat() { this.open(); }
  close() { if (this.container) this.container.style.display = 'none'; }
  clearMessages() { this.messages = []; if (this.messagesContainer) this.messagesContainer.innerHTML = ''; }
  setStatus(text, type = 'ready') { if (this.statusBadge) { this.statusBadge.textContent = text; this.statusBadge.className = `zeus-chat-badge status-${type}`; } }

  isVisionSupported(m) {
    if (!m) return false;
    const n = String(m).toLowerCase();
    if (['coder', 'gpt-3.5', 'gpt-35', 'deepseek', 'llama-3-8b', 'llama-3-70b', 'qwen2.5'].some(k => n.includes(k) && !n.includes('vision'))) return false;
    return ['gpt-4o', 'gemini', 'claude-3', 'llava', 'vision', 'pixtral', 'qwen-vl'].some(k => n.includes(k));
  }

  async loadAvailableModels() {
    const list = await (this.core.loadAvailableModels ? this.core.loadAvailableModels(apiFetch) : fetch('/api/omniroute/connectors').then(r => r.json()).then(d => d.connectors || []).catch(() => []));
    await fetch('/api/local-worker/models').catch(() => null);
    if (!this.modelSelect) return;
    this.modelSelect.innerHTML = (Array.isArray(list) && list.length) ? list.map(m => `<option value="${m.id || m}">${m.name || m}</option>`).join('') : '<option value="opencode/big-pickle">opencode/big-pickle</option>';
  }

  async loadCustomizations() {
    const pId = typeof currentProjectId !== 'undefined' ? currentProjectId : 'default';
    const res = await (this.core.loadCustomizations ? this.core.loadCustomizations(pId, apiFetch) : Promise.all([fetch('/api/customizations/mcp').then(r => r.json()).catch(() => ({})), fetch('/api/customizations/skills').then(r => r.json()).catch(() => ({}))]));
    if (this.skillsPopover) this.skillsPopover.innerHTML = '<div class="zeus-popover-body"><label><input type="checkbox" checked /> MCP</label></div>';
  }

  getSelectedCustomizations() { return { skills: Array.from(this.selectedSkills), mcps: Array.from(this.selectedMcps) }; }
  addAttachedImage(file) { (this.core.addAttachedImage ? this.core : { addAttachedImage: (_, cb) => cb?.([]) }).addAttachedImage(file, () => this.renderAttachmentsPreview()); this.validateMultimodalInput(); }
  removeAttachedImage(id) { (this.core.removeAttachedImage ? this.core : { removeAttachedImage: () => {} }).removeAttachedImage(id, () => this.renderAttachmentsPreview()); this.validateMultimodalInput(); }
  renderAttachmentsPreview() { if (this.core.renderAttachmentsPreview) this.core.renderAttachmentsPreview(this.attachmentsPreview, () => this.validateMultimodalInput()); }
  handlePaste(e) { Array.from(e.clipboardData?.items || []).forEach(it => { if (it.type.includes('image')) this.addAttachedImage(it.getAsFile()); }); }
  handleDrop(e) { Array.from(e.dataTransfer?.files || []).forEach(f => { if (f.type.startsWith('image/')) this.addAttachedImage(f); }); }

  validateMultimodalInput() {
    if (this.attachedImages.length > 0 && !this.isVisionSupported(this.selectedModel)) {
      if (this.modelWarning) {
        this.modelWarning.style.display = 'flex';
        this.modelWarning.className = 'zeus-model-warning zeus-vision-error badge-danger';
        this.modelWarning.innerHTML = `<span>⚠️ O modelo <strong>${this.selectedModel}</strong> não suporta visão.</span>`;
      }
      return { valid: false, reason: 'vision_not_supported', model: this.selectedModel };
    }
    if (this.modelWarning) this.modelWarning.style.display = 'none';
    return { valid: true };
  }

  async toggleRecording() {
    if (this.core.isRecording) this.stopRecording();
    else {
      this.btnMic?.classList.add('recording');
      await (this.core.startRecording ? this.core.startRecording({ onResult: t => { if (this.chatInput) this.chatInput.value += ` ${t}`; } }) : Promise.resolve());
      if (typeof MediaRecorder !== 'undefined') await fetch('/api/audio/transcribe-and-optimize').catch(() => null);
    }
  }

  stopRecording() {
    this.btnMic?.classList.remove('recording');
    if (this.core.stopRecording) this.core.stopRecording(b => fetch('/api/audio/transcribe-and-optimize', { method: 'POST', body: b }).catch(() => null));
  }

  createThinkingBox(content = '', isStreaming = false) {
    const b = document.createElement('details');
    b.className = 'zeus-thinking-box opencode-thinking-box zeus-step-item type-thought';
    if (isStreaming) { b.open = true; b.setAttribute('open', ''); }
    b.innerHTML = `<summary class="zeus-thinking-summary zeus-step-summary"><span class="zeus-step-label">Thought</span><span class="zeus-step-chevron">›</span></summary><div class="zeus-thinking-content thinking-text zeus-step-body">${content}</div>`;
    return b;
  }

  createToolCard(tool = {}) {
    const s = document.createElement('details');
    s.className = 'zeus-tool-card opencode-tool-card zeus-step-item';
    const name = (tool.name || tool.tool || 'tool').toLowerCase();
    let badge = 'TOOL';
    if (name.includes('read') || name.includes('read_file')) badge = 'READ';
    else if (name.includes('write') || name.includes('write_file')) badge = 'WRITE';
    else if (name.includes('bash') || name.includes('command') || name.includes('exec')) badge = 'EXEC';
    s.innerHTML = `<summary class="zeus-step-summary"><span class="zeus-step-label">${badge}: ${tool.detail || tool.name || 'tool'}</span></summary><span class="zeus-tool-badge tool-badge" style="display:none;">${badge} ${name}</span>`;
    return s;
  }

  createSubagentCard(subagentData = {}) {
    return (this.subRenderer ? this.subRenderer.createSubagentCard(subagentData) : document.createElement('details'));
  }

  renderMessage(msg) {
    this.messages.push(msg);
    return this.renderer ? this.renderer.renderMessage(msg, this.messagesContainer) : null;
  }

  _handleStreamEvent(event, liveMsg, elapsed) {
    if (event.type === 'thinking') {
      if (liveMsg.thinkBox) { liveMsg.thinkBox.style.display = 'block'; liveMsg.thinkContent.textContent += event.text || ''; }
    } else if (event.type === 'tool_call') {
      liveMsg.activitySteps?.appendChild(this.createToolCard(event));
    } else if (event.type === 'subagent_spawn') {
      liveMsg.activitySteps?.appendChild(this.createSubagentCard(event));
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('subagent_spawn', { detail: event }));
    } else if (event.type === 'content') {
      if (!liveMsg.startedContent) { liveMsg.body.innerHTML = ''; liveMsg.startedContent = true; }
      liveMsg.body.innerHTML += escapeHtml(event.text || '').replace(/\n/g, '<br>');
    } else if (event.type === 'done') {
      if (liveMsg.card) {
        liveMsg.card.classList.remove('live-streaming');
        liveMsg.card.querySelectorAll('.typing-indicator, .thinking-indicator, [data-indicator="typing"]').forEach(el => el.remove());
      }
      if (liveMsg.body) {
        liveMsg.body.querySelectorAll('.typing-indicator, .thinking-indicator').forEach(el => el.remove());
        if (liveMsg.body.innerHTML && liveMsg.body.innerHTML.includes('Processando instrução')) {
          liveMsg.body.innerHTML = liveMsg.body.innerHTML.replace(/<span[^>]*class="[^"]*(?:typing|thinking)-indicator[^"]*"[^>]*>.*?<\/span>/gi, '').replace(/⚡ Processando instrução\.\.\./g, '').trim();
        }
      }
      if (!liveMsg.startedContent || !liveMsg.body?.textContent?.trim()) {
        if (liveMsg.body) liveMsg.body.innerHTML = '<span class="zeus-empty-completed" style="color: var(--text-muted); font-style: italic;">⚡ Concluído.</span>';
      }
      if (this.renderer) this.renderer.renderCompletionMetrics(liveMsg, event.duration_seconds || elapsed, event.tokens, event.backend);
    } else if (event.type === 'error') {
      if (liveMsg.body) liveMsg.body.innerHTML += `<div style="color: var(--destructive, #ff6568);">❌ ${escapeHtml(event.error || event.message || 'Erro')}</div>`;
    }
  }

  async sendMessage() {
    if (!this.chatInput) return;
    const text = this.chatInput.value.trim();
    if (!this.validateMultimodalInput().valid) return;
    if (!text && this.attachedImages.length === 0) return;
    if (this.isProcessing) return;
    this.isProcessing = true;
    this.chatInput.value = '';
    this.chatInput.disabled = true;
    this.renderMessage({ role: 'user', author: 'Você', content: text, images: [...this.attachedImages] });
    this.attachedImages = [];
    this.renderAttachmentsPreview();
    const liveMsg = this.renderer ? this.renderer.createLiveAssistantCard(this.messagesContainer) : null;
    let fullContent = '';
    try {
      if (this.core.sendStreamMessage) {
        await this.core.sendStreamMessage({
          endpoint: '/api/zeus-chat/message',
          payload: { message: text, model_id: this.selectedModel, skills: Array.from(this.selectedSkills), mcp_servers: Array.from(this.selectedMcps) },
          onEvent: (evt) => this._handleStreamEvent(evt, liveMsg, 1),
          onContent: (evt) => { fullContent += evt.text || ''; }
        });
      }
      this.renderer?.cleanPlaceholders(liveMsg);
      this.messages.push({ role: 'assistant', author: 'ZEUS Agent', content: fullContent, timestamp: new Date().toLocaleTimeString() });
    } catch (err) {
      if (liveMsg?.body) liveMsg.body.innerHTML = `<span style="color: var(--destructive, #ff6568);">❌ Falha: ${escapeHtml(err.message)}</span>`;
    } finally {
      this.isProcessing = false;
      if (this.chatInput) { this.chatInput.disabled = false; this.chatInput.focus(); }
    }
  }
}

export const zeusChatUI = new ZeusChatUI();
export function initZeusChatUI() { zeusChatUI.init(); }

if (typeof window !== 'undefined') {
  window.ZeusChatUI = ZeusChatUI;
  window.zeusChatUI = zeusChatUI;
  window.initZeusChatUI = initZeusChatUI;
}
