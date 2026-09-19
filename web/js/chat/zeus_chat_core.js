/**
 * ZeusChatCore - Estado da sessão, modelos, áudio WAV 16kHz PCM e parser SSE.
 * Issue #34 & #42 (Gravação Resiliente WAV 16kHz e Fallback de Microfone)
 */

export const encodeWav = (samples, sampleRate = 16000) => {
  const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); w(8, 'WAVEfmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data');
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0, o = 44; i < samples.length; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
};

export class ZeusChatCore {
  constructor() {
    this.availableModels = []; this.selectedModel = 'opencode/big-pickle';
    this.selectedSkills = new Set(); this.selectedMcps = new Set();
    this.attachedImages = []; this.isRecording = false;
    this.mediaRecorder = this.recognition = this.audioStream = this.audioContext = this.audioProcessor = null;
    this.audioChunks = []; this.pcmChunks = [];
  }

  isVisionSupported(modelName) {
    if (!modelName) return false;
    const name = String(modelName).toLowerCase();
    const textOnly = ['coder', 'gpt-3.5', 'gpt-35', 'deepseek-chat', 'deepseek-coder', 'llama-3-8b', 'llama-3-70b', 'llama3:8b', 'llama3:latest', 'mistral:7b', 'codellama', 'qwen2.5-coder'];
    if (textOnly.some(kw => name.includes(kw) && !name.includes('vision'))) return false;
    const visionKw = ['gpt-4o', 'gpt-4-turbo', 'gemini', 'claude-3', 'claude-3-5', 'claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku', 'llava', 'bakllava', 'vision', 'multimodal', 'pixtral', 'qwen-vl', 'minicpm-v', 'llama-3.2-11b-vision', 'llama-3.2-90b-vision'];
    if (visionKw.some(kw => name.includes(kw))) return true;
    const found = this.availableModels.find(m => (m.id || m.name || '').toLowerCase() === name);
    return Boolean(found && (found.supports_vision || found.vision || (found.capabilities && found.capabilities.includes('vision'))));
  }

  async loadAvailableModels(fetchFn = fetch) {
    const list = [];
    try {
      const res = await fetchFn('/api/opencode/models');
      const data = typeof res.json === 'function' ? await res.json() : res;
      (data?.models || []).forEach(m => list.push({ id: m, name: m, provider: 'OpenCode', supports_vision: this.isVisionSupported(m) }));
    } catch (_) {}
    try {
      const res = await fetchFn('/api/omniroute/connectors'), data = typeof res.json === 'function' ? await res.json() : res;
      (data?.connectors || (Array.isArray(data) ? data : [])).forEach(c => (c.models || []).forEach(m => {
        const id = typeof m === 'string' ? m : (m.id || m.name);
        if (!list.some(x => x.id === id)) list.push({ id, name: `${id} (${c.provider || 'Cloud'})`, provider: c.provider || 'OmniRoute', supports_vision: this.isVisionSupported(id) });
      }));
    } catch (_) {}
    try {
      const res = await fetchFn('/api/local-worker/models'), data = typeof res.json === 'function' ? await res.json() : res;
      (data?.models || (Array.isArray(data) ? data : [])).forEach(m => {
        const id = typeof m === 'string' ? m : (m.name || m.id);
        if (!list.some(x => x.id === id)) list.push({ id, name: `${id} (Local)`, provider: 'Local Worker', supports_vision: this.isVisionSupported(id) });
      });
    } catch (_) {}
    if (!list.some(x => (x.id || x) === 'auto')) list.unshift({ id: 'auto', name: 'auto (Roteamento Automático)', provider: 'OmniRoute', supports_vision: true });
    if (!list.some(x => (x.id || x) === 'opencode/big-pickle')) list.push({ id: 'opencode/big-pickle', name: 'opencode/big-pickle (Padrão)', provider: 'OpenCode', supports_vision: true });
    this.availableModels = list;
    return list;
  }

