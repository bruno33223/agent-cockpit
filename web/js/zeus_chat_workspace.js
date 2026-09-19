/**
 * ZeusChatWorkspaceManager - Casca leve integrada ao TerminalWorkspaceManager (role: 'visual-chat').
 * Issue #34 & #40 (Deduplicação, Reidratação de Histórico no F5 e Modularidade do Zeus Chat)
 */

import { escapeHtml } from './ui_utils.js';
import { currentProjectId } from './state.js';
import { terminalWorkspace } from './terminal_workspace.js';
import { openSubagentTab, focusSubagentTab } from './subagent_tabs.js';
import { ZeusChatCore } from './chat/zeus_chat_core.js';
import { MessageRenderer } from './chat/message_renderer.js';
import { SubagentCardRenderer } from './chat/subagent_card_renderer.js';
const STORAGE_KEY_SESSION = 'zeus_chat_active_session_id';
const getStoredSessionId = () => { try { return localStorage?.getItem?.(STORAGE_KEY_SESSION) || null; } catch (_) { return null; } };
const setStoredSessionId = (id) => { try { id ? localStorage?.setItem?.(STORAGE_KEY_SESSION, id) : localStorage?.removeItem?.(STORAGE_KEY_SESSION); } catch (_) {} };

export class ZeusChatSessionController {
  constructor(session = null, elPane = null) {
    const savedId = getStoredSessionId(); this.sessionId = session?.id || savedId || 'zeus-chat';
    if (this.sessionId) setStoredSessionId(this.sessionId);
    this.paneClassName = 'zeus-chat-pane'; this.role = 'visual-chat';
    this.messages = []; this.isProcessing = false; this.subagents = new Map();
    this.session = session; this.paneEl = elPane;
    this.core = new ZeusChatCore(); this.renderer = new MessageRenderer(); this.subRenderer = new SubagentCardRenderer();
    this.messagesContainer = this.chatInput = this.btnSend = null;
    this.selectedModel = 'auto'; this.selectedSkills = this.core.selectedSkills; this.selectedMcps = this.core.selectedMcps; this.attachedImages = this.core.attachedImages;
    if (session && elPane) this.attachPane(session, elPane);
  }

