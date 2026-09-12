/**
 * Agent Cockpit - Landing Page Interactive Application (Vanilla ES6+)
 * 
 * Funcionalidades:
 * 1. Simulador da Frota 3x3 e Gauntlet Loop interativo (3 Builders paralelos + 3 Harsh Critics + Vereditos + Handoff)
 * 2. Console de logs streaming em tempo real (telemetria do Cockpit & Ollama Local Worker com tokens/s)
 * 3. Alternador de abas interativas de recursos
 * 4. Contador dinâmico de tokens economizados e métricas de velocidade da GPU
 * 5. Scroll suave e tooltips interativos
 */

class AgentCockpitApp {
    constructor() {
        this.simulationRunning = false;
        this.simulationStep = 0;
        this.simInterval = null;
        this.tokensSaved = 142850;
        this.gpuSpeed = 48.6;
        this.metricsTimer = null;
        this.init();
    }

    init() {
        this.initDOM();
        this.bindEvents();
        this.startMetricsTicker();
        this.setupTooltips();
        this.setupSmoothScroll();
    }

    initDOM() {
        console.log('[AgentCockpit] Inicializando aplicação interativa da landing page...');
        const appElement = document.getElementById('app') || document.body;
        if (appElement) {
            appElement.dataset.status = 'ready';
        }
    }