  validateMultimodalInput(model = this.selectedModel, images = this.attachedImages, warningEl = null) {
    if (images.length > 0 && !this.isVisionSupported(model)) {
      if (warningEl) {
        warningEl.style.display = 'flex'; warningEl.className = 'zeus-model-warning zeus-vision-error badge-danger';
        warningEl.innerHTML = `<span>⚠️ O modelo <strong>${model || 'atual'}</strong> não suporta visão. Escolha um modelo multimodal ou remova a imagem.</span>`;
      }
      return { valid: false, reason: 'vision_not_supported', model };
    }
    if (warningEl) { warningEl.style.display = 'none'; warningEl.innerHTML = ''; }
    return { valid: true };
  }

  addAttachedImage(file, callback = null) {
    if (!file || !file.type?.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      this.attachedImages.push({ id: 'img_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5), name: file.name, size: file.size, dataUrl: e.target.result, file });
      if (callback) callback(this.attachedImages);
    };
    reader.readAsDataURL(file);
  }
  removeAttachedImage(idOrIndex, callback = null) {
    if (typeof idOrIndex === 'number') this.attachedImages.splice(idOrIndex, 1);
    else this.attachedImages = this.attachedImages.filter(img => (typeof img === 'string' ? img : img.id) !== idOrIndex);
    if (callback) callback(this.attachedImages);
  }

  renderAttachmentsPreview(container, onRemove = null) {
    if (!container) return;
    container.innerHTML = '';
    if (this.attachedImages.length === 0) { container.style.display = 'none'; return; }
    container.style.display = 'flex';
    this.attachedImages.forEach((img, idx) => {
      const thumb = document.createElement('div');
      thumb.className = 'zeus-attachment-thumb';
      const src = typeof img === 'string' ? img : img.dataUrl, name = typeof img === 'string' ? 'anexo' : (img.name || 'anexo');
      thumb.innerHTML = `<img src="${src}" alt="${name}" class="thumb-img" /><button type="button" class="btn-remove-thumb zeus-thumb-remove" title="Remover imagem">✕</button>`;
      thumb.querySelector('.zeus-thumb-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        this.removeAttachedImage(img.id || idx, () => this.renderAttachmentsPreview(container, onRemove));
        if (onRemove) onRemove();
      });
      container.appendChild(thumb);
    });
  }

  async loadCustomizations(projectId = 'default', fetchFn = fetch) {
    try {
      const [resMcp, resSkills] = await Promise.all([
        fetchFn(`/api/customizations/mcp?project_id=${encodeURIComponent(projectId)}`).then(r => r.json()).catch(() => null),
        fetchFn(`/api/customizations/skills?project_id=${encodeURIComponent(projectId)}`).then(r => r.json()).catch(() => null)
      ]);
      return { mcps: (resMcp?.mcp_servers || resMcp?.mcp || (Array.isArray(resMcp) ? resMcp : [])) || [], skills: (resSkills?.skills || (Array.isArray(resSkills) ? resSkills : [])) || [] };
    } catch (_) { return { mcps: [], skills: [] }; }
  }

  async _startMediaRecording({ onStart, onError, onEnd }) {
    if (!navigator?.mediaDevices?.getUserMedia) { if (onError) onError(new Error('Microfone não suportado no navegador')); return; }
    try {
      this.audioStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } });
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.audioContext = new AudioCtx({ sampleRate: 16000 });
        const source = this.audioContext.createMediaStreamSource(this.audioStream);
        this.pcmChunks = [];
        this.audioProcessor = this.audioContext.createScriptProcessor(4096, 1, 1);
        this.audioProcessor.onaudioprocess = (e) => { if (this.isRecording) this.pcmChunks.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
        source.connect(this.audioProcessor);
        this.audioProcessor.connect(this.audioContext.destination);
      } else {
        this.mediaRecorder = new MediaRecorder(this.audioStream);
        this.audioChunks = [];
        this.mediaRecorder.ondataavailable = e => { if (e.data?.size > 0) this.audioChunks.push(e.data); };
        this.mediaRecorder.start();
      }
      this.isRecording = true; if (onStart) onStart();
    } catch (err) { this.isRecording = false; if (onError) onError(err); }
  }

  async startRecording({ onStart, onResult, onError, onEnd }) {
    const SpeechRec = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
    let hasResult = false;
    if (SpeechRec) {
      try {
        this.recognition = new SpeechRec();
        this.recognition.lang = 'pt-BR'; this.recognition.continuous = true; this.recognition.interimResults = true;
        this.recognition.onstart = () => { this.isRecording = true; if (onStart) onStart(); };
        this.recognition.onresult = (evt) => {
          hasResult = true; let text = '';
          for (let i = evt.resultIndex; i < evt.results.length; ++i) text += evt.results[i][0].transcript;
          if (onResult) onResult(text);
        };
        this.recognition.onerror = async (err) => {
          if (!hasResult) {
            try { this.recognition?.abort?.(); } catch (_) {}
            this.recognition = null;
            await this._startMediaRecording({ onStart, onError, onEnd });
          } else if (onError) onError(err);
        };
        this.recognition.onend = () => { if (!this.audioStream) { this.isRecording = false; if (onEnd) onEnd(); } };
        this.recognition.start(); return;
      } catch (_) {}
    }
    await this._startMediaRecording({ onStart, onError, onEnd });
  }

  stopRecording(onStop = null) {
    this.isRecording = false;
    if (this.recognition) { try { this.recognition.stop(); } catch (_) {} this.recognition = null; }
    if (this.audioStream) { this.audioStream.getTracks().forEach(t => t.stop()); this.audioStream = null; }
    if (this.audioProcessor && this.audioContext) {
      try { this.audioProcessor.disconnect(); this.audioContext.close(); } catch (_) {}
      this.audioProcessor = null; this.audioContext = null;
      if (onStop && this.pcmChunks?.length) {
        const total = this.pcmChunks.reduce((acc, c) => acc + c.length, 0);
        const merged = new Float32Array(total);
        let off = 0; for (const c of this.pcmChunks) { merged.set(c, off); off += c.length; }
        this.pcmChunks = []; onStop(encodeWav(merged, 16000)); return;
      }
    }
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
      if (onStop) onStop(new Blob(this.audioChunks, { type: 'audio/wav' }));
      this.mediaRecorder = null;
    }
  }

  async sendAudioForTranscription(audioBlob, projectId = 'default', fetchFn = fetch) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'prompt_audio.wav');
    formData.append('project_id', projectId);
    const res = await fetchFn('/api/audio/transcribe-and-optimize', { method: 'POST', body: formData });
    const data = typeof res.json === 'function' ? await res.json() : res;
    return data?.optimized_prompt || data?.prompt || data?.text || data?.transcription || '';
  }

  async sendStreamMessage({ endpoint = '/api/zeus-chat/message', payload, onEvent, onThinking, onToolCall, onSubagentSpawn, onContent, onDone, onError }) {
    const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify(payload) });
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new Error(err.message || `Erro HTTP ${response.status}: ${response.statusText}`); }
    const reader = response.body.getReader(), decoder = new TextDecoder('utf-8');
    let buffer = '';
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
          if (onEvent) onEvent(event);
          if (event.type === 'thinking' && onThinking) onThinking(event);
          else if (event.type === 'tool_call' && onToolCall) onToolCall(event);
          else if (event.type === 'subagent_spawn' && onSubagentSpawn) onSubagentSpawn(event);
          else if (event.type === 'content' && onContent) onContent(event);
          else if (event.type === 'done' && onDone) onDone(event);
          else if (event.type === 'error' && onError) onError(event);
        } catch (_) {}
      }
    }
  }

  async loadHistory(sessionId, fetchFn = fetch) {
    if (!sessionId) return [];
    try { const res = await fetchFn(`/api/zeus-chat/session/${encodeURIComponent(sessionId)}/history`); const data = typeof res.json === 'function' ? await res.json() : res; return Array.isArray(data?.history) ? data.history : []; } catch (_) { return []; }
  }
  async fetchHistory(sessionId, fetchFn = fetch) { return this.loadHistory(sessionId, fetchFn); }
  async clearHistory(sessionId, fetchFn = fetch) {
    if (!sessionId) return false;
    try { const res = await fetchFn(`/api/zeus-chat/session/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }); return Boolean(res?.ok || (res?.status >= 200 && res?.status < 300)); } catch (_) { return false; }
  }
}
export const zeusChatCore = new ZeusChatCore();
if (typeof window !== 'undefined') { window.ZeusChatCore = ZeusChatCore; window.zeusChatCore = zeusChatCore; }
