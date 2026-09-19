/**
 * Tactical Holographic 3D Avatar (Issue #45)
 * Procedural WebGL / Three.js particle renderer with graceful 2D Canvas fallback.
 * Zero external asset dependencies - pure memory-generated geometry and shaders.
 */

const STATE_COLORS = {
  IDLE: { hex: '#00ff66', num: 0x00ff66 },
  READY: { hex: '#00ff66', num: 0x00ff66 },
  LISTENING: { hex: '#00e5ff', num: 0x00e5ff },
  THINKING: { hex: '#a855f7', num: 0xa855f7 },
  DISPATCHING_WORKER: { hex: '#f59e0b', num: 0xf59e0b },
  TESTING: { hex: '#06b6d4', num: 0x06b6d4 },
  SPEAKING: { hex: '#10b981', num: 0x10b981 }
};

export class TacticalAvatar3D {
  constructor() {
    this.state = 'IDLE';
    this.stateMetadata = {};
    this.audioLevel = 0.0;
    this.targetAudioLevel = 0.0;
    this.container = null;
    this.canvas = null;
    this.ctx = null;
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.core = null;
    this.ring = null;
    this.particles = null;
    this.isThree = false;
    this.rafId = null;
    this.time = 0;
    this.disposed = false;
    this._boundAnimate = this._animate.bind(this);
  }

  init(containerElement, options = {}) {
    if (!containerElement) return;
    this.destroy();
    this.disposed = false;
    this.container = containerElement;
    this.container.classList.add('avatar-3d-container', 'tactical-avatar-viewport');
    this.container.setAttribute('data-state', this.state);

    const rect = containerElement.getBoundingClientRect?.() || { width: 300, height: 200 };
    const width = options.width || rect.width || 300;
    const height = options.height || rect.height || 200;

    const doc = typeof document !== 'undefined' ? document : window?.document;
    this.canvas = doc?.createElement('canvas');
    if (!this.canvas) return;

    this.canvas.className = 'avatar-3d-canvas';
    this.canvas.width = width;
    this.canvas.height = height;
    this.container.appendChild(this.canvas);

    const hasThree = typeof window !== 'undefined' && typeof window.THREE === 'object' && window.THREE !== null;
    if (hasThree) {
      this._initThree(window.THREE, width, height);
    } else {
      this._init2D();
    }
    const raf = typeof requestAnimationFrame === 'function' ? requestAnimationFrame : window?.requestAnimationFrame;
    this.rafId = raf?.(this._boundAnimate);
  }

