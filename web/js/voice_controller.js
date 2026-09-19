/**
 * VoiceController - VAD Hands-Free, Push-To-Talk (PTT), TTS e Sincronia com Avatar 3D.
 * Issue #46 (Frontend/Voice UX & Chief Architect Voice Assistant).
 */
import { encodeWav, downsampleTo16k } from './chat/zeus_chat_core.js';

export class VoiceController {
  constructor(options = {}) {
    this.mode = options.mode || 'vad';
    this.vadThreshold = options.vadThreshold || 0.010;
    this.silenceTimeoutMs = options.silenceTimeoutMs || 1100;
    this.minSpeechMs = options.minSpeechMs || 250;
    this.audioContext = this.mediaStream = this.analyser = this.processor = this.recognition = null;
    this.isListening = this.isSpeaking = this.isPttPressed = this.isPlayingTts = false;
    this.speechStartTime = 0; this.silenceTimer = this._rafAudioLoop = null;
    this.pcmBuffer = []; this.lastCapturedText = '';
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
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        try { this.audioContext = new AudioCtx({ sampleRate: 16000 }); } catch (_) { this.audioContext = new AudioCtx(); }
        if (this.audioContext.state === 'suspended') await this.audioContext.resume().catch(() => {});
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        this.analyser = this.audioContext.createAnalyser(); this.analyser.fftSize = 512;
        this.processor = this.audioContext.createScriptProcessor(2048, 1, 1);
        this.processor.onaudioprocess = (e) => this.processAudioFrame(e.inputBuffer.getChannelData(0));
        const muteGain = this.audioContext.createGain(); muteGain.gain.value = 0;
        source.connect(this.analyser); this.analyser.connect(this.processor);
        this.processor.connect(muteGain); muteGain.connect(this.audioContext.destination);
      }
      this._startWebSpeechRecognition();
      this.isListening = true; this._getAvatar()?.setState('LISTENING');
      this._notifyState('listening_started');
      return true;
    } catch (_) { this.isListening = false; return false; }
  }

  _startWebSpeechRecognition() {
    const SpeechRec = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
    if (!SpeechRec) return;
    try {
      this.recognition = new SpeechRec();
      this.recognition.lang = 'pt-BR'; this.recognition.continuous = true; this.recognition.interimResults = true;
      this.recognition.onresult = (evt) => {
        let interim = '', final = '';
        for (let i = evt.resultIndex; i < evt.results.length; i++) {
          const t = evt.results[i][0].transcript;
          if (evt.results[i].isFinal) final += t; else interim += t;
        }
        const captured = (final || interim).trim();
        if (captured) {
          this.lastCapturedText = captured; this._getAvatar()?.updateAudioLevel(0.85);
          if (this.silenceTimer) clearTimeout(this.silenceTimer);
          this.silenceTimer = setTimeout(() => this._handleSpeechText(this.lastCapturedText), 1100);
        }
      };
      this.recognition.onerror = (e) => { if (e?.error === 'network' || e?.error === 'not-allowed') { try { this.recognition.stop(); } catch (_) {} this.recognition = null; } };
      this.recognition.onend = () => { if (this.isListening && this.recognition) { try { this.recognition.start(); } catch (_) {} } };
      this.recognition.start();
    } catch (_) {}
  }

  stopListening() {
    this.isListening = this.isSpeaking = false;
    if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
    if (this.recognition) { try { this.recognition.stop(); } catch (_) {} this.recognition = null; }
    if (this.processor && this.audioContext) {
      try { this.processor.disconnect(); this.analyser?.disconnect(); this.audioContext.close(); } catch (_) {}
      this.processor = this.analyser = this.audioContext = null;
    }
    if (this.mediaStream) { this.mediaStream.getTracks().forEach(t => t.stop()); this.mediaStream = null; }
    this.lastCapturedText = '';
    this._getAvatar()?.updateAudioLevel(0); this._getAvatar()?.setState('OFF');
    this._notifyState('listening_stopped');
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
        if (!this.isSpeaking) { this.isSpeaking = true; this.speechStartTime = Date.now(); this._notifyState('speech_start'); }
        if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
      } else {
        av?.updateAudioLevel(Math.max(0, (av.getAudioLevel?.() || 0) * 0.8));
        if (this.isSpeaking && this.mode === 'vad' && !this.silenceTimer) {
          this.silenceTimer = setTimeout(() => this._handleSpeechEnd(), this.silenceTimeoutMs);
        }
      }
      if (this.isSpeaking) { this.pcmBuffer.push(new Float32Array(samples)); }
    }
    return rms;
  }

  startPtt() { this.isPttPressed = true; this.pcmBuffer = []; this.startListening(); this._getAvatar()?.setState('LISTENING'); this._notifyState('ptt_start'); }
  stopPtt() { if (!this.isPttPressed) return; this.isPttPressed = false; this._getAvatar()?.updateAudioLevel(0); this._notifyState('ptt_end'); this._handleSpeechEnd(); }

  async _handleSpeechEnd() {
    if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
    if (this.lastCapturedText) { const t = this.lastCapturedText; this.lastCapturedText = ''; return this._handleSpeechText(t); }
    const dur = Date.now() - this.speechStartTime, has = this.pcmBuffer.length > 0;
    this.isSpeaking = false;
    if (has && dur >= this.minSpeechMs) {
      const total = this.pcmBuffer.reduce((acc, c) => acc + c.length, 0), merged = new Float32Array(total);
      let off = 0; for (const c of this.pcmBuffer) { merged.set(c, off); off += c.length; }
      this.pcmBuffer = [];
      const rate = this.audioContext?.sampleRate || 16000;
      await this._sendAudio(encodeWav(downsampleTo16k(merged, rate), 16000));
    } else { this.pcmBuffer = []; if (this.isListening) this._getAvatar()?.setState('LISTENING'); }
  }

  async _handleSpeechText(text) {
    if (!text || !text.trim() || this._isHandlingSpeech) return;
    this._isHandlingSpeech = true;
    const promptText = text.trim(); this.lastCapturedText = '';
    if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
    const av = this._getAvatar(); av?.setState('THINKING');
    const ensureChatOpen = () => { window?.switchTab?.('view-terminal'); window?.openOrCreateChatSession?.(); };
    if (/\b(abrir?|mostr[ae]|modifiq|alter[ae]|cri[ae]|execut[ae]|consert[ae]|corrij[ae]|implement[ae]|adicione|remova)\b/i.test(promptText)) {
      ensureChatOpen();
    }
    setTimeout(() => {
      let s = window.zeusChatWorkspace?.getActiveSession?.();
      if (!s && typeof window.openOrCreateChatSession === 'function') {
        const sess = window.openOrCreateChatSession();
        s = sess?.chatController || window.zeusChatWorkspace?.getActiveSession?.();
      }
      if (s) {
        s._isFromVoice = true;
        if (s.chatInput) { s.chatInput.value = promptText; s.chatInput.dispatchEvent(new Event('input', { bubbles: true })); }
        if (typeof s.sendMessage === 'function' && !s.isProcessing) s.sendMessage();
      }
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('voice:transcription', { detail: { text: promptText } }));
      av?.setState(this.isListening ? 'LISTENING' : 'OFF'); this._isHandlingSpeech = false;
    }, 120);
  }

  async _sendAudio(audioBlob) {
    try {
      const fd = new FormData(); fd.append('audio', audioBlob, 'voice_input.wav');
      const res = await fetch('/api/audio/transcribe-and-optimize', { method: 'POST', body: fd }), data = await res.json();
      const text = data?.optimized_prompt || data?.prompt || data?.transcription || '';
      if (text) await this._handleSpeechText(text);
    } catch (_) {}
  }

  cleanTextForTts(text) {
    if (!text) return '';
    let t = text.replace(/```[\s\S]*?```/g, '').replace(/`([^`]+)`/g, '$1').replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1').replace(/[*#_~>]/g, '').replace(/\s+/g, ' ').trim();
    if (t.length > 350) { const dot = t.indexOf('.', 220); t = dot !== -1 && dot < 380 ? t.substring(0, dot + 1) : t.substring(0, 350) + '...'; }
    return t;
  }

  _speakWithWebSpeech(cleanText) {
    const av = this._getAvatar();
    if (typeof window === 'undefined' || !window.speechSynthesis) { this.isPlayingTts = false; av?.updateAudioLevel(0); av?.setState(this.isListening ? 'LISTENING' : 'OFF'); return false; }
    try { window.speechSynthesis.cancel(); } catch (_) {}
    const utter = new SpeechSynthesisUtterance(cleanText); utter.lang = 'pt-BR'; utter.rate = 1.05;
    this.isPlayingTts = true; av?.setState('SPEAKING');
    const interval = setInterval(() => { if (!this.isPlayingTts) { clearInterval(interval); return; } av?.updateAudioLevel(0.3 + Math.random() * 0.5); }, 120);
    return new Promise(resolve => {
      utter.onend = utter.onerror = () => { clearInterval(interval); this.isPlayingTts = false; av?.updateAudioLevel(0); av?.setState(this.isListening ? 'LISTENING' : 'OFF'); resolve(true); };
      window.speechSynthesis.speak(utter);
    });
  }

  async playTts(text, opt = {}) {
    if (!text || !text.trim()) return false;
    const clean = this.cleanTextForTts(text); if (!clean) return false;
    const av = this._getAvatar(); this.isPlayingTts = true; av?.setState('SPEAKING');
    try {
      const res = await fetch('/api/audio/synthesize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: clean, voice: opt.voice || 'pt-BR-FranciscaNeural' }) });
      if (!res.ok) throw new Error('Falha síntese');
      const blob = await res.blob(); if (!blob || blob.size < 50) throw new Error('Áudio vazio');
      const audioUrl = URL.createObjectURL(blob), audio = new Audio(audioUrl);
      const interval = setInterval(() => { if (!this.isPlayingTts) { clearInterval(interval); return; } av?.updateAudioLevel(0.3 + Math.random() * 0.5); }, 120);
      return new Promise(resolve => {
        const cleanup = () => { clearInterval(interval); URL.revokeObjectURL(audioUrl); this.isPlayingTts = false; av?.updateAudioLevel(0); av?.setState(this.isListening ? 'LISTENING' : 'OFF'); };
        audio.onended = () => { cleanup(); resolve(true); };
        audio.onerror = () => { cleanup(); this._speakWithWebSpeech(clean).then(resolve); };
        audio.play().catch(() => { cleanup(); this._speakWithWebSpeech(clean).then(resolve); });
      });
    } catch (_) { return this._speakWithWebSpeech(clean); }
  }

  _bindPttShortcuts() {
    if (typeof window === 'undefined') return;
    window.addEventListener('keydown', (e) => {
      const isInput = e.target?.tagName === 'INPUT' || e.target?.tagName === 'TEXTAREA' || e.target?.isContentEditable;
      if (e.altKey && e.key.toLowerCase() === 'v') { e.preventDefault(); if (this.isListening) this.stopListening(); else this.startListening(); return; }
      if (this.mode === 'ptt' && !isInput && e.code === 'Space' && !e.repeat && !this.isPttPressed) { e.preventDefault(); this.startPtt(); }
    });
    window.addEventListener('keyup', (e) => { if (this.mode === 'ptt' && this.isPttPressed && e.code === 'Space') { e.preventDefault(); this.stopPtt(); } });
  }

  _notifyState(evt, meta = {}) {
    if (typeof document !== 'undefined') {
      const rec = evt === 'listening_started' || evt === 'ptt_start' || evt === 'speech_start';
      document.querySelectorAll('.zeus-btn-mic').forEach(b => b.classList.toggle('recording', rec));
    }
    if (this.onStateChange) this.onStateChange(evt, meta);
    if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('voice:state', { detail: { event: evt, ...meta } }));
  }
}

export const voiceController = new VoiceController();

export function initAvatarAndVoice() {
  const dock = document.getElementById('zeus-avatar-dock');
  if (dock && typeof window !== 'undefined' && window.avatar3D) {
    window.avatar3D.init(dock);
    dock.addEventListener('click', async (e) => { e.stopPropagation(); if (voiceController.isListening) voiceController.stopListening(); else await voiceController.startListening(); });
  }
  document.addEventListener('click', async (e) => {
    const btnMic = e.target.closest('.zeus-btn-mic');
    if (btnMic) { if (voiceController.isListening) voiceController.stopListening(); else await voiceController.startListening(); }
  });
}

if (typeof window !== 'undefined') {
  window.VoiceController = VoiceController;
  window.voiceController = voiceController;
  window.initAvatarAndVoice = initAvatarAndVoice;
}
