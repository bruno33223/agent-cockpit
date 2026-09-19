/**
 * ZeusChatWorkspaceManager - Casca leve integrada ao TerminalWorkspaceManager (role: 'visual-chat').
 * Issue #34 (Deduplicação e Arquitetura Modular do Zeus Chat)
 */

import { escapeHtml } from './ui_utils.js';
import { currentProjectId } from './state.js';
import { terminalWorkspace } from './terminal_workspace.js';
import { openSubagentTab, focusSubagentTab } from './subagent_tabs.js';
import { ZeusChatCore } from './chat/zeus_chat_core.js';
import { MessageRenderer } from './chat/message_renderer.js';
import { SubagentCardRenderer } from './chat/subagent_card_renderer.js';

export class ZeusChatSessionController {
  constructor(session = null, elPane = null) {
    this.sessionId = session?.id || 'zeus-chat';
    this.paneClassName = 'zeus-chat-pane';
    this.role = 'visual-chat';
    this.messages = [];
    this.isProcessing = false;
    this.subagents = new Map();
    this.session = session;
    this.paneEl = elPane;
    this.core = new ZeusChatCore();
    this.renderer = new MessageRenderer();
    this.subRenderer = new SubagentCardRenderer();
    this.messagesContainer = null;
    this.chatInput = null;
    this.btnSend = null;
    this.selectedModel = 'auto';
    this.selectedSkills = this.core.selectedSkills;
    this.selectedMcps = this.core.selectedMcps;
    this.attachedImages = this.core.attachedImages;
    if (session && elPane) this.attachPane(session, elPane);
  }

