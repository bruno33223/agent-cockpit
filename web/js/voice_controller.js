/**
 * VoiceController - VAD Hands-Free, Push-To-Talk (PTT), TTS e Sincronia com Avatar 3D.
 * Issue #46 (Frontend/Voice UX) - Clean Architecture & No-Build ES Modules.
 */
import { encodeWav } from './chat/zeus_chat_core.js';

export class VoiceController {
  constructor(options = {}) {
    this.mode = options.mode || 'vad';
    this.vadThreshold = options.vadThreshold || 0.022;
    this.silenceTimeoutMs = options.silenceTimeoutMs || 1200;
    this.minSpeechMs = options.minSpeechMs || 350;
    this.audioContext = this.mediaStream = this.analyser = this.processor = null;
    this.isListening = this.isSpeaking = this.isPttPressed = this.isPlayingTts = false;
    this.speechStartTime = 0;
    this.silenceTimer = this._rafAudioLoop = null;
    this.pcmBuffer = [];
    this.avatar = options.avatar || (typeof window !== 'undefined' ? window.avatar3D : null);
    this.onTranscription = options.onTranscription || null;
    this.onStateChange = options.onStateChange || null;
  }

  setMode(m) { this.mode = m === 'ptt' ? 'ptt' : 'vad'; this._notifyState('mode_change', { mode: this.mode }); return this.mode; }
  getMode() { return this.mode; }
  async init(o = {}) { if (o.avatar) this.avatar = o.avatar; if (o.onTranscription) this.onTranscription = o.onTranscription; this._bindPttShortcuts(); return this; }
  _getAvatar() { return this.avatar || (typeof window !== 'undefined' ? window.avatar3D : null); }

  async startListening() {
    if (this.isListening) return true;
    if (!navigator?.mediaDevices?.getUserMedia) return false;
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } });
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.audioContext = new AudioCtx({ sampleRate: 16000 });
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 512;
        this.processor = this.audioContext.createScriptProcessor(2048, 1, 1);
        this.processor.onaudioprocess = (e) => this.processAudioFrame(e.inputBuffer.getChannelData(0));
        source.connect(this.analyser); this.analyser.connect(this.processor);
        this.processor.connect(this.audioContext.destination);
      }
      this.isListening = true; this._notifyState('listening_started'); return true;
    } catch (_) { this.isListening = false; return false; }
  }

  stopListening() {
    this.isListening = this.isSpeaking = false;
    if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
    if (this.processor && this.audioContext) {
      try { this.processor.disconnect(); this.analyser?.disconnect(); this.audioContext.close(); } catch (_) {}
      this.processor = this.analyser = this.audioContext = null;
    }
    if (this.mediaStream) { this.mediaStream.getTracks().forEach(t => t.stop()); this.mediaStream = null; }
    this._getAvatar()?.updateAudioLevel(0); this._notifyState('listening_stopped');
  }

  processAudioFrame(samples) {
    if (!samples || samples.length === 0) return 0.0;
    let sumSq = 0;
    for (let i = 0; i < samples.length; i++) sumSq += samples[i] * samples[i];
    const rms = Math.sqrt(sumSq / samples.length), av = this._getAvatar();
    if (!this.isPlayingTts) {
      const activeVoice = this.mode === 'ptt' ? this.isPttPressed : (rms > this.vadThreshold);
      if (activeVoice) {
        av?.updateAudioLevel(Math.min(1.0, rms * 4.5));
        if (av?.getState() !== 'LISTENING') av?.setState('LISTENING');
        this.pcmBuffer.push(new Float32Array(samples));
        if (!this.isSpeaking) {
          this.isSpeaking = true; this.speechStartTime = Date.now();
          if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
          this._notifyState('speech_start');
        } else if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
      } else {
        av?.updateAudioLevel(Math.max(0, (av.getAudioLevel?.() || 0) * 0.8));
        if (this.isSpeaking && this.mode === 'vad' && !this.silenceTimer) {
          this.silenceTimer = setTimeout(() => this._handleSpeechEnd(), this.silenceTimeoutMs);
        }
      }
    }
    return rms;
  }

  startPtt() { this.isPttPressed = true; this.pcmBuffer = []; this.startListening(); this._getAvatar()?.setState('LISTENING'); this._notifyState('ptt_start'); }
  stopPtt() { if (!this.isPttPressed) return; this.isPttPressed = false; this._getAvatar()?.updateAudioLevel(0); this._notifyState('ptt_end'); this._handleSpeechEnd(); }

  async _handleSpeechEnd() {
    if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
    const dur = Date.now() - this.speechStartTime, has = this.pcmBuffer.length > 0;
    this.isSpeaking = false;
    if (has && dur >= this.minSpeechMs) {
      const total = this.pcmBuffer.reduce((acc, c) => acc + c.length, 0), merged = new Float32Array(total);
      let off = 0; for (const c of this.pcmBuffer) { merged.set(c, off); off += c.length; }
      this.pcmBuffer = []; await this._sendAudio(encodeWav(merged, 16000));
    } else { this.pcmBuffer = []; this._getAvatar()?.setState('IDLE'); }
  }

  async _sendAudio(audioBlob) {
    const av = this._getAvatar(); av?.setState('THINKING');
    try {
      const fd = new FormData(); fd.append('audio', audioBlob, 'voice_input.wav');
      const res = await fetch('/api/audio/transcribe-and-optimize', { method: 'POST', body: fd }), data = await res.json();
      const text = data?.optimized_prompt || data?.prompt || data?.transcription || '';
      if (text) {
        if (this.onTranscription) this.onTranscription(text);
        if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('voice:transcription', { detail: { text, data } }));
      }
    } catch (_) {}
    if (av?.getState() === 'THINKING') av?.setState('IDLE');
  }

  async playTts(text, opt = {}) {
    if (!text || !text.trim()) return false;
    const av = this._getAvatar(); this.isPlayingTts = true; av?.setState('SPEAKING');
    try {
      const res = await fetch('/api/audio/synthesize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text.trim(), voice: opt.voice || 'pt-BR-FranciscaNeural' }) });
      if (!res.ok) throw new Error('Falha síntese');
      const arrayBuffer = await res.arrayBuffer(), AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) { this.isPlayingTts = false; av?.setState('IDLE'); return true; }
      const ctx = new AudioCtx(), audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      const source = ctx.createBufferSource(), analyser = ctx.createAnalyser();
      analyser.fftSize = 256; source.buffer = audioBuffer;
      source.connect(analyser); analyser.connect(ctx.destination);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const check = () => {
        if (!this.isPlayingTts) return;
        analyser.getByteFrequencyData(data);
        let sum = 0; for (let i = 0; i < data.length; i++) sum += data[i];
        av?.updateAudioLevel(Math.min(1.0, (sum / (data.length * 255)) * 1.5));
        this._rafAudioLoop = requestAnimationFrame(check);
      };
      this._rafAudioLoop = requestAnimationFrame(check);
      return new Promise(r => {
        source.onended = () => {
          this.isPlayingTts = false; if (this._rafAudioLoop) cancelAnimationFrame(this._rafAudioLoop);
          av?.updateAudioLevel(0); av?.setState('IDLE'); ctx.close(); r(true);
        };
        source.start(0);
      });
    } catch (_) { this.isPlayingTts = false; av?.updateAudioLevel(0); av?.setState('IDLE'); return false; }
  }

  _bindPttShortcuts() {
    if (typeof window === 'undefined') return;
    window.addEventListener('keydown', (e) => {
      if (this.mode !== 'ptt') return;
      const t = e.target;
      if (t?.tagName === 'INPUT' || t?.tagName === 'TEXTAREA' || t?.isContentEditable) return;
      if (e.code === 'Space' && !e.repeat && !this.isPttPressed) { e.preventDefault(); this.startPtt(); }
    });
    window.addEventListener('keyup', (e) => {
      if (this.mode !== 'ptt' || !this.isPttPressed) return;
      if (e.code === 'Space') { e.preventDefault(); this.stopPtt(); }
    });
  }

  _notifyState(evt, meta = {}) {
    if (this.onStateChange) this.onStateChange(evt, meta);
    if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('voice:state', { detail: { event: evt, ...meta } }));
  }
}