  attachPane(session, elPane) {
    this.session = session; this.paneEl = elPane;
    const savedId = getStoredSessionId(); this.sessionId = savedId || session?.id || this.sessionId;
    if (session) session.id = this.sessionId; setStoredSessionId(this.sessionId);
    const q = (s) => elPane.querySelector(s);
    this.messagesContainer = q('.zeus-chat-messages'); this.chatInput = q('.zeus-chat-input');
    this.btnSend = q('.btn-send-zeus-chat'); this.btnClear = q('.zeus-btn-clear-history') || q('#btn-clear-zeus-chat');
    this.modelSelect = q('.zeus-pane-model-select') || q('.zeus-model-select'); this.btnAttach = q('.zeus-btn-attach');
    this.fileInput = q('.zeus-file-input'); this.btnMic = q('.zeus-btn-mic'); this.attachmentsPreview = q('.zeus-attachments-preview');
    this.btnSkills = q('.zeus-pane-btn-skills') || q('.zeus-btn-skills'); this.skillsPopover = q('.zeus-pane-skills-popover') || q('.zeus-skills-popover');

    this.btnSend?.addEventListener('click', (e) => { e.stopPropagation(); this.sendMessage(); });
    this.chatInput?.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); } });
    this.chatInput?.addEventListener('paste', (e) => Array.from(e.clipboardData?.items || []).forEach(it => { if (it.type.includes('image')) this.addAttachedImage(it.getAsFile()); }));
    this.btnClear?.addEventListener('click', () => this.clearMessages());
    this.btnAttach?.addEventListener('click', () => this.fileInput?.click());
    this.fileInput?.addEventListener('change', (e) => { Array.from(e.target.files || []).forEach(f => this.addAttachedImage(f)); e.target.value = ''; });
    this.btnMic?.addEventListener('click', () => this.toggleRecording());
    this.btnSkills?.addEventListener('click', () => { if (this.skillsPopover) this.skillsPopover.style.display = this.skillsPopover.style.display === 'none' ? 'flex' : 'none'; });
    this.modelSelect?.addEventListener('change', (e) => { this.selectedModel = e.target.value; }); this.loadAvailableModels();

    const renderWelcome = () => { if (this.messages.length === 0) this.renderMessage({ role: 'assistant', author: 'Orquestrador Zeus', content: '⚡ **Zeus Master Chat Online.** Orquestração de alto nível e controle de subagentes.', timestamp: new Date().toLocaleTimeString() }); };
    if (savedId) { this.loadHistory(savedId).then(h => { if (!h || !h.length) renderWelcome(); }).catch(renderWelcome); }
    else { renderWelcome(); }
  }

  async loadAvailableModels() {
    if (!this.modelSelect) return;
    try {
      const list = await this.core.loadAvailableModels();
      if (Array.isArray(list) && list.length > 0) {
        this.modelSelect.innerHTML = list.map(m => `<option value="${m.id || m}">${m.name || m}</option>`).join('');
        if (this.selectedModel && list.some(m => (m.id || m) === this.selectedModel)) this.modelSelect.value = this.selectedModel;
        else if (this.modelSelect.value) this.selectedModel = this.modelSelect.value;
      }
    } catch (_) {}
  }

  async loadHistory(sessionId = this.sessionId) {
    const targetId = sessionId || this.sessionId;
    if (!targetId) return [];
    try {
      const history = await this.core.loadHistory(targetId);
      if (Array.isArray(history) && history.length > 0) {
        if (this.messagesContainer) this.messagesContainer.innerHTML = '';
        this.messages = [];
        history.forEach(item => {
          const role = item.role || 'assistant', author = item.author || (role === 'user' ? 'Você' : 'Orquestrador Zeus');
          const time = item.timestamp ? (typeof item.timestamp === 'number' ? new Date(item.timestamp * 1000).toLocaleTimeString() : String(item.timestamp)) : new Date().toLocaleTimeString();
          this.renderMessage({ role, author, content: item.content || '', thinking: item.thinking || null, tools: item.tool_calls || item.tools || [], images: item.images || [], timestamp: time });
        });
        return history;
      }
    } catch (_) {}
    return [];
  }

  fetchHistory(sessionId) { return this.loadHistory(sessionId); }
  addAttachedImage(f) { this.core.addAttachedImage(f, () => this.renderAttachmentsPreview()); } renderAttachmentsPreview() { this.core.renderAttachmentsPreview(this.attachmentsPreview); }
  focusInput() { if (this.chatInput) setTimeout(() => this.chatInput.focus(), 60); }
  renderMessage(msg) { this.messages.push(msg); return this.renderer.renderMessage(msg, this.messagesContainer); }

  async clearMessages() {
    this.messages = []; if (this.messagesContainer) this.messagesContainer.innerHTML = '';
    const oldId = this.sessionId; this.sessionId = `zeus-chat-${Date.now()}`;
    if (this.session) this.session.id = this.sessionId;
    setStoredSessionId(this.sessionId);
    if (oldId && this.core) await this.core.clearHistory(oldId).catch(() => {});
  }

  async toggleRecording() {
    if (this.core.isRecording) {
      this.core.stopRecording(b => this.core.sendAudioForTranscription(b).then(t => { if (t && this.chatInput) this.chatInput.value += ` ${t}`; }));
      this.btnMic?.classList.remove('recording');
    } else {
      await this.core.startRecording({
        onStart: () => this.btnMic?.classList.add('recording'),
        onResult: t => { if (this.chatInput) this.chatInput.value += ` ${t}`; },
        onError: (err) => {
          this.btnMic?.classList.remove('recording');
          const msg = typeof err === 'string' ? err : (err?.message || err?.error || 'Acesso ao microfone negado ou indisponível.');
          if (this.messagesContainer) this.renderMessage({ role: 'assistant', author: 'Sistema', content: `⚠️ Microfone: ${escapeHtml(msg)}` });
        },
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
      callbacks.onThinking?.(event.text || '');
    } else if (event.type === 'tool_call') {
      liveMsg.activitySteps?.appendChild(this.renderer.createToolCard(event));
      liveMsg.toolsList?.push(event);
    } else if (event.type === 'subagent_spawn') {
      this.handleSubagentSpawn(event);
    } else if (event.type === 'content') {
      if (!liveMsg.startedContent) { if (liveMsg.body) liveMsg.body.innerHTML = ''; liveMsg.startedContent = true; }
      if (liveMsg.body) liveMsg.body.innerHTML += escapeHtml(event.text || '').replace(/\n/g, '<br>');
      callbacks.onContent?.(event.text || '');
    } else if (event.type === 'done') {
      const duration = event.duration_seconds || elapsed;
      const titleSpan = liveMsg.activityHeader?.querySelector('.zeus-activity-title');
      if (titleSpan) titleSpan.textContent = `Worked for ${duration}s`;
      if (liveMsg.thinkStep) liveMsg.thinkStep.open = false;
      if (liveMsg.thinkBox) liveMsg.thinkBox.open = false;
      liveMsg.card?.classList.remove('live-streaming');
      liveMsg.card?.querySelectorAll('.typing-indicator, .thinking-indicator, [data-indicator="typing"]').forEach(el => el.remove());
      if (liveMsg.body) {
        liveMsg.body.querySelectorAll('.typing-indicator, .thinking-indicator').forEach(el => el.remove());
        if (liveMsg.body.innerHTML?.includes('Processando instrução')) liveMsg.body.innerHTML = liveMsg.body.innerHTML.replace(/<span[^>]*class="[^"]*(?:typing|thinking)-indicator[^"]*"[^>]*>.*?<\/span>/gi, '').replace(/⚡ Processando instrução\.\.\./g, '').trim();
      }
      if (!liveMsg.startedContent || !liveMsg.body?.textContent?.trim()) {
        if (liveMsg.body) liveMsg.body.innerHTML = '<span class="zeus-empty-completed" style="color: var(--text-muted, #94a3b8); font-style: italic;">⚡ Concluído.</span>';
      }
      if (this.renderer) this.renderer.renderCompletionMetrics(liveMsg, duration, event.tokens, event.backend);
    } else if (event.type === 'error' && liveMsg.body) {
      liveMsg.body.innerHTML += `<div style="color: var(--destructive, #ff6568);">❌ ${escapeHtml(event.error || event.message || 'Erro')}</div>`;
    }
  }

  async sendMessage() {
    if (!this.chatInput) return;
    if (this.isProcessing) {
      if (this.abortController) { this.abortController.abort(); this.abortController = null; }
      return;
    }
    const text = this.chatInput.value.trim();
    if (!text && this.core.attachedImages.length === 0) return;
    this.isProcessing = true; this.abortController = new AbortController();
    this.chatInput.value = ''; this.chatInput.disabled = true;
    if (this.btnSend) { this.btnSend.textContent = '⏹ Parar'; this.btnSend.disabled = false; this.btnSend.title = 'Parar execução'; }
    this.renderMessage({ role: 'user', author: 'Você', content: text, images: [...this.core.attachedImages] });
    this.core.attachedImages = []; this.renderAttachmentsPreview();
    const liveMsg = this.renderer.createLiveAssistantCard(this.messagesContainer);
    let fullContent = '', fullThinking = '';
    try {
      await this.core.sendStreamMessage({
        endpoint: '/api/zeus-chat/message',
        payload: { message: text, session_id: this.sessionId, model_id: this.selectedModel, project_id: currentProjectId || 'default' },
        signal: this.abortController?.signal,
        onEvent: (evt) => this._handleLiveStreamEvent(evt, liveMsg, { onThinking: c => { fullThinking += c; }, onContent: c => { fullContent += c; } })
      });
      this.messages.push({ role: 'assistant', author: 'Orquestrador Zeus', content: fullContent, thinking: fullThinking, timestamp: new Date().toLocaleTimeString() });
      if (window.voiceController?.playTts && fullContent && (this._isFromVoice || window.voiceController?.isListening)) { window.voiceController.playTts(fullContent); } this._isFromVoice = false;
    } catch (err) {
      const msg = err.name === 'AbortError' ? 'Execução interrompida pelo usuário.' : err.message;
      if (liveMsg?.body) liveMsg.body.innerHTML += `<div style="color: var(--destructive, #ff6568); font-size: 11px; margin-top: 4px;">⚠️ ${escapeHtml(msg)}</div>`;
    } finally {
      this.isProcessing = false; this.abortController = null;
      if (this.chatInput) { this.chatInput.disabled = false; this.focusInput(); }
      if (this.btnSend) { this.btnSend.textContent = 'Enviar'; this.btnSend.title = 'Enviar mensagem'; }
    }
  }

  destroy() { this.core.stopRecording(); }
}

export class ZeusChatWorkspaceManager {
  constructor() {
    this.sessionId = 'zeus-chat'; this.paneClassName = 'zeus-chat-pane'; this.role = 'visual-chat';
    this.sessions = new Map(); this.activeSessionId = null;
  }
  attachPane(session, elPane) {
    if (!session || !elPane) return null;
    const controller = new ZeusChatSessionController(session, elPane);
    this.sessions.set(session.id, controller);
    session.chatController = controller; session.focusInput = () => controller.focusInput();
    this.activeSessionId = session.id;
    return controller;
  }
  closeSession(sessionId) {
    const c = this.sessions.get(sessionId); if (c) { c.destroy(); this.sessions.delete(sessionId); }
    if (this.activeSessionId === sessionId) { const keys = Array.from(this.sessions.keys()); this.activeSessionId = keys.length ? keys[keys.length - 1] : null; }
  }
  getSession(id) { return this.sessions.get(id) || null; }
  getActiveSession() { return (terminalWorkspace?.activeSessionId && this.sessions.get(terminalWorkspace.activeSessionId)) || this.sessions.get(this.activeSessionId) || Array.from(this.sessions.values()).pop() || null; }
  focusInput() { this.getActiveSession()?.focusInput(); }
  get messages() { return this.getActiveSession()?.messages || []; } get isProcessing() { return this.getActiveSession()?.isProcessing || false; }
  handleSubagentSpawn(data = {}) { this.sessions.forEach(c => c.handleSubagentSpawn(data)); }
  openOrCreateChatSession(mgr = terminalWorkspace, opt = {}) {
    const m = mgr || (typeof window !== 'undefined' ? window.terminalWorkspace : null);
    if (!m) return null;
    const existing = (m.sessions ? Array.from(m.sessions.values()).find(s => s.role === 'visual-chat') : null) || this.getActiveSession();
    if (existing) {
      const id = existing.id || existing.sessionId;
      if (id && m.selectSession) m.selectSession(id);
      existing.focusInput?.(); return existing.session || existing;
    }
    const session = m.createSession({ id: opt.id || getStoredSessionId(), name: opt.name || 'Zeus Chat', role: 'visual-chat', agentType: 'zeus', cwd: m.getActiveProjectRoot?.() || '/' });
    if (session) { m.selectSession(session.id); session.focusInput?.(); }
    return session;
  }
}

export const zeusChatWorkspace = new ZeusChatWorkspaceManager();
export function openOrCreateChatSession(mgr = terminalWorkspace) { return zeusChatWorkspace.openOrCreateChatSession(mgr); }
export function initZeusChatWorkspace() {
  const h = e => { if (e?.detail) zeusChatWorkspace.handleSubagentSpawn(e.detail); };
  if (typeof window !== 'undefined') window.addEventListener('subagent_spawn', h);
  if (typeof document !== 'undefined') document.addEventListener('subagent_spawn', h);
}
if (typeof window !== 'undefined') {
  Object.assign(window, { ZeusChatSessionController, ZeusChatWorkspaceManager, zeusChatWorkspace, openOrCreateChatSession, openZeusChat: () => zeusChatWorkspace.openOrCreateChatSession(), initZeusChatWorkspace });
}