    bindEvents() {
        // Alternador de abas interativas
        const tabButtons = document.querySelectorAll('[data-tab-target], .tab-button, .tab-btn, [role="tab"]');
        tabButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const target = btn.dataset.tabTarget || btn.getAttribute('href') || btn.dataset.target;
                this.switchTab(target, btn);
            });
        });

        // Botão para iniciar simulação da Frota 3x3 e Gauntlet Loop
        const simBtn = document.getElementById('btn-start-simulation') ||
                       document.getElementById('startSimulationButton') ||
                       document.querySelector('.btn-simulate');
        if (simBtn) {
            simBtn.addEventListener('click', () => this.toggleGauntletSimulation(simBtn));
        }
    }

    switchTab(tabTarget, activeBtn) {
        if (!tabTarget) return;
        const cleanTarget = tabTarget.replace('#', '');
        
        // Alterna os painéis de conteúdo
        const panes = document.querySelectorAll('.tab-pane, [data-tab-content], .tab-content-panel');
        panes.forEach(pane => {
            pane.classList.remove('active');
            if (pane.id === cleanTarget || pane.dataset.tabContent === cleanTarget) {
                pane.classList.add('active');
            }
        });

        // Atualiza estilo dos botões das abas
        const buttons = document.querySelectorAll('[data-tab-target], .tab-button, .tab-btn, [role="tab"]');
        buttons.forEach(b => b.classList.remove('active'));
        if (activeBtn) {
            activeBtn.classList.add('active');
        }
    }

    toggleGauntletSimulation(triggerBtn) {
        if (this.simulationRunning) {
            this.stopSimulation(triggerBtn);
        } else {
            this.startGauntletSimulation(triggerBtn);
        }
    }

    startGauntletSimulation(triggerBtn) {
        this.simulationRunning = true;
        this.simulationStep = 0;
        if (triggerBtn) {
            triggerBtn.textContent = 'Parar Simulação';
            triggerBtn.classList.add('running');
        }

        this.appendLog('[FLEET-ORCHESTRATOR] Inicializando Master Blueprint e despachando Frota 3x3...', 'orchestrator');

        const builders = [
            { id: 1, slice: 'slice-1', name: 'Builder 1 (Core Engine)', status: 'WORKING', tdd: 'RED -> GREEN' },
            { id: 2, slice: 'slice-2', name: 'Builder 2 (Worker Queue)', status: 'WORKING', tdd: 'RED -> GREEN' },
            { id: 3, slice: 'slice-3', name: 'Builder 3 (Web UI)', status: 'WORKING', tdd: 'RED -> GREEN' }
        ];

        const critics = [
            { id: 1, slice: 'slice-1', name: 'Harsh Critic 1 (Architecture)', verdict: 'APROVADO', severity: '0 Critical' },
            { id: 2, slice: 'slice-2', name: 'Harsh Critic 2 (Security & Concurrency)', verdict: 'APROVADO', severity: '0 Critical' },
            { id: 3, slice: 'slice-3', name: 'Harsh Critic 3 (Integration & UI)', verdict: 'APROVADO', severity: '0 Critical' }
        ];

        this.simInterval = setInterval(() => {
            this.simulationStep++;

            if (this.simulationStep === 1) {
                this.appendLog('[FLEET] 3 Subagentes Executores iniciados em lote único paralelo.', 'info');
                builders.forEach(b => {
                    this.updateAgentNode(b.slice, 'builder', 'WORKING', 'Executando Iron Law TDD');
                    this.appendLog(`[BUILDER-${b.id}] (${b.slice}) ${b.name}: ${b.tdd} via Local Ollama Worker`, 'builder');
                });
            } else if (this.simulationStep === 2) {
                this.appendLog('[LOCAL-WORKER] Fila GPU processou fatias com sucesso. Vazão: 48.6 tokens/s.', 'worker');
                builders.forEach(b => {
                    this.updateAgentNode(b.slice, 'builder', 'WAITING', 'Entrega gerada');
                });
                this.appendLog('[GAUNTLET-LOOP] Transição de contexto: 3 Harsh Critics convocados para a banca...', 'warning');
                critics.forEach(c => {
                    this.updateAgentNode(c.slice, 'critic', 'REVIEWING', 'Auditando git diff');
                    this.appendLog(`[CRITIC-${c.id}] Analisando patch da ${c.slice} contra critérios de aceitação...`, 'critic');
                });
            } else if (this.simulationStep === 3) {
                this.appendLog('[CRITIQUE-VERDICT] Banca avaliadora concluiu a sabatina de código.', 'warning');
                critics.forEach(c => {
                    this.updateAgentNode(c.slice, 'critic', 'APPROVED', `${c.verdict} (${c.severity})`);
                    this.appendLog(`[VERDICT] ${c.name}: ${c.verdict} com ${c.severity}!`, 'success');
                });
            } else if (this.simulationStep === 4) {
                this.appendLog('[HANDOFF] Gerando handoff consolidado: 3 fatias verticais prontas para merge.', 'success');
                this.appendLog('[ORCHESTRATOR] Épico finalizado com perfeição técnica sem regressões!', 'success');
                this.stopSimulation(triggerBtn);
            }
        }, 1100);
    }

    stopSimulation(triggerBtn) {
        this.simulationRunning = false;
        if (this.simInterval) {
            clearInterval(this.simInterval);
            this.simInterval = null;
        }
        if (triggerBtn) {
            triggerBtn.textContent = 'Simular Frota 3x3';
            triggerBtn.classList.remove('running');
        }
    }

    updateAgentNode(sliceId, role, status, details) {
        const nodeEl = document.querySelector(`[data-node-slice="${sliceId}"]`) ||
                       document.getElementById(`node-${sliceId}`);
        if (nodeEl) {
            nodeEl.dataset.status = status.toLowerCase();
            const badge = nodeEl.querySelector('.status-badge');
            if (badge) badge.textContent = status;
            const detEl = nodeEl.querySelector('.status-details');
            if (detEl) detEl.textContent = details;
        }
    }

    appendLog(message, type = 'info') {
        const consoleEl = document.getElementById('logsStream') ||
                          document.getElementById('live-console-logs') ||
                          document.getElementById('logsContainer') ||
                          document.querySelector('.terminal-logs');
        if (!consoleEl) {
            console.log(`[${type.toUpperCase()}] ${message}`);
            return;
        }

        const line = document.createElement('div');
        line.className = `log-line log-${type}`;
        
        const timeSpan = document.createElement('span');
        timeSpan.className = 'log-timestamp';
        timeSpan.textContent = new Date().toLocaleTimeString();

        const badgeSpan = document.createElement('span');
        badgeSpan.className = `log-badge badge-${type}`;
        badgeSpan.textContent = `[${type.toUpperCase()}]`;

        const contentSpan = document.createElement('span');
        contentSpan.className = 'log-content';
        contentSpan.textContent = ` ${message}`;

        line.appendChild(timeSpan);
        line.appendChild(document.createTextNode(' '));
        line.appendChild(badgeSpan);
        line.appendChild(contentSpan);

        consoleEl.appendChild(line);
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    startMetricsTicker() {
        this.metricsTimer = setInterval(() => {
            // Simula contagem de economia de tokens e velocidade local
            this.tokensSaved += Math.floor(Math.random() * 30) + 15;
            this.gpuSpeed = +(46.0 + Math.random() * 6.5).toFixed(1);

            const tokensEl = document.getElementById('tokensEconomizedCounter') ||
                             document.getElementById('metric-tokens-saved');
            const gpuEl = document.getElementById('gpuSpeedometer') ||
                          document.getElementById('metric-gpu-speed');

            if (tokensEl) {
                tokensEl.textContent = this.tokensSaved.toLocaleString('pt-BR');
            }
            if (gpuEl) {
                gpuEl.textContent = `${this.gpuSpeed} tokens/s`;
            }
        }, 2200);
    }

    setupTooltips() {
        const tooltipElements = document.querySelectorAll('[data-tooltip]');
        tooltipElements.forEach(el => {
            el.addEventListener('mouseenter', () => {
                const text = el.dataset.tooltip;
                let tip = el.querySelector('.agent-tooltip');
                if (!tip) {
                    tip = document.createElement('div');
                    tip.className = 'agent-tooltip';
                    tip.textContent = text;
                    el.appendChild(tip);
                }
                tip.classList.add('visible');
            });
            el.addEventListener('mouseleave', () => {
                const tip = el.querySelector('.agent-tooltip');
                if (tip) tip.classList.remove('visible');
            });
        });
    }

    setupSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                const href = this.getAttribute('href');
                if (href && href !== '#' && href.startsWith('#')) {
                    const targetEl = document.querySelector(href);
                    if (targetEl) {
                        e.preventDefault();
                        targetEl.scrollIntoView({ behavior: 'smooth' });
                    }
                }
            });
        });
    }
}

function initLandingApp() {
    return new AgentCockpitApp();
}

if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
        window.agentCockpitApp = initLandingApp();
    });
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AgentCockpitApp, initLandingApp };
}