  _initThree(THREE, w, h) {
    this.isThree = true;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, (w || 300) / (h || 200), 0.1, 100);
    this.camera.position.set(0, 0, 7);

    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, alpha: true, antialias: true });
    this.renderer.setSize(w || 300, h || 200);
    this.renderer.setPixelRatio?.(typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1);

    const col = STATE_COLORS.IDLE.num;
    this.core = new THREE.Points(new THREE.IcosahedronGeometry(1.2, 2), new THREE.PointsMaterial({ color: col, size: 0.08, transparent: true, opacity: 0.85 }));
    this.ring = new THREE.Mesh(new THREE.TorusGeometry(2.1, 0.03, 16, 64), new THREE.MeshBasicMaterial({ color: col, wireframe: true, transparent: true, opacity: 0.7 }));
    this.scene.add(this.core);
    this.scene.add(this.ring);

    const count = 70, pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const u = Math.random(), v = Math.random(), theta = u * 2 * Math.PI, phi = Math.acos(2 * v - 1), r = 2.4 + Math.random() * 0.8;
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
    }
    const partGeo = new THREE.BufferGeometry();
    partGeo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    this.particles = new THREE.Points(partGeo, new THREE.PointsMaterial({ color: col, size: 0.06, transparent: true, opacity: 0.6 }));
    this.scene.add(this.particles);
  }

  _init2D() {
    this.isThree = false;
    this.ctx = this.canvas?.getContext?.('2d');
  }

  setState(stateName, metadata = {}) {
    const validState = STATE_COLORS[stateName] ? stateName : 'IDLE';
    this.state = validState;
    this.stateMetadata = metadata;
    if (this.container) this.container.setAttribute('data-state', validState);

    if (this.isThree && typeof window !== 'undefined' && window.THREE) {
      const col = STATE_COLORS[validState]?.num || STATE_COLORS.IDLE.num;
      [this.core, this.ring, this.particles].forEach(obj => obj?.material?.color?.setHex?.(col));
    }
    if (this.container?.dispatchEvent && typeof CustomEvent === 'function') {
      this.container.dispatchEvent(new CustomEvent('avatar:statechange', { detail: { state: validState, metadata } }));
    }
  }

  getState() { return this.state; }
  getStateMetadata() { return this.stateMetadata; }

  updateAudioLevel(rmsLevel) {
    const raw = typeof rmsLevel === 'number' && !isNaN(rmsLevel) ? rmsLevel : 0;
    this.targetAudioLevel = Math.max(0.0, Math.min(1.0, raw));
    this.audioLevel = this.targetAudioLevel;
  }

  getAudioLevel() { return this.audioLevel; }

  _animate() {
    if (this.disposed) return;
    this.time += 0.03;
    this.audioLevel += (this.targetAudioLevel - this.audioLevel) * 0.25;

    if (this.isThree && this.renderer && this.scene && this.camera) {
      this._updateThreeDynamics();
      this.renderer.render(this.scene, this.camera);
    } else if (this.ctx && this.canvas) {
      this._render2DFallback();
    }
    const raf = typeof requestAnimationFrame === 'function' ? requestAnimationFrame : window?.requestAnimationFrame;
    if (raf && !this.disposed) this.rafId = raf(this._boundAnimate);
  }

  _updateThreeDynamics() {
    const s = this.state, a = this.audioLevel;
    let speed = 0.015, coreScale = 1.0, ringScale = 1.0;

    if (s === 'LISTENING') { ringScale = 1.0 + a * 0.9; speed = 0.02; }
    else if (s === 'THINKING') { coreScale = 0.88 + Math.sin(this.time * 6) * 0.04; speed = 0.06; }
    else if (s === 'DISPATCHING_WORKER') { speed = 0.04; this.particles?.scale?.setScalar?.(1.1 + (this.time % 1) * 0.5); }
    else if (s === 'TESTING') { coreScale = 1.0 + Math.sin(this.time * 5) * 0.12; speed = 0.025; }
    else if (s === 'SPEAKING') { coreScale = 1.0 + a * 0.6; ringScale = 1.0 + a * 0.4; speed = 0.03; }

    if (this.core) {
      this.core.rotation.y += speed;
      this.core.rotation.x += speed * 0.5;
      this.core.scale.setScalar(coreScale);
    }
    if (this.ring) {
      this.ring.rotation.z += speed * 0.8;
      this.ring.rotation.x += speed * 0.3;
      this.ring.scale.setScalar(ringScale);
    }
    if (this.particles && s !== 'DISPATCHING_WORKER') {
      this.particles.rotation.y -= speed * 0.4;
      this.particles.scale.setScalar(1.0);
    }
  }

  _render2DFallback() {
    const w = this.canvas.width || 300, h = this.canvas.height || 200, cx = w / 2, cy = h / 2, ctx = this.ctx;
    const color = STATE_COLORS[this.state]?.hex || STATE_COLORS.IDLE.hex;
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(cx, cy);

    let ringR = 48 + (this.state === 'LISTENING' ? this.audioLevel * 35 : 0);
    let coreR = 24 * (this.state === 'THINKING' ? 0.85 + Math.sin(this.time * 6) * 0.06 : 1);
    if (this.state === 'SPEAKING') coreR += this.audioLevel * 16;

    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(0, 0, ringR, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, coreR, 0, Math.PI * 2); ctx.fill();

    const dots = this.state === 'DISPATCHING_WORKER' ? 12 : 6;
    for (let i = 0; i < dots; i++) {
      const ang = this.time + (i * Math.PI * 2) / dots;
      const dist = ringR + (this.state === 'DISPATCHING_WORKER' ? ((this.time * 40 + i * 15) % 40) : 10);
      ctx.beginPath(); ctx.arc(Math.cos(ang) * dist, Math.sin(ang) * dist, 2.5, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  destroy() {
    this.disposed = true;
    const cancel = typeof cancelAnimationFrame === 'function' ? cancelAnimationFrame : window?.cancelAnimationFrame;
    if (this.rafId && cancel) { cancel(this.rafId); this.rafId = null; }
    [this.core, this.ring, this.particles].forEach(obj => {
      obj?.geometry?.dispose?.();
      obj?.material?.dispose?.();
    });
    this.renderer?.dispose?.();
    if (this.canvas?.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    this.canvas = null; this.ctx = null; this.renderer = null; this.scene = null; this.camera = null; this.container = null;
  }
}

export const avatar3D = new TacticalAvatar3D();
export function initAvatar3D(container, options) {
  avatar3D.init(container, options);
  return avatar3D;
}

if (typeof window !== 'undefined') {
  window.TacticalAvatar3D = TacticalAvatar3D;
  window.avatar3D = avatar3D;
  window.initAvatar3D = initAvatar3D;
}
