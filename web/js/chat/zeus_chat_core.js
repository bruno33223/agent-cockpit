/**
 * ZeusChatCore - Estado da sessão, chamadas à API, modelos, áudio e parser SSE.
 * Issue #34 (Deduplicação e Arquitetura Modular do Zeus Chat)
 */

export class ZeusChatCore {
  constructor() {
    this.availableModels = [];
    this.selectedModel = 'opencode/big-pickle';
    this.selectedSkills = new Set();
    this.selectedMcps = new Set();
    this.attachedImages = [];
    this.isRecording = false;
    this.mediaRecorder = null;
    this.recognition = null;
    this.audioChunks = [];
  }

  isVisionSupported(modelName) {
    if (!modelName) return false;
    const name = String(modelName).toLowerCase();
    const textOnly = ['coder', 'gpt-3.5', 'gpt-35', 'deepseek-chat', 'deepseek-coder', 'llama-3-8b', 'llama-3-70b', 'llama3:8b', 'llama3:latest', 'mistral:7b', 'codellama', 'qwen2.5-coder'];
    for (const kw of textOnly) {
      if (name.includes(kw) && !name.includes('vision')) return false;
    }
    const visionKw = ['gpt-4o', 'gpt-4-turbo', 'gemini', 'claude-3', 'claude-3-5', 'claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku', 'llava', 'bakllava', 'vision', 'multimodal', 'pixtral', 'qwen-vl', 'minicpm-v', 'llama-3.2-11b-vision', 'llama-3.2-90b-vision'];
    for (const kw of visionKw) {
      if (name.includes(kw)) return true;
    }
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
      const res = await fetchFn('/api/omniroute/connectors');
      const data = typeof res.json === 'function' ? await res.json() : res;
      (data?.connectors || (Array.isArray(data) ? data : [])).forEach(c => {
        (c.models || []).forEach(m => {
          const id = typeof m === 'string' ? m : (m.id || m.name);
          if (!list.some(x => x.id === id)) list.push({ id, name: `${id} (${c.provider || 'Cloud'})`, provider: c.provider || 'OmniRoute', supports_vision: this.isVisionSupported(id) });
        });
      });
    } catch (_) {}
    try {
      const res = await fetchFn('/api/local-worker/models');
      const data = typeof res.json === 'function' ? await res.json() : res;
      (data?.models || (Array.isArray(data) ? data : [])).forEach(m => {
        const id = typeof m === 'string' ? m : (m.name || m.id);
        if (!list.some(x => x.id === id)) list.push({ id, name: `${id} (Local)`, provider: 'Local Worker', supports_vision: this.isVisionSupported(id) });
      });
    } catch (_) {}
    this.availableModels = list;
    return list;
  }

  validateMultimodalInput(model = this.selectedModel, images = this.attachedImages, warningEl = null) {
    if (images.length > 0 && !this.isVisionSupported(model)) {
      if (warningEl) {
        warningEl.style.display = 'flex';
        warningEl.className = 'zeus-model-warning zeus-vision-error badge-danger';
        warningEl.innerHTML = `<span>⚠️ O modelo <strong>${model || 'atual'}</strong> não suporta visão. Escolha um modelo multimodal ou remova a imagem.</span>`;
      }
      return { valid: false, reason: 'vision_not_supported', model };
    }
    if (warningEl) {
      warningEl.style.display = 'none';
      warningEl.innerHTML = '';
    }
    return { valid: true };
  }

  addAttachedImage(file, callback = null) {
    if (!file || !file.type || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const imgObj = { id: 'img_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5), name: file.name, size: file.size, dataUrl: e.target.result, file };
      this.attachedImages.push(imgObj);
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
    if (this.attachedImages.length === 0) {
      container.style.display = 'none';
      return;
    }
    container.style.display = 'flex';
    this.attachedImages.forEach((img, idx) => {
      const thumb = document.createElement('div');
      thumb.className = 'zeus-attachment-thumb';
      const src = typeof img === 'string' ? img : img.dataUrl;
      const name = typeof img === 'string' ? 'anexo' : (img.name || 'anexo');
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
      return {
        mcps: (resMcp?.mcp_servers || resMcp?.mcp || (Array.isArray(resMcp) ? resMcp : [])) || [],
        skills: (resSkills?.skills || (Array.isArray(resSkills) ? resSkills : [])) || []
      };
    } catch (_) {
      return { mcps: [], skills: [] };
    }
  }

  async startRecording({ onStart, onResult, onError, onEnd }) {
    const SpeechRecognition = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
    if (SpeechRecognition) {
      try {
        this.recognition = new SpeechRecognition();
        this.recognition.lang = 'pt-BR';
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.onstart = () => { this.isRecording = true; if (onStart) onStart(); };
        this.recognition.onresult = (evt) => {
          let text = '';
          for (let i = evt.resultIndex; i < evt.results.length; ++i) text += evt.results[i][0].transcript;
          if (onResult) onResult(text);
        };
        this.recognition.onerror = (err) => { if (onError) onError(err); };
        this.recognition.onend = () => { this.isRecording = false; if (onEnd) onEnd(); };
        this.recognition.start();
        return;
      } catch (_) {}
    }
    if (!navigator?.mediaDevices?.getUserMedia) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.audioChunks = [];
    this.mediaRecorder = new MediaRecorder(stream);
    this.mediaRecorder.addEventListener('dataavailable', e => { if (e.data.size > 0) this.audioChunks.push(e.data); });
    this.mediaRecorder.addEventListener('stop', () => stream.getTracks().forEach(t => t.stop()));
    this.mediaRecorder.start();
    this.isRecording = true;
    if (onStart) onStart();
  }

  stopRecording(onStop = null) {
    this.isRecording = false;
    if (this.recognition) { try { this.recognition.stop(); } catch (_) {} this.recognition = null; }
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
      if (onStop) {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        onStop(audioBlob);
      }
    }
  }

  async sendAudioForTranscription(audioBlob, projectId = 'default', fetchFn = fetch) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'prompt_audio.webm');
    formData.append('project_id', projectId);
    const res = await fetchFn('/api/audio/transcribe-and-optimize', { method: 'POST', body: formData });
    const data = typeof res.json === 'function' ? await res.json() : res;
    return data?.optimized_prompt || data?.prompt || data?.text || data?.transcription || '';
  }

  async sendStreamMessage({ endpoint = '/api/zeus-chat/message', payload, onEvent, onThinking, onToolCall, onSubagentSpawn, onContent, onDone, onError }) {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.message || `Erro HTTP ${response.status}: ${response.statusText}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
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
}

export const zeusChatCore = new ZeusChatCore();

if (typeof window !== 'undefined') {
  window.ZeusChatCore = ZeusChatCore;
  window.zeusChatCore = zeusChatCore;
}