  attachPane(session, elPane) {
    this.session = session;
    this.paneEl = elPane;
    this.messagesContainer = elPane.querySelector('.zeus-chat-messages');
    this.chatInput = elPane.querySelector('.zeus-chat-input');
    this.btnSend = elPane.querySelector('.btn-send-zeus-chat');
    this.btnClear = elPane.querySelector('.zeus-btn-clear-history') || elPane.querySelector('#btn-clear-zeus-chat');
    this.modelSelect = elPane.querySelector('.zeus-pane-model-select') || elPane.querySelector('.zeus-model-select');
    this.btnAttach = elPane.querySelector('.zeus-btn-attach');
    this.fileInput = elPane.querySelector('.zeus-file-input');
    this.btnMic = elPane.querySelector('.zeus-btn-mic');
    this.attachmentsPreview = elPane.querySelector('.zeus-attachments-preview');
    this.btnSkills = elPane.querySelector('.zeus-pane-btn-skills') || elPane.querySelector('.zeus-btn-skills');
    this.skillsPopover = elPane.querySelector('.zeus-pane-skills-popover') || elPane.querySelector('.zeus-skills-popover');

    this.btnSend?.addEventListener('click', (e) => { e.stopPropagation(); this.sendMessage(); });
    this.chatInput?.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); } });
    this.chatInput?.addEventListener('paste', (e) => { Array.from(e.clipboardData?.items || []).forEach(it => { if (it.type.includes('image')) this.addAttachedImage(it.getAsFile()); }); });
    this.btnClear?.addEventListener('click', () => this.clearMessages());
    this.btnAttach?.addEventListener('click', () => this.fileInput?.click());
    this.fileInput?.addEventListener('change', (e) => { Array.from(e.target.files || []).forEach(f => this.addAttachedImage(f)); e.target.value = ''; });
    this.btnMic?.addEventListener('click', () => this.toggleRecording());
    this.btnSkills?.addEventListener('click', () => { if (this.skillsPopover) this.skillsPopover.style.display = this.skillsPopover.style.display === 'none' ? 'flex' : 'none'; });

    if (this.messages.length === 0) {
      this.renderMessage({ role: 'assistant', author: 'Orquestrador Zeus', content: '⚡ **Zeus Master Chat Online.** Orquestração de alto nível e controle de subagentes.', timestamp: new Date().toLocaleTimeString() });
    }
  }

  addAttachedImage(f) { this.core.addAttachedImage(f, () => this.renderAttachmentsPreview()); }
  renderAttachmentsPreview() { this.core.renderAttachmentsPreview(this.attachmentsPreview); }
  focusInput() { if (this.chatInput) setTimeout(() => this.chatInput.focus(), 60); }
  clearMessages() { this.messages = []; if (this.messagesContainer) this.messagesContainer.innerHTML = ''; }
  renderMessage(msg) { this.messages.push(msg); return this.renderer.renderMessage(msg, this.messagesContainer); }

  async toggleRecording() {
    if (this.core.isRecording) {
      this.core.stopRecording(b => this.core.sendAudioForTranscription(b).then(t => { if (t && this.chatInput) this.chatInput.value += ` ${t}`; }));
      this.btnMic?.classList.remove('recording');
    } else {
      await this.core.startRecording({
        onStart: () => this.btnMic?.classList.add('recording'),
        onResult: t => { if (this.chatInput) this.chatInput.value += ` ${t}`; },
        onEnd: () => this.btnMic?.classList.remove('recording')
      });
    }
  }

  handleSubagentSpawn(subagentData = {}) {
    const card = this.subRenderer.renderSubagentCardInContainer(subagentData, this.messagesContainer);
    if (subagentData.id) this.subagents.set(subagentData.id, subagentData);
    const targetFiles = subagentData.target_files || subagentData.targetFiles || [];
    const worktreePath = subagentData.worktree_path || subagentData.worktreePath || '';
    if (card && !card.getAttribute('data-subagent-ready')) {
      card.setAttribute('data-subagent-ready', 'true');
      card.innerHTML += `<span class="hidden-compat btn-open-subagent-terminal" data-target-files="${escapeHtml(JSON.stringify(targetFiles))}" data-worktree="${escapeHtml(worktreePath)}" style="display:none;">Abrir Terminal do Subagente</span>`;
    }
    return card;
  }

  _handleLiveStreamEvent(event, liveMsg, callbacks = {}) {
    if (!liveMsg || !event) return;
    const elapsed = Math.max(1, Math.round((Date.now() - (liveMsg.startTime || Date.now())) / 1000));
    if (event.type === 'thinking') {
      if (liveMsg.thinkBox) liveMsg.thinkBox.style.display = 'block';
      if (liveMsg.thinkContent) liveMsg.thinkContent.textContent += event.text || '';
      if (callbacks.onThinking) callbacks.onThinking(event.text || '');
    } else if (event.type === 'tool_call') {
      liveMsg.activitySteps?.appendChild(this.renderer.createToolCard(event));
      liveMsg.toolsList?.push(event);
    } else if (event.type === 'subagent_spawn') {
      this.handleSubagentSpawn(event);
    } else if (event.type === 'content') {
      if (!liveMsg.startedContent) { if (liveMsg.body) liveMsg.body.innerHTML = ''; liveMsg.startedContent = true; }
      if (liveMsg.body) liveMsg.body.innerHTML += escapeHtml(event.text || '').replace(/\n/g, '<br>');
      if (callbacks.onContent) callbacks.onContent(event.text || '');
    } else if (event.type === 'done') {
      const duration = event.duration_seconds || elapsed;
      if (liveMsg.activityHeader) {
        const titleSpan = liveMsg.activityHeader.querySelector('.zeus-activity-title');
        if (titleSpan) titleSpan.textContent = `Worked for ${duration}s`;
      }
      if (liveMsg.thinkStep) liveMsg.thinkStep.open = false;
      if (liveMsg.thinkBox) liveMsg.thinkBox.open = false;
      if (liveMsg.card) {
        liveMsg.card.classList.remove('live-streaming');
        const indicators = liveMsg.card.querySelectorAll('.typing-indicator, .thinking-indicator, [data-indicator="typing"]');
        indicators.forEach(el => el.remove());
      }
      if (liveMsg.body) {
        const bodyIndicators = liveMsg.body.querySelectorAll('.typing-indicator, .thinking-indicator');
        bodyIndicators.forEach(el => el.remove());
        if (liveMsg.body.innerHTML && liveMsg.body.innerHTML.includes('Processando instrução')) {
          liveMsg.body.innerHTML = liveMsg.body.innerHTML
            .replace(/<span[^>]*class="[^"]*(?:typing|thinking)-indicator[^"]*"[^>]*>.*?<\/span>/gi, '')
            .replace(/⚡ Processando instrução\.\.\./g, '')
            .trim();
        }
      }
      if (!liveMsg.startedContent || !liveMsg.body?.textContent?.trim()) {
        if (liveMsg.body) liveMsg.body.innerHTML = '<span class="zeus-empty-completed" style="color: var(--text-muted, #94a3b8); font-style: italic;">⚡ Concluído.</span>';
      }
      if (this.renderer) this.renderer.renderCompletionMetrics(liveMsg, duration, event.tokens, event.backend);
    } else if (event.type === 'error') {
      if (liveMsg.body) liveMsg.body.innerHTML += `<div style="color: var(--destructive, #ff6568);">❌ ${escapeHtml(event.error || event.message || 'Erro')}</div>`;
    }
  }

  async sendMessage() {
    if (!this.chatInput) return;
    const text = this.chatInput.value.trim();
    if (!text && this.core.attachedImages.length === 0) return;
    if (this.isProcessing) return;
    this.isProcessing = true;
    this.chatInput.value = '';
    this.chatInput.disabled = true;
    if (this.btnSend) this.btnSend.disabled = true;
    this.renderMessage({ role: 'user', author: 'Você', content: text, images: [...this.core.attachedImages] });
    this.core.attachedImages = [];
    this.renderAttachmentsPreview();
    const liveMsg = this.renderer.createLiveAssistantCard(this.messagesContainer);
    let fullContent = '', fullThinking = '';
    try {
      await this.core.sendStreamMessage({
        endpoint: '/api/zeus-chat/message',
        payload: { message: text, session_id: this.sessionId, model_id: this.selectedModel, project_id: currentProjectId || 'default' },
        onEvent: (evt) => this._handleLiveStreamEvent(evt, liveMsg, { onThinking: c => { fullThinking += c; }, onContent: c => { fullContent += c; } })
      });
      this.renderer.cleanPlaceholders(liveMsg);
      this.messages.push({ role: 'assistant', author: 'Orquestrador Zeus', content: fullContent, thinking: fullThinking, timestamp: new Date().toLocaleTimeString() });
    } catch (err) {
      if (liveMsg?.body) liveMsg.body.innerHTML = `<span style="color: var(--destructive, #ff6568);">❌ ${escapeHtml(err.message)}</span>`;
    } finally {
      this.isProcessing = false;
      if (this.chatInput) { this.chatInput.disabled = false; this.focusInput(); }
      if (this.btnSend) this.btnSend.disabled = false;
    }
  }

  destroy() { this.core.stopRecording(); }
}