export const voiceController = new VoiceController();

export function initAvatarAndVoice() {
  const dock = document.getElementById('zeus-avatar-dock');
  if (dock && typeof window !== 'undefined' && window.avatar3D) {
    window.avatar3D.init(dock);
    dock.addEventListener('click', () => dock.classList.toggle('avatar-dock-collapsed'));
  }
  voiceController.init({
    onTranscription: (t) => {
      const el = document.querySelector('.zeus-chat-pane:not(.context-hidden) .zeus-chat-input') || document.getElementById('opencode-chat-input') || document.querySelector('.zeus-chat-input');
      if (el) el.value = (el.value ? el.value + ' ' : '') + t;
    }
  });
  document.addEventListener('click', async (e) => {
    const btnMode = e.target.closest('.zeus-btn-voice-mode');
    if (btnMode) {
      const next = voiceController.getMode() === 'vad' ? 'ptt' : 'vad';
      voiceController.setMode(next);
      document.querySelectorAll('.zeus-btn-voice-mode').forEach(b => {
        b.textContent = next.toUpperCase();
        b.className = `zeus-btn-voice-mode badge ${next === 'vad' ? 'badge-info' : 'badge-warning'}`;
      });
      return;
    }
    const btnMic = e.target.closest('.zeus-btn-mic');
    if (btnMic && voiceController.getMode() === 'vad') {
      if (voiceController.isListening) {
        voiceController.stopListening();
        document.querySelectorAll('.zeus-btn-mic').forEach(b => b.classList.remove('recording'));
      } else {
        const ok = await voiceController.startListening();
        if (ok) document.querySelectorAll('.zeus-btn-mic').forEach(b => b.classList.add('recording'));
      }
    }
  });
  document.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.zeus-btn-mic') && voiceController.getMode() === 'ptt') {
      e.preventDefault(); voiceController.startPtt();
      document.querySelectorAll('.zeus-btn-mic').forEach(b => b.classList.add('recording'));
    }
  });
  document.addEventListener('pointerup', (e) => {
    if (e.target.closest('.zeus-btn-mic') && voiceController.getMode() === 'ptt') {
      voiceController.stopPtt();
      document.querySelectorAll('.zeus-btn-mic').forEach(b => b.classList.remove('recording'));
    }
  });
}

if (typeof window !== 'undefined') {
  window.VoiceController = VoiceController;
  window.voiceController = voiceController;
  window.initAvatarAndVoice = initAvatarAndVoice;
}