export class ZeusChatWorkspaceManager {
  constructor() {
    this.sessionId = 'zeus-chat';
    this.paneClassName = 'zeus-chat-pane';
    this.role = 'visual-chat';
    this.sessions = new Map();
    this.activeSessionId = null;
  }

  attachPane(session, elPane) {
    if (!session || !elPane) return null;
    const controller = new ZeusChatSessionController(session, elPane);
    this.sessions.set(session.id, controller);
    session.chatController = controller;
    session.focusInput = () => controller.focusInput();
    this.activeSessionId = session.id;
    return controller;
  }

  closeSession(sessionId) {
    const controller = this.sessions.get(sessionId);
    if (controller) { controller.destroy(); this.sessions.delete(sessionId); }
    if (this.activeSessionId === sessionId) {
      const remaining = Array.from(this.sessions.keys());
      this.activeSessionId = remaining.length > 0 ? remaining[remaining.length - 1] : null;
    }
  }

  getSession(sessionId) { return this.sessions.get(sessionId) || null; }

  getActiveSession() {
    if (terminalWorkspace?.activeSessionId && this.sessions.has(terminalWorkspace.activeSessionId)) {
      return this.sessions.get(terminalWorkspace.activeSessionId);
    }
    return this.sessions.get(this.activeSessionId) || Array.from(this.sessions.values()).pop() || null;
  }

  focusInput() { this.getActiveSession()?.focusInput(); }
  get messages() { return this.getActiveSession()?.messages || []; }
  get isProcessing() { return this.getActiveSession()?.isProcessing || false; }

  handleSubagentSpawn(subagentData = {}) {
    this.sessions.forEach(ctrl => ctrl.handleSubagentSpawn(subagentData));
  }

  openOrCreateChatSession(terminalManager = terminalWorkspace, options = {}) {
    const mgr = terminalManager || (typeof window !== 'undefined' ? window.terminalWorkspace : null);
    if (!mgr) return null;
    const name = options.name || 'Zeus Chat';
    const session = mgr.createSession({ name, role: 'visual-chat', agentType: 'zeus', cwd: mgr.getActiveProjectRoot?.() || '/' });
    if (session) { mgr.selectSession(session.id); session.focusInput?.(); }
    return session;
  }
}

export const zeusChatWorkspace = new ZeusChatWorkspaceManager();
export function openOrCreateChatSession(mgr = terminalWorkspace) { return zeusChatWorkspace.openOrCreateChatSession(mgr); }
export function initZeusChatWorkspace() {
  const handler = e => { if (e?.detail) zeusChatWorkspace.handleSubagentSpawn(e.detail); };
  if (typeof window !== 'undefined') window.addEventListener('subagent_spawn', handler);
  if (typeof document !== 'undefined') document.addEventListener('subagent_spawn', handler);
}

if (typeof window !== 'undefined') {
  window.ZeusChatSessionController = ZeusChatSessionController;
  window.ZeusChatWorkspaceManager = ZeusChatWorkspaceManager;
  window.zeusChatWorkspace = zeusChatWorkspace;
  window.openOrCreateChatSession = openOrCreateChatSession;
  window.openZeusChat = () => zeusChatWorkspace.openOrCreateChatSession();
  window.initZeusChatWorkspace = initZeusChatWorkspace;
}
