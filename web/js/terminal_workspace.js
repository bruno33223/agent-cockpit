/**
 * Módulo de Terminal Workspace (TerminalWorkspaceManager)
 * Governa sessões PTY 1:N concorrentes, abas estilo Chrome, layouts de split e statusline.
 */

import { escapeHtml, formatRelativeCwd } from './ui_utils.js';
import { currentProjectId, activeSliceId, state, knownProjects, recordRecentProject, apiFetch, getActiveProjectRoot } from './state.js';
import { renderWorktreeSidebar } from './sidebar.js';
import { openCodeChat } from './opencode_chat.js';


export class TerminalWorkspaceManager {
  constructor() {
    this.sessions = new Map(); // id -> { id, name, role, sliceId, agentType, cwd, term, fitAddon, socket, isConnected, elPane, elTab, resizeObserver, contextKey, projectId, taskId }
    this.contextSessions = new Map(); // contextKey -> Set of sessionIds
    this.activeSessionId = null;
    this.activeContextKey = null;
    this.roleFilter = 'all'; // 'all' | 'orchestrator' | 'agent' | 'subagent'
    this.layout = localStorage.getItem('cockpit_terminal_layout') || 'grid';
    this.zoomLevel = 1.0;
    this.minZoom = 0.4;
    this.maxZoom = 2.0;
    this.zoomStep = 0.1;
    this.panX = 0;
    this.panY = 0;
    this.isPanning = false;
    this.startPanX = 0;
    this.startPanY = 0;
    this.counter = 0;
    this.tabsBar = null;
    this.gridContainer = null;
    this.viewport = null;
    this.isInitialized = false;
  }

  getRoleIcon(role) {
    switch (role) {
      case 'orchestrator': return '⚡';
      case 'agent': return '⚙️';
      case 'subagent': return '🔬';
      case 'visual-chat': return `<img src="/zeus_terminal_god.svg" class="zeus-tab-god-icon" alt="Zeus Chat" style="width:14px;height:14px;vertical-align:middle;display:inline-block;" />`;
      default: return '💻';
    }
  }

  getRoleTitle(role) {
    switch (role) {
      case 'orchestrator': return 'Orquestrador';
      case 'agent': return 'Agente Executor';
      case 'subagent': return 'Subagente Efêmero';
      case 'visual-chat': return 'Zeus Chat';
      default: return 'Terminal';
    }
  }

  getRoleBadgeHtml(role) {
    const title = this.getRoleTitle(role);
    const icon = this.getRoleIcon(role);
    return `<span class="term-tab-role-badge role-${role}" title="${title}"><span class="role-badge-icon">${icon}</span> <span class="role-badge-text">${title}</span></span>`;
  }

  getRolePermissionsText(role) {
    switch (role) {
      case 'orchestrator':
        return '🛡️ Staff Orchestrator (Full Access / Blueprint Control)';
      case 'agent':
        return '⚡ Fleet Agent (Worktree Isolated / Auto-Red-Green)';
      case 'subagent':
        return '🔬 Ephemeral Subagent (Task Sandbox / Read-Write)';
      case 'visual-chat':
        return '⚡ Zeus Master Chat (Interactive Blueprint & Subagent Dispatcher)';
      default:
        return '⚡ bypass permissions on (shift+tab to cycle) - for agents';
    }
  }

  getTerminalTheme(themeName) {
    const currentTheme = themeName || (typeof document !== 'undefined' && document.documentElement ? document.documentElement.getAttribute('data-theme') : null) || 'dark';
    switch (currentTheme) {
      case 'light':
        return {
          background: '#ffffff',
          foreground: '#0f172a',
          cursor: '#0f172a',
          cursorAccent: '#ffffff',
          selectionBackground: 'rgba(15, 23, 42, 0.15)',
          selectionForeground: '#0f172a',
          black: '#0f172a',
          red: '#b91c1c',
          green: '#15803d',
          yellow: '#a16207',
          blue: '#1d4ed8',
          magenta: '#7e22ce',
          cyan: '#0e7490',
          white: '#475569',
          brightBlack: '#64748b',
          brightRed: '#dc2626',
          brightGreen: '#16a34a',
          brightYellow: '#c2410c',
          brightBlue: '#2563eb',
          brightMagenta: '#9333ea',
          brightCyan: '#0891b2',
          brightWhite: '#0f172a'
        };
      case 'classic':
        return {
          background: '#181818',
          foreground: '#d4d4d4',
          cursor: '#00ff66',
          cursorAccent: '#181818',
          selectionBackground: 'rgba(0, 255, 102, 0.25)',
          selectionForeground: '#ffffff',
          black: '#000000',
          red: '#cd3131',
          green: '#0dbc79',
          yellow: '#e5e510',
          blue: '#2472c8',
          magenta: '#bc3fbc',
          cyan: '#11a8cd',
          white: '#e5e5e5',
          brightBlack: '#666666',
          brightRed: '#f14c4c',
          brightGreen: '#23d18b',
          brightYellow: '#f5f543',
          brightBlue: '#3b8eea',
          brightMagenta: '#d670d6',
          brightCyan: '#29b8db',
          brightWhite: '#ffffff'
        };
      case 'sepia':
        return {
          background: '#faf4e8',
          foreground: '#291e12',
          cursor: '#5a4123',
          cursorAccent: '#faf4e8',
          selectionBackground: 'rgba(90, 65, 35, 0.2)',
          selectionForeground: '#291e12',
          black: '#291e12',
          red: '#991b1b',
          green: '#166534',
          yellow: '#92400e',
          blue: '#1e40af',
          magenta: '#6b21a8',
          cyan: '#155e75',
          white: '#5c4731',
          brightBlack: '#78654c',
          brightRed: '#b91c1c',
          brightGreen: '#15803d',
          brightYellow: '#b45309',
          brightBlue: '#1d4ed8',
          brightMagenta: '#7e22ce',
          brightCyan: '#0369a1',
          brightWhite: '#1c140c'
        };
      case 'dark':
      default:
        return {
          background: '#09090b',
          foreground: '#f4f4f5',
          cursor: '#f4f4f5',
          cursorAccent: '#09090b',
          selectionBackground: 'rgba(255, 255, 255, 0.18)',
          black: '#18181b',
          red: '#f43f5e',
          green: '#10b981',
          yellow: '#f59e0b',
          blue: '#3b82f6',
          magenta: '#a855f7',
          cyan: '#38bdf8',
          white: '#f4f4f5',
          brightBlack: '#71717a',
          brightRed: '#fb7185',
          brightGreen: '#34d399',
          brightYellow: '#fbbf24',
          brightBlue: '#60a5fa',
          brightMagenta: '#c084fc',
          brightCyan: '#7dd3fc',
          brightWhite: '#ffffff'
        };
    }
  }

  setRoleFilter(filter) {
    this.roleFilter = filter || 'all';
    this.sessions.forEach(s => {
      const belongsContext = (!this.activeContextKey || s.contextKey === this.activeContextKey);
      const matchesFilter = (this.roleFilter === 'all' || s.role === this.roleFilter);
      const isVisible = belongsContext && matchesFilter;
      if (s.elTab) s.elTab.style.display = isVisible ? '' : 'none';
    });
  }

  getActiveContextSessions() {
    if (!this.activeContextKey) {
      return Array.from(this.sessions.values());
    }
    const sessionIds = this.contextSessions.get(this.activeContextKey);
    if (!sessionIds) return [];
    const list = [];
    sessionIds.forEach(id => {
      const s = this.sessions.get(id);
      if (s) list.push(s);
    });
    return list;
  }

  getAgentCommand(agentType) {
    switch (agentType) {
      case 'opencode':
        return 'opencode\n';
      case 'claude':
        return 'claude\n';
      case 'codex':
        return 'codex\n';
      case 'bash':
      default:
        return '';
    }
  }

  findNextFreeSlot() {
    const activeSessions = this.getActiveContextSessions();
    const occupied = [];
    activeSessions.forEach(s => {
      if (s.elPane && s.elPane.style.display !== 'none') {
        const x = parseFloat(s.elPane.style.left) || (s.customPos && s.customPos.x) || 0;
        const y = parseFloat(s.elPane.style.top) || (s.customPos && s.customPos.y) || 0;
        occupied.push({ x, y });
      }
    });

    const slotWidth = 600;
    const slotHeight = 460;
    const startX = 24;
    const startY = 24;
    const maxCols = 3;

    for (let index = 0; index < 100; index++) {
      const col = index % maxCols;
      const row = Math.floor(index / maxCols);
      const testX = startX + col * slotWidth;
      const testY = startY + row * slotHeight;

      const collides = occupied.some(pos => {
        return Math.abs(pos.x - testX) < (slotWidth - 40) && Math.abs(pos.y - testY) < (slotHeight - 40);
      });

      if (!collides) {
        return { x: testX, y: testY };
      }
    }

    return { x: startX + (activeSessions.length * 30), y: startY + (activeSessions.length * 30) };
  }

  applyDynamicSplit() {
    if (!this.gridContainer) return;
    const count = this.getActiveContextSessions().length;
    const splitClass = `split-${Math.max(1, Math.min(count, 6))}`;
    this.gridContainer.className = `terminal-workspace-grid layout-dynamic ${splitClass}`;
    this.updateHeaderBadge();
    this.fitAll();
    setTimeout(() => this.fitAll(), 120);
  }

  getAgentIcon(agentType) {
    switch (agentType) {
      case 'zeus':
      case 'zeus-chat':
      case 'visual-chat':
        return `<span class="orca-tab-agent-icon orca-agent-zeus" title="Zeus Chat"><img src="/zeus_terminal_god.svg" class="zeus-tab-god-icon" alt="Zeus Chat" style="width:14px;height:14px;vertical-align:middle;display:inline-block;" /></span>`;
      case 'claude':
        return `<span class="orca-tab-agent-icon orca-agent-claude" title="Claude Code"><svg class="orca-icon-svg" width="14" height="14" viewBox="0 0 24 24" fill="#D97757" aria-label="Claude Code"><path d="M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z"/></svg></span>`;
      case 'opencode':
        return `<span class="orca-tab-agent-icon orca-agent-opencode" title="OpenCode">⚡</span>`;
      case 'codex':
        return `<span class="orca-tab-agent-icon orca-agent-codex" title="Codex">&gt;_</span>`;
      case 'bash':
      default:
        return `<span class="orca-tab-agent-icon orca-agent-bash" title="Bash">&gt;</span>`;
    }
  }

  getAgentDisplayName(agentType, sessionIndex) {
    switch (agentType) {
      case 'claude':
        return 'Claude Code';
      case 'opencode':
        return 'OpenCode';
      case 'codex':
        return 'Codex';
      case 'bash':
      default:
        return sessionIndex ? `Term ${sessionIndex}` : 'Bash';
    }
  }

  setZoom(level) {
    this.zoomLevel = Math.max(this.minZoom, Math.min(this.maxZoom, parseFloat(level.toFixed(2))));
    this.updateCanvasTransform();
    const displayBtn = document.getElementById('btn-zoom-reset-term');
    if (displayBtn) {
      displayBtn.textContent = `${Math.round(this.zoomLevel * 100)}%`;
    }
    this.fitAll();
  }

  zoomIn() {
    this.setZoom(this.zoomLevel + this.zoomStep);
  }

  zoomOut() {
    this.setZoom(this.zoomLevel - this.zoomStep);
  }

  resetZoom() {
    this.panX = 0;
    this.panY = 0;
    this.setZoom(1.0);
  }

  updateCanvasTransform() {
    if (!this.gridContainer) return;
    this.gridContainer.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoomLevel})`;
    this.gridContainer.style.transformOrigin = '0 0';
  }

  setLayoutMode(mode) {
    if (!this.gridContainer) return;
    this.layout = mode;
    localStorage.setItem('cockpit_terminal_layout', mode);

    this.gridContainer.classList.remove('layout-grid', 'layout-side-by-side', 'layout-stacked', 'layout-free', 'layout-dynamic');
    this.gridContainer.classList.add(`layout-${mode}`);

    if (mode !== 'free') {
      this.sessions.forEach(s => {
        if (s.elPane) {
          s.elPane.style.position = '';
          s.elPane.style.left = '';
          s.elPane.style.top = '';
          s.elPane.style.width = '';
          s.elPane.style.height = '';
          s.elPane.style.zIndex = '';
        }
      });
    } else {
      this.getActiveContextSessions().forEach(s => {
        if (s.elPane) {
          if (!s.customPos) {
            const slot = this.findNextFreeSlot();
            s.elPane.style.position = 'absolute';
            s.elPane.style.left = `${slot.x}px`;
            s.elPane.style.top = `${slot.y}px`;
            s.elPane.style.width = '580px';
            s.elPane.style.height = '440px';
            s.customPos = slot;
          } else {
            s.elPane.style.position = 'absolute';
            s.elPane.style.left = `${s.customPos.x}px`;
            s.elPane.style.top = `${s.customPos.y}px`;
            s.elPane.style.width = `${s.customWidth || 580}px`;
            s.elPane.style.height = `${s.customHeight || 440}px`;
          }
        }
      });
    }

    document.querySelectorAll('#grid-config-dropdown .grid-config-item').forEach(item => {
      item.classList.toggle('active', item.getAttribute('data-grid-layout') === mode);
    });

    this.updateHeaderBadge();
    this.fitAll();
    setTimeout(() => this.fitAll(), 100);
  }

  getCurrentModel() {
    if (typeof localWorkerStatus !== 'undefined' && localWorkerStatus && localWorkerStatus.model) {
      return localWorkerStatus.model;
    }
    if (typeof state !== 'undefined' && state && state.config && state.config.model) {
      return state.config.model;
    }
    return '';
  }

  getCurrentSliceOrBranch() {
    if (typeof activeSliceId !== 'undefined' && activeSliceId) {
      if (typeof state !== 'undefined' && state.nodes && Array.isArray(state.nodes)) {
        const node = state.nodes.find(n => n.id === activeSliceId);
        if (node) {
          return node.title || node.branch || `slice/${node.id}`;
        }
      }
      return `slice/${activeSliceId}`;
    }
    return 'main';
  }

  formatRelativeCwd(cwd) {
    if (!cwd) return './';
    const root = this.getActiveProjectRoot();
    if (root && cwd.startsWith(root)) {
      let rel = cwd.slice(root.length).replace(/^[\\\/]+/, '');
      return rel ? `./${rel}` : './';
    }
    return this.formatCwd(cwd);
  }

  init() {
    this.tabsBar = document.getElementById('terminal-tabs-bar');
    this.gridContainer = document.getElementById('terminal-workspace-grid');
    if (!this.tabsBar || !this.gridContainer) return;

    if (this.isInitialized) {
      this.fitAll();
      return;
    }
    this.isInitialized = true;

    this.viewport = document.getElementById('terminal-canvas-viewport');

    // Botão e Dropdown Configurar Grid (Issue #10)
    const btnConfigGrid = document.getElementById('btn-config-grid');
    const gridDropdown = document.getElementById('grid-config-dropdown');
    if (btnConfigGrid && gridDropdown) {
      btnConfigGrid.addEventListener('click', (e) => {
        e.stopPropagation();
        gridDropdown.style.display = (gridDropdown.style.display === 'none' || !gridDropdown.style.display) ? 'block' : 'none';
      });

      gridDropdown.querySelectorAll('.grid-config-item').forEach(item => {
        item.addEventListener('click', (e) => {
          e.stopPropagation();
          const mode = item.getAttribute('data-grid-layout');
          if (mode) this.setLayoutMode(mode);
          gridDropdown.style.display = 'none';
        });
      });

      document.addEventListener('click', () => {
        gridDropdown.style.display = 'none';
      });
    }

    // Controles de Zoom In/Out/Reset (Issue #10)
    const btnZoomIn = document.getElementById('btn-zoom-in-term');
    if (btnZoomIn) {
      btnZoomIn.addEventListener('click', () => this.zoomIn());
    }
    const btnZoomOut = document.getElementById('btn-zoom-out-term');
    if (btnZoomOut) {
      btnZoomOut.addEventListener('click', () => this.zoomOut());
    }
    const btnZoomReset = document.getElementById('btn-zoom-reset-term');
    if (btnZoomReset) {
      btnZoomReset.addEventListener('click', () => this.resetZoom());
    }

    // Área de Trabalho Virtual: Suporte a Pan e Wheel Zoom (Issue #10)
    if (this.viewport) {
      this.viewport.addEventListener('mousedown', (e) => {
        const isCanvasBg = (e.target === this.viewport || e.target === this.gridContainer);
        const isMiddle = (e.button === 1);
        if (isCanvasBg || isMiddle || e.spaceKey) {
          this.isPanning = true;
          this.startPanX = e.clientX - this.panX;
          this.startPanY = e.clientY - this.panY;
          this.viewport.classList.add('is-panning');
          e.preventDefault();
        }
      });

      window.addEventListener('mousemove', (e) => {
        if (this.isPanning) {
          this.panX = e.clientX - this.startPanX;
          this.panY = e.clientY - this.startPanY;
          this.updateCanvasTransform();
        }
      });

      window.addEventListener('mouseup', () => {
        if (this.isPanning) {
          this.isPanning = false;
          if (this.viewport) this.viewport.classList.remove('is-panning');
        }
      });

      this.viewport.addEventListener('wheel', (e) => {
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          if (e.deltaY < 0) {
            this.zoomIn();
          } else {
            this.zoomOut();
          }
        }
      }, { passive: false });
    }

    // Botão e Dropdown Novo Terminal (+ Novo Terminal) - Split Button
    const btnNewTerm = document.getElementById('btn-new-terminal');
    const btnNewTermDropdown = document.getElementById('btn-new-terminal-dropdown');
    const newTermDropdown = document.getElementById('new-terminal-dropdown');
    if (btnNewTerm && (newTermDropdown || btnNewTermDropdown)) {
      // 1. Clique direto no botão principal abre ou foca o Zeus Chat
      btnNewTerm.addEventListener('click', (e) => {
        e.stopPropagation();
        if (newTermDropdown) newTermDropdown.style.display = 'none';
        if (btnNewTermDropdown) btnNewTermDropdown.setAttribute('aria-expanded', 'false');
        if (currentProjectId) {
          recordRecentProject(currentProjectId);
          renderWorktreeSidebar();
        }
        this.openZeusChat();
      });

      // 2. Seta lateral (▾): abre o menu suspenso de seleção de terminais alternativos
      if (btnNewTermDropdown && newTermDropdown) {
        btnNewTermDropdown.addEventListener('click', (e) => {
          e.stopPropagation();
          const isHidden = (newTermDropdown.style.display === 'none' || !newTermDropdown.style.display);
          newTermDropdown.style.display = isHidden ? 'block' : 'none';
          btnNewTermDropdown.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
        });
      }

      if (newTermDropdown) {
        newTermDropdown.querySelectorAll('.grid-config-item').forEach(item => {
          item.addEventListener('click', (e) => {
            e.stopPropagation();
            const action = item.getAttribute('data-action');
            if (action === 'open-zeus-chat') {
              this.openZeusChat();
              newTermDropdown.style.display = 'none';
              if (btnNewTermDropdown) btnNewTermDropdown.setAttribute('aria-expanded', 'false');
              return;
            }
            if (action === 'open-visual-chat') {
              if (typeof openCodeChat !== 'undefined' && openCodeChat && openCodeChat.open) {
                openCodeChat.open();
              } else if (typeof window !== 'undefined' && window.openCodeChat && window.openCodeChat.open) {
                window.openCodeChat.open();
              }
              newTermDropdown.style.display = 'none';
              if (btnNewTermDropdown) btnNewTermDropdown.setAttribute('aria-expanded', 'false');
              return;
            }

            const agentType = item.getAttribute('data-terminal-type') || 'bash';
            const role = item.getAttribute('data-role') || 'agent';
            const name = item.querySelector('div div') ? item.querySelector('div div').textContent.trim() : 'Terminal';

            if (currentProjectId) {
              recordRecentProject(currentProjectId);
              renderWorktreeSidebar();
            }

            if (agentType === 'zeus-chat' || role === 'visual-chat') {
              this.openZeusChat();
              newTermDropdown.style.display = 'none';
              if (btnNewTermDropdown) btnNewTermDropdown.setAttribute('aria-expanded', 'false');
              return;
            }

            if (agentType === 'opencode-visual' || name.includes('Chat Visual (OpenCode)')) {
              import('./subagent_tabs.js').then(mod => {
                if (mod && mod.openSubagentTab) {
                  mod.openSubagentTab({
                    role: 'agent',
                    type: 'builder',
                    agentType: 'opencode',
                    name: 'Chat Visual (OpenCode)',
                    title: '🤖 [Builder] Chat Visual (OpenCode)',
                    status: 'RUNNING'
                  });
                }
              }).catch(() => {
                this.createSession({
                  agentType: 'opencode',
                  role: 'agent',
                  name: 'Chat Visual (OpenCode)',
                  cwd: this.getActiveProjectRoot()
                });
              });
              newTermDropdown.style.display = 'none';
              if (btnNewTermDropdown) btnNewTermDropdown.setAttribute('aria-expanded', 'false');
              return;
            }

            this.createSession({
              agentType,
              role,
              name,
              cwd: this.getActiveProjectRoot()
            });

            newTermDropdown.style.display = 'none';
            if (btnNewTermDropdown) btnNewTermDropdown.setAttribute('aria-expanded', 'false');
          });
        });

        document.addEventListener('click', () => {
          newTermDropdown.style.display = 'none';
          if (btnNewTermDropdown) btnNewTermDropdown.setAttribute('aria-expanded', 'false');
        });
      }
    } else if (btnNewTerm) {
      btnNewTerm.addEventListener('click', () => {
        if (currentProjectId) {
          recordRecentProject(currentProjectId);
          renderWorktreeSidebar();
        }
        this.createSession({ role: 'orchestrator' });
      });
    }

    // Botão alternar largura total (recolher/expandir barra lateral de telemetria)
    const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
    if (btnToggleSidebar) {
      btnToggleSidebar.addEventListener('click', () => {
        const wrapper = document.querySelector('.workspace-wrapper');
        if (wrapper) {
          wrapper.classList.toggle('collapse-sidebar');
          const isCollapsed = wrapper.classList.contains('collapse-sidebar');
          btnToggleSidebar.classList.toggle('active', isCollapsed);
          this.fitAll();
        }
      });
    }

    // Botão e Modal de Terminais Ativos
    const btnActiveTerm = document.getElementById('btn-active-terminals');
    if (btnActiveTerm) {
      btnActiveTerm.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openActiveTerminalsModal();
      });
    }

    const btnCloseModal = document.getElementById('btn-close-active-terminals');
    const btnCloseFooter = document.getElementById('btn-active-terminals-close-footer');
    if (btnCloseModal) btnCloseModal.addEventListener('click', () => this.closeActiveTerminalsModal());
    if (btnCloseFooter) btnCloseFooter.addEventListener('click', () => this.closeActiveTerminalsModal());

    const btnShowAll = document.getElementById('btn-active-terminals-show-all');
    if (btnShowAll) {
      btnShowAll.addEventListener('click', () => {
        this.showAllSessions();
        this.renderActiveTerminalsList();
      });
    }

    const btnHideAll = document.getElementById('btn-active-terminals-hide-all');
    if (btnHideAll) {
      btnHideAll.addEventListener('click', () => {
        this.hideAllSessions();
        this.renderActiveTerminalsList();
      });
    }

    const modalActiveTerm = document.getElementById('modal-active-terminals');
    if (modalActiveTerm) {
      modalActiveTerm.addEventListener('click', (e) => {
        if (e.target === modalActiveTerm) {
          this.closeActiveTerminalsModal();
        }
      });
    }

    // Redimensionamento global da janela
    window.addEventListener('resize', () => {
      this.fitAll();
    });

    // Aplica modo de layout configurado
    this.setLayoutMode(this.layout || 'grid');

    // Inicializa controles de abas estilo Chrome, filtros e popovers
    this.initTabsBarControls();

    // Inicializa contexto do projeto ativo sincronizando do backend em disco
    const initialContext = currentProjectId ? `project:${currentProjectId}` : 'global';
    this.syncSessionsWithBackend(currentProjectId).then(() => {
      this.switchContext(initialContext, this.getActiveProjectRoot(), true);
    }).catch(() => {
      this.switchContext(initialContext, this.getActiveProjectRoot(), true);
    });

    if (typeof window !== 'undefined' && typeof window.checkOmniRouteStatus === 'function') {
      window.checkOmniRouteStatus();
    }

    // Observador reativo de temas para instâncias do Xterm.js
    const updateAllTerminalThemes = () => {
      const themeObj = this.getTerminalTheme();
      this.sessions.forEach(session => {
        if (session && session.term && session.term.options) {
          session.term.options.theme = themeObj;
          session.term.options.minimumContrastRatio = 4.5;
        }
      });
    };

    if (typeof MutationObserver !== 'undefined' && typeof document !== 'undefined' && document.documentElement) {
      const themeObserver = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          if (mutation.type === 'attributes' && mutation.attributeName === 'data-theme') {
            updateAllTerminalThemes();
            break;
          }
        }
      });
      themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('theme-changed', () => updateAllTerminalThemes());
    }
  }

  getActiveProjectRoot(projectId = null) {
    return getActiveProjectRoot(projectId || currentProjectId, knownProjects);
  }

  getSliceCwd(sliceId, projectId = null) {
    const pid = projectId || currentProjectId;
    const root = this.getActiveProjectRoot(pid);
    if (!root) return '';
    return `${root}/.worktrees/${sliceId}`;
  }

  formatCwd(cwd) {
    if (!cwd) return 'cockpit-root';
    const parts = cwd.replace(/\\/g, '/').split('/').filter(Boolean);
    return parts.length > 0 ? parts[parts.length - 1] : cwd;
  }

  createSession(options = {}) {
    if (!this.tabsBar) {
      this.tabsBar = document.getElementById('terminal-tabs-bar');
    }
    if (!this.gridContainer) {
      this.gridContainer = document.getElementById('terminal-workspace-grid');
    }

    const isVisualChat = (options.role === 'visual-chat');

    if (typeof Terminal === 'undefined' && !isVisualChat) {
      if (this.gridContainer) {
        this.gridContainer.innerHTML = '<div style="color: #ef4444; padding: 20px; font-family: monospace;">Aguardando carregamento da biblioteca xterm.js...</div>';
      }
      return null;
    }

    if (!this.tabsBar || !this.gridContainer) {
      return null;
    }

    this.counter++;
    const id = options.id || (isVisualChat ? 'zeus-chat' : `term-${Date.now()}-${this.counter}`);
    const contextKey = options.contextKey || this.activeContextKey || (currentProjectId ? `project:${currentProjectId}` : 'global');
    let projectId = options.projectId;
    let taskId = options.taskId;

    if (!projectId) {
      if (contextKey.startsWith('slice:')) {
        const parts = contextKey.split(':');
        projectId = parts[1];
        taskId = taskId || parts[2];
      } else if (contextKey.startsWith('project:')) {
        projectId = contextKey.slice(8);
      } else {
        projectId = currentProjectId || null;
      }
    }

    const role = options.role || (options.taskId ? 'agent' : 'orchestrator');
    const sliceId = options.sliceId || (role === 'agent' ? (activeSliceId || options.taskId) : null);
    const agentType = options.agentType || (isVisualChat ? 'zeus' : (options.name && options.name.toLowerCase().includes('claude') ? 'claude' : (options.name && options.name.toLowerCase().includes('opencode') ? 'opencode' : 'bash')));
    const defaultName = isVisualChat
      ? 'Zeus Chat'
      : (role === 'orchestrator'
        ? (this.counter === 1 ? 'Orquestrador' : `Orquestrador #${this.counter}`)
        : (role === 'agent'
          ? (sliceId ? `Agente (${sliceId})` : `Agente da Frota #${this.counter}`)
          : (taskId ? `Subagente (${taskId})` : `Subagente #${this.counter}`)));
    const name = options.name || defaultName;
    const cwd = options.cwd || (sliceId ? this.getSliceCwd(sliceId, projectId) : (taskId ? this.getSliceCwd(taskId, projectId) : this.getActiveProjectRoot()));
    const model = this.getCurrentModel();
    const branchOrSlice = sliceId ? `slice/${sliceId}` : (taskId ? `task/${taskId}` : this.getCurrentSliceOrBranch());
    const relCwd = this.formatRelativeCwd(cwd);
    const iconHtml = this.getAgentIcon(agentType);
    const roleIcon = this.getRoleIcon(role);
    const roleTitle = this.getRoleTitle(role);
    const roleBadgeHtml = this.getRoleBadgeHtml(role);
    const rolePerms = this.getRolePermissionsText(role);

    // 1. Instância do Xterm ou Adaptador de Chat Visual
    let term = null;
    let fitAddon = null;
    if (!isVisualChat && typeof Terminal !== 'undefined') {
      term = new Terminal({
        cursorBlink: true,
        cursorStyle: 'block',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 13,
        lineHeight: 1.25,
        minimumContrastRatio: 4.5,
        theme: this.getTerminalTheme()
      });

      if (typeof FitAddon !== 'undefined' && FitAddon.FitAddon) {
        fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
      }
      if (typeof WebLinksAddon !== 'undefined' && WebLinksAddon.WebLinksAddon) {
        term.loadAddon(new WebLinksAddon.WebLinksAddon());
      }
    } else {
      term = {
        focus: () => {
          if (elPane) {
            const inp = elPane.querySelector('.zeus-chat-input');
            if (inp) inp.focus();
          }
        },
        dispose: () => {},
        write: () => {},
        onData: () => {}
      };
    }

    // 2. Elementos DOM (Aba e Painel Minimalista - Issue #10 e Issue #24)
    const elTab = document.createElement('div');
    elTab.className = `term-tab orca-tab role-${role}`;
    elTab.id = `tab-${id}`;
    elTab.setAttribute('data-session-id', id);
    elTab.setAttribute('data-role', role);
    elTab.innerHTML = `
      <span class="term-tab-dot connected" title="Status de Conexão"></span>
      <span class="term-tab-icon">${iconHtml}</span>
      <span class="term-tab-title orca-tab-title" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
      ${roleBadgeHtml}
      <button class="term-tab-close orca-tab-close" title="Encerrar terminal">×</button>
    `;

    const orchestratorControlHtml = role === 'orchestrator' ? `
      <div class="orchestrator-subagents-wrap" id="subagents-wrap-${id}">
        <button class="action-btn secondary btn-sm btn-orchestrator-subagents" data-session-id="${id}" title="Subagentes vinculados a este Orquestrador">
          <span>⚡ Subagentes</span>
          <span class="subagents-count">(0)</span>
          <span class="subagents-arrow">▾</span>
        </button>
        <div class="orchestrator-subagents-dropdown" id="subagents-drop-${id}" style="display: none;">
          <div class="subagents-dropdown-header">
            <span>Subagentes Vinculados</span>
            <button class="btn-spawn-subagent-quick" data-parent-id="${id}" title="Invocar Subagente">+ Novo Subagente</button>
          </div>
          <div class="subagents-dropdown-list" id="subagents-list-${id}">
            <div class="subagents-empty-msg">Nenhum subagente ativo no momento</div>
          </div>
        </div>
      </div>
    ` : `<span class="orca-role-badge role-${role}" title="${roleTitle}">${roleIcon} ${roleTitle}</span>`;

    const elPane = document.createElement('div');
    elPane.className = `terminal-pane orca-split-pane ${isVisualChat ? 'zeus-chat-pane' : ''}`;
    elPane.id = `pane-${id}`;
    elPane.setAttribute('data-session-id', id);
    elPane.setAttribute('data-role', role);

    if (isVisualChat) {
      elPane.innerHTML = `
        <div class="orca-pane-header zeus-chat-pane-header">
          <div class="orca-tab-strip" style="display: flex; align-items: center; width: 100%;">
            <div class="orca-tab active">
              <span class="orca-tab-icon">${iconHtml}</span>
              <span class="orca-tab-title">${escapeHtml(name)}</span>
            </div>
            <span class="orca-role-badge role-visual-chat" title="Zeus Master Chat">
              <img src="/zeus_terminal_god.svg" style="width: 12px; height: 12px; vertical-align: middle; margin-right: 4px;" alt="" /> Zeus Chat
            </span>
            <select class="zeus-model-select zeus-pane-model-select" style="margin-left: 8px; height: 24px; font-size: 11px; padding: 0 6px;" title="Selecionar modelo de IA"></select>
            <div class="orca-pane-controls ml-auto" style="display: flex; align-items: center; gap: 4px;">
              <button type="button" class="zeus-btn-skills zeus-pane-btn-skills action-btn btn-sm" style="height: 24px; padding: 0 8px; font-size: 10px;" title="Configurar Skills e MCPs">⚡ Skills & MCPs</button>
              <button class="orca-pane-btn zeus-btn-clear-history" id="btn-clear-zeus-chat" title="Limpar Mensagens">🗑️</button>
              <button class="orca-pane-btn orca-btn-minimize" title="Minimizar (Ocultar Terminal)">–</button>
              <button class="orca-pane-btn orca-btn-close danger" title="Fechar sessão (×)">×</button>
            </div>
          </div>
        </div>
        <div class="pane-body zeus-chat-pane-body" style="width: 100%; height: calc(100% - 35px); display: flex; flex-direction: column; overflow: hidden; background: var(--bg-void, #0c0e11);">
          <div class="zeus-chat-messages" id="zeus-chat-messages" style="flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 12px;"></div>
          <div class="zeus-attachments-preview" style="display: none; padding: 6px 14px; background: rgba(0,0,0,0.2); gap: 8px; flex-wrap: wrap;"></div>
          <div class="zeus-chat-input-bar" style="border-top: 1px solid var(--border-subtle, #23282f); padding: 10px 14px; display: flex; gap: 8px; background: var(--bg-surface, #111417); align-items: flex-end;">
            <button type="button" class="zeus-btn-attach" title="Anexar imagem (ou cole com Ctrl+V)" style="height: 38px; width: 38px; min-width: 38px;">📷</button>
            <input type="file" class="zeus-file-input" accept="image/*" multiple style="display: none;" />
            <button type="button" class="zeus-btn-mic" title="Gravar áudio (STT em RAM)" style="height: 38px; width: 38px; min-width: 38px;">🎙️</button>
            <textarea class="zeus-chat-input" id="zeus-chat-input" placeholder="Comunique-se com o Orquestrador Zeus ou despache subagentes..." rows="1" style="flex: 1; resize: none; min-height: 38px; max-height: 120px; padding: 8px 12px; border-radius: 6px; background: var(--bg-card, #181b20); border: 1px solid var(--border, #23282f); color: var(--foreground, #f4f4f5); font-family: 'JetBrains Mono', monospace; font-size: 13px; outline: none;"></textarea>
            <button class="action-btn primary btn-sm btn-send-zeus-chat" id="btn-send-zeus-chat" style="height: 38px; padding: 0 14px; display: inline-flex; align-items: center; gap: 6px; font-weight: 600;">
              <span>Enviar</span>
              <span>⚡</span>
            </button>
          </div>
        </div>
      `;
    } else {
      elPane.innerHTML = `
        <div class="orca-pane-header">
          <div class="orca-tab-strip">
            <div class="orca-tab active">
              <span class="orca-tab-icon">${iconHtml}</span>
              <span class="orca-tab-title">${escapeHtml(name)}</span>
            </div>
            ${orchestratorControlHtml}
            <div class="orca-pane-controls ml-auto">
              ${role === 'subagent' ? '<button class="orca-pane-btn orca-btn-terminate-subagent danger" title="Encerrar Subagente">Encerrar Subagente</button>' : ''}
              <button class="orca-pane-btn orca-btn-minimize" title="Minimizar (Ocultar Terminal)">–</button>
              <button class="orca-pane-btn orca-btn-close danger" title="Fechar sessão (×)">×</button>
            </div>
          </div>
        </div>
        <div class="pane-body">
          <div class="xterm-mount" style="width: 100%; height: 100%; position: relative;"></div>
        </div>
      `;
    }

    // Botão "+" na barra de abas
    let btnAddTab = document.getElementById('btn-tab-add-wrap') || document.getElementById('btn-tab-add');
    if (!btnAddTab) {
      this.initTabsBarControls();
      btnAddTab = document.getElementById('btn-tab-add-wrap') || document.getElementById('btn-tab-add');
    }

    if (btnAddTab && btnAddTab.parentNode === this.tabsBar) {
      this.tabsBar.insertBefore(elTab, btnAddTab);
    } else {
      this.tabsBar.appendChild(elTab);
    }
    this.gridContainer.appendChild(elPane);

    let assignedSlot = null;
    if (this.layout === 'free' || this.gridContainer.classList.contains('layout-free')) {
      assignedSlot = this.findNextFreeSlot();
      elPane.style.position = 'absolute';
      elPane.style.left = `${assignedSlot.x}px`;
      elPane.style.top = `${assignedSlot.y}px`;
      elPane.style.width = '580px';
      elPane.style.height = '440px';
    }

    const mountEl = elPane.querySelector('.xterm-mount');
    if (!isVisualChat && term && term.open) {
      if (mountEl) term.open(mountEl);
    }

    // 3. Estrutura da Sessão
    const session = {
      id,
      name,
      role,
      sliceId,
      agentType,
      cwd,
      contextKey,
      projectId,
      taskId,
      term,
      fitAddon,
      socket: null,
      isConnected: false,
      isMinimized: false,
      hasLaunchedAgent: false,
      customPos: assignedSlot,
      customWidth: 580,
      customHeight: 440,
      elPane,
      elTab,
      resizeObserver: null,
      focusInput: () => {
        if (term && term.focus) term.focus();
      }
    };
    this.sessions.set(id, session);

    // Persistência REST no backend
    apiFetch('/api/terminal/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: id,
        project_id: projectId,
        task_id: taskId,
        role,
        name,
        agent_type: agentType,
        agent_name: options.agentName || null,
        slice_id: sliceId,
        cwd
      })
    }).catch(() => {});

    if (!this.contextSessions.has(contextKey)) {
      this.contextSessions.set(contextKey, new Set());
    }
    this.contextSessions.get(contextKey).add(id);

    // Ajusta visibilidade baseada no contexto ativo
    const isVisible = (!this.activeContextKey || this.activeContextKey === contextKey);
    elTab.style.display = isVisible ? '' : 'none';
    elPane.classList.toggle('context-hidden', !isVisible);
    elPane.style.display = isVisible ? '' : 'none';

    // 4. WebSocket Conexão / Inicialização do Chat Visual
    if (!isVisualChat) {
      this.connectSessionSocket(session);

      // 5. Eventos de Entrada no Terminal
      term.onData(data => {
        if (session.socket && session.socket.readyState === WebSocket.OPEN) {
          session.socket.send(data);
        }
        if (data && (data.includes('\r') || data.includes('\n'))) {
          const pid = session.projectId || currentProjectId;
          if (pid) {
            recordRecentProject(pid);
          }
        }
      });
    } else {
      session.isConnected = true;
      import('./zeus_chat_workspace.js').then(mod => {
        if (mod && mod.zeusChatWorkspace) {
          mod.zeusChatWorkspace.attachPane(session, elPane);
        }
      }).catch(() => {});
    }

    // 6. Eventos de Interação DOM
    elTab.addEventListener('click', (e) => {
      if (e.target.classList.contains('term-tab-close') || e.target.classList.contains('orca-tab-close')) {
        this.closeSession(id);
      } else {
        this.selectSession(id);
      }
    });

    elPane.addEventListener('mousedown', () => {
      document.querySelectorAll('.terminal-pane').forEach(p => p.style.zIndex = '1');
      elPane.style.zIndex = '10';
      this.selectSession(id, false);
    });

    this.enablePaneDragging(elPane, session);

    // Botão de Subagentes Vinculados no Cabeçalho do Orquestrador (Issue #10)
    const btnSubagents = elPane.querySelector('.btn-orchestrator-subagents');
    const dropSubagents = elPane.querySelector('.orchestrator-subagents-dropdown');
    if (btnSubagents && dropSubagents) {
      btnSubagents.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = (dropSubagents.style.display !== 'none');
        document.querySelectorAll('.orchestrator-subagents-dropdown').forEach(d => d.style.display = 'none');
        dropSubagents.style.display = isOpen ? 'none' : 'block';
        if (!isOpen) {
          this.renderSubagentsListForOrchestrator(id);
        }
      });
    }

    const btnSpawnSub = elPane.querySelector('.btn-spawn-subagent-quick');
    if (btnSpawnSub) {
      btnSpawnSub.addEventListener('click', (e) => {
        e.stopPropagation();
        if (dropSubagents) dropSubagents.style.display = 'none';
        this.createSession({
          role: 'subagent',
          name: `Subagente (${name})`,
          agentType: 'bash',
          cwd: cwd
        });
        this.updateSubagentsBadge(id);
      });
    }

    const btnMinimize = elPane.querySelector('.orca-btn-minimize');
    if (btnMinimize) {
      btnMinimize.addEventListener('click', (e) => {
        e.stopPropagation();
        this.minimizeSession(id);
      });
    }

    const btnClose = elPane.querySelector('.orca-btn-close');
    if (btnClose) {
      btnClose.addEventListener('click', (e) => {
        e.stopPropagation();
        this.closeSession(id);
      });
    }

    const btnTerminateSub = elPane.querySelector('.orca-btn-terminate-subagent');
    if (btnTerminateSub) {
      btnTerminateSub.addEventListener('click', (e) => {
        e.stopPropagation();
        this.closeSession(id);
      });
    }

    // Seletor de tipo de agente no cabeçalho
    const agentSelect = elPane.querySelector('.orca-agent-select');
    if (agentSelect) {
      agentSelect.addEventListener('change', (e) => {
        e.stopPropagation();
        this.setSessionAgent(id, e.target.value, true);
      });
    }

    // ResizeObserver para redimensionamento perfeito em tempo real
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => {
        if (session.elPane.offsetParent !== null && session.fitAddon && session.term) {
          try {
            session.fitAddon.fit();
            if (session.socket && session.socket.readyState === WebSocket.OPEN && session.term.cols > 0 && session.term.rows > 0) {
              session.socket.send(JSON.stringify({
                type: 'resize',
                cols: session.term.cols,
                rows: session.term.rows
              }));
            }
          } catch (e) {}
        }
      });
      ro.observe(elPane);
      if (mountEl) ro.observe(mountEl);
      session.resizeObserver = ro;
    }

    // Seleciona a sessão criada
    this.selectSession(id);
    if (this.layout === 'dynamic') {
      this.applyDynamicSplit();
    } else {
      this.fitAll();
    }

    this.updateActiveTerminalsCount();
    return session;
  }

  openZeusChat() {
    // 1. Procura se já existe sessão de Zeus Chat ativa
    for (const [id, s] of this.sessions) {
      if (s.role === 'visual-chat' || id === 'zeus-chat' || s.name === 'Zeus Chat') {
        this.selectSession(id);
        if (s.focusInput) s.focusInput();
        return s;
      }
    }

    // 2. Cria nova sessão nativa visual-chat no TerminalWorkspaceManager
    const session = this.createSession({
      id: 'zeus-chat',
      role: 'visual-chat',
      name: 'Zeus Chat',
      agentType: 'zeus',
      cwd: this.getActiveProjectRoot ? this.getActiveProjectRoot() : '/'
    });

    if (session) {
      this.selectSession(session.id);
      if (session.focusInput) session.focusInput();
    }
    return session;
  }

  enablePaneDragging(elPane, session) {
    const header = elPane.querySelector('.orca-pane-header');
    if (!header) return;

    header.style.cursor = 'grab';

    let isDragging = false;
    let startMouseX = 0;
    let startMouseY = 0;
    let startPaneX = 0;
    let startPaneY = 0;

    const onMouseDown = (e) => {
      // Não inicia arrasto ao clicar em botões, selects, links ou dropdowns
      if (e.target.closest('button, select, input, a, .orca-agent-picker-wrap, .orchestrator-subagents-dropdown, .btn-orchestrator-subagents, .orca-btn-close, .orca-btn-terminate-subagent')) {
        return;
      }
      if (e.button !== 0) return;

      isDragging = true;
      header.style.cursor = 'grabbing';
      elPane.classList.add('is-dragging');

      // Traz o painel arrastado para a camada de foco superior
      document.querySelectorAll('.terminal-pane').forEach(p => p.style.zIndex = '1');
      elPane.style.zIndex = '100';
      this.selectSession(session.id, false);

      // Garante modo livre no gridContainer
      if (!this.gridContainer.classList.contains('layout-free')) {
        this.gridContainer.classList.add('layout-free');
        this.gridContainer.classList.remove('layout-grid', 'layout-side-by-side', 'layout-stacked');
        this.layout = 'free';
        localStorage.setItem('cockpit_terminal_layout', 'free');
        document.querySelectorAll('#grid-config-dropdown .grid-config-item').forEach(item => {
          item.classList.toggle('active', item.getAttribute('data-grid-layout') === 'free');
        });
      }

      const gridRect = this.gridContainer.getBoundingClientRect();
      const paneRect = elPane.getBoundingClientRect();

      // Posição normalizada no sistema de coordenadas do canvas (dividindo pelo zoomLevel)
      startPaneX = (paneRect.left - gridRect.left) / this.zoomLevel;
      startPaneY = (paneRect.top - gridRect.top) / this.zoomLevel;

      if (!elPane.style.width) {
        elPane.style.width = `${Math.max(480, paneRect.width / this.zoomLevel)}px`;
      }
      if (!elPane.style.height) {
        elPane.style.height = `${Math.max(340, paneRect.height / this.zoomLevel)}px`;
      }

      elPane.style.position = 'absolute';
      elPane.style.left = `${startPaneX}px`;
      elPane.style.top = `${startPaneY}px`;

      startMouseX = e.clientX;
      startMouseY = e.clientY;

      e.preventDefault();
      e.stopPropagation();

      const onMouseMove = (moveEvt) => {
        if (!isDragging) return;
        const deltaX = (moveEvt.clientX - startMouseX) / this.zoomLevel;
        const deltaY = (moveEvt.clientY - startMouseY) / this.zoomLevel;

        const newLeft = Math.max(0, startPaneX + deltaX);
        const newTop = Math.max(0, startPaneY + deltaY);

        elPane.style.left = `${newLeft}px`;
        elPane.style.top = `${newTop}px`;
        session.customPos = { x: newLeft, y: newTop };
      };

      const onMouseUp = () => {
        if (!isDragging) return;
        isDragging = false;
        header.style.cursor = 'grab';
        elPane.classList.remove('is-dragging');
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);

        if (session.fitAddon && session.term) {
          try { session.fitAddon.fit(); } catch (_) {}
        }
      };

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    };

    header.addEventListener('mousedown', onMouseDown);
  }

  setSessionAgent(sessionId, newAgentType, autoLaunch = false) {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    session.agentType = newAgentType;
    session.name = this.getAgentDisplayName(newAgentType, this.counter);

    const iconHtml = this.getAgentIcon(newAgentType);

    // Atualiza tab bar interna do painel
    const paneIcon = session.elPane.querySelector('.orca-tab-icon');
    if (paneIcon) paneIcon.innerHTML = iconHtml;
    const paneTitle = session.elPane.querySelector('.orca-tab-title');
    if (paneTitle) paneTitle.textContent = session.name;

    const selectEl = session.elPane.querySelector('.orca-agent-select');
    if (selectEl && selectEl.value !== newAgentType) {
      selectEl.value = newAgentType;
    }

    // Atualiza tab bar do topo
    const topTabIcon = session.elTab.querySelector('.term-tab-icon');
    if (topTabIcon) topTabIcon.innerHTML = iconHtml;
    const topTabTitle = session.elTab.querySelector('.term-tab-title');
    if (topTabTitle) topTabTitle.textContent = session.name;

    // Se autoLaunch estiver habilitado e houver comando correspondente, dispara
    if (autoLaunch) {
      const cmd = this.getAgentCommand(newAgentType);
      if (cmd) {
        this.sendToSession(sessionId, cmd);
      }
    }

    this.updateHeaderBadge();
  }

  splitSession(sourceSessionId) {
    if (this.layout === 'tabs') {
      this.setLayout('split', true);
    } else if (this.layout === 'split') {
      this.setLayout('grid', true);
    } else {
      this.createSession();
    }
  }

  connectSessionSocket(session) {
    if (session.socket) {
      try { session.socket.close(); } catch (e) {}
    }

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const params = new URLSearchParams();
    params.set('session_id', session.id);
    if (session.cwd) params.set('cwd', session.cwd);
    const pid = session.projectId || currentProjectId;
    if (pid) params.set('project_id', pid);
    if (session.taskId) params.set('task_id', session.taskId);
    if (session.role) params.set('role', session.role);
    if (session.name) params.set('name', session.name);
    if (session.agentType) params.set('agent_type', session.agentType);
    if (session.agentName) params.set('agent_name', session.agentName);
    if (session.sliceId) params.set('slice_id', session.sliceId);
    if (session.taskId) params.set('task_id', session.taskId);

    const url = `${proto}//${window.location.host}/ws/terminal?${params.toString()}`;
    const dot = session.elTab.querySelector('.term-tab-dot');

    const ws = new WebSocket(url);
    session.socket = ws;

    ws.onopen = () => {
      session.isConnected = true;
      if (dot) dot.className = 'term-tab-dot active';
      this.updateHeaderBadge();

      const doFitAndResize = () => {
        if (session.fitAddon && session.term && session.elPane && session.elPane.offsetParent !== null) {
          try {
            session.fitAddon.fit();
            if (ws.readyState === WebSocket.OPEN && session.term.cols > 0 && session.term.rows > 0) {
              ws.send(JSON.stringify({
                type: 'resize',
                cols: session.term.cols,
                rows: session.term.rows
              }));
            }
          } catch (e) {}
        }
      };

      setTimeout(doFitAndResize, 50);
      setTimeout(doFitAndResize, 200);
      setTimeout(doFitAndResize, 500);

      // Auto-inicia o comando do agente se especificado (ex: OpenCode, Claude Code, Codex)
      if (session.agentType && session.agentType !== 'bash' && !session.hasLaunchedAgent) {
        session.hasLaunchedAgent = true;
        const cmd = this.getAgentCommand(session.agentType);
        if (cmd) {
          setTimeout(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(cmd);
            }
          }, 350);
        }
      }
    };

    ws.onmessage = (event) => {
      session.term.write(event.data);
    };

    ws.onclose = () => {
      session.isConnected = false;
      if (dot) dot.className = 'term-tab-dot disconnected';
      this.updateHeaderBadge();
      session.term.write('\r\n\x1b[33m[PTY desconectado. Clique em ⟳ para reiniciar a sessão]\x1b[0m\r\n');
    };

    ws.onerror = () => {
      session.isConnected = false;
      if (dot) dot.className = 'term-tab-dot disconnected';
      this.updateHeaderBadge();
    };
  }

  selectSession(id, focus = true) {
    if (!this.sessions.has(id)) return;
    this.activeSessionId = id;

    const current = this.sessions.get(id);
    if (current && current.contextKey) {
      this.activeContextKey = current.contextKey;
    }

    // Atualiza tabs e panes pertencentes ao contexto ativo
    const contextSessions = this.getActiveContextSessions();
    contextSessions.forEach(s => {
      const isActive = (s.id === id);
      s.elTab.classList.toggle('active', isActive);
      s.elPane.classList.toggle('active-pane', isActive);
    });

    this.updateHeaderBadge();

    if (current && focus) {
      setTimeout(() => {
        current.term.focus();
      }, 50);
    }
  }

  closeSession(id) {
    const session = this.sessions.get(id);
    if (!session) return;

    if (session.contextKey && this.contextSessions.has(session.contextKey)) {
      this.contextSessions.get(session.contextKey).delete(id);
      if (this.contextSessions.get(session.contextKey).size === 0) {
        this.contextSessions.delete(session.contextKey);
      }
    }

    if (session.resizeObserver) {
      try { session.resizeObserver.disconnect(); } catch (e) {}
      session.resizeObserver = null;
    }

    if (session.socket) {
      try { session.socket.close(); } catch (e) {}
    }

    // Notifica backend
    apiFetch(`/api/terminal/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }).catch(() => {});

    // Remove elementos do DOM
    if (session.elTab && session.elTab.parentNode) {
      session.elTab.parentNode.removeChild(session.elTab);
    }
    if (session.elPane && session.elPane.parentNode) {
      session.elPane.parentNode.removeChild(session.elPane);
    }

    try {
      session.term.dispose();
    } catch (e) {}

    this.sessions.delete(id);

    // Seleciona outra sessão do mesmo contexto se a atual foi fechada
    if (this.activeSessionId === id) {
      const remainingContextSessions = this.getActiveContextSessions();
      if (remainingContextSessions.length > 0) {
        this.selectSession(remainingContextSessions[remainingContextSessions.length - 1].id);
      } else {
        this.createSession({ contextKey: this.activeContextKey, name: 'Term 1' });
      }
    }

    if (this.layout === 'dynamic') {
      this.applyDynamicSplit();
    } else {
      this.fitAll();
    }

    this.updateActiveTerminalsCount();
  }

  setLayout(layout, autoSpawn = true) {
    if (!['dynamic', 'tabs', 'split', 'grid'].includes(layout)) layout = 'dynamic';
    this.layout = layout;
    localStorage.setItem('cockpit_terminal_layout', layout);

    if (layout === 'dynamic') {
      this.applyDynamicSplit();
      return;
    }

    // Atualiza botões
    const layoutPicker = document.getElementById('terminal-layout-picker');
    if (layoutPicker) {
      layoutPicker.querySelectorAll('.layout-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-layout') === layout);
      });
    }

    // Atualiza container
    if (this.gridContainer) {
      this.gridContainer.className = `terminal-workspace-grid layout-${layout}`;
    }

    // Auto-cria sessões se necessário para Split ou Grid
    if (autoSpawn) {
      const contextSessions = this.getActiveContextSessions();
      if (layout === 'split' && contextSessions.length < 2) {
        this.createSession({ contextKey: this.activeContextKey, name: 'Term 2' });
      } else if (layout === 'grid' && contextSessions.length < 4) {
        const needed = 4 - contextSessions.length;
        for (let i = 0; i < needed; i++) {
          this.createSession({ contextKey: this.activeContextKey, name: `Term ${contextSessions.length + 1}` });
        }
      }
    }

    this.fitAll();
    setTimeout(() => this.fitAll(), 160);
  }

  fitAll() {
    setTimeout(() => {
      const visibleSessions = this.getActiveContextSessions();
      visibleSessions.forEach(session => {
        if (session.elPane && session.elPane.offsetParent !== null && session.fitAddon && session.term) {
          try {
            session.fitAddon.fit();
            if (session.socket && session.socket.readyState === WebSocket.OPEN) {
              session.socket.send(JSON.stringify({
                type: 'resize',
                cols: session.term.cols,
                rows: session.term.rows
              }));
            }
          } catch (e) {}
        }
      });
    }, 60);
  }

  sendToSession(sessionId, cmd) {
    const session = this.sessions.get(sessionId);
    if (!session) return;
    const pid = session.projectId || currentProjectId;
    if (pid) {
      recordRecentProject(pid);
      renderWorktreeSidebar();
    }
    if (session.socket && session.socket.readyState === WebSocket.OPEN) {
      session.socket.send(cmd + '\r');
      session.term.focus();
    } else {
      this.connectSessionSocket(session);
      setTimeout(() => {
        if (session.socket && session.socket.readyState === WebSocket.OPEN) {
          session.socket.send(cmd + '\r');
          session.term.focus();
        }
      }, 500);
    }
  }

  sendToActive(cmd) {
    const contextSessions = this.getActiveContextSessions();
    if (contextSessions.length === 0) {
      const newSess = this.createSession({ contextKey: this.activeContextKey });
      if (newSess) {
        setTimeout(() => this.sendToSession(newSess.id, cmd), 600);
      }
      return;
    }
    const current = this.activeSessionId ? this.sessions.get(this.activeSessionId) : null;
    if (current && current.contextKey === this.activeContextKey) {
      this.sendToSession(this.activeSessionId, cmd);
    } else {
      this.sendToSession(contextSessions[0].id, cmd);
    }
  }

  updatePaneContexts() {
    // Subtítulos e statuslines foram limpos para evitar poluição visual (Issue #10)
  }

  renderSubagentsListForOrchestrator(parentId) {
    const listEl = document.getElementById(`subagents-list-${parentId}`);
    if (!listEl) return;

    const subagents = Array.from(this.sessions.values()).filter(s => s.role === 'subagent');
    if (subagents.length === 0) {
      listEl.innerHTML = '<div class="subagents-empty-msg">Nenhum subagente ativo no momento</div>';
      return;
    }

    listEl.innerHTML = '';
    subagents.forEach(sub => {
      const item = document.createElement('div');
      item.className = 'subagent-dropdown-item';
      item.innerHTML = `
        <div class="subagent-item-info">
          <span class="subagent-dot ${sub.isConnected ? 'connected' : 'disconnected'}">●</span>
          <span class="subagent-title">${escapeHtml(sub.name)}</span>
        </div>
        <button class="action-btn secondary btn-xs btn-focus-subagent" title="Focar Subagente">Focar</button>
      `;
      const btnFocus = item.querySelector('.btn-focus-subagent');
      if (btnFocus) {
        btnFocus.addEventListener('click', (e) => {
          e.stopPropagation();
          const drop = document.getElementById(`subagents-drop-${parentId}`);
          if (drop) drop.style.display = 'none';
          this.selectSession(sub.id);
          if (sub.elPane) {
            sub.elPane.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        });
      }
      listEl.appendChild(item);
    });
  }

  updateSubagentsBadge(parentId) {
    const wrap = document.getElementById(`subagents-wrap-${parentId}`);
    if (!wrap) return;
    const countEl = wrap.querySelector('.subagents-count');
    if (!countEl) return;
    const subagents = Array.from(this.sessions.values()).filter(s => s.role === 'subagent');
    countEl.textContent = `(${subagents.length})`;
  }

  updateHeaderBadge() {
    const badge = document.getElementById('terminal-session-badge');
    if (!badge) return;

    const total = this.getActiveContextSessions().length;
    const active = this.activeSessionId ? this.sessions.get(this.activeSessionId) : null;
    const activeName = active ? active.name : 'Nenhum';
    const status = active && active.isConnected ? 'Conectado' : 'Pronto';
    const layoutName = this.layout ? this.layout.toUpperCase() : 'GRID';

    badge.textContent = `${total} Sessões | ${activeName} (${status}) | Layout: ${layoutName}`;
  }

  switchContext(contextKey, defaultCwd = null, autoCreate = true) {
    if (!contextKey) return;
    this.activeContextKey = contextKey;

    if (!this.tabsBar) this.tabsBar = document.getElementById('terminal-tabs-bar');
    if (!this.gridContainer) this.gridContainer = document.getElementById('terminal-workspace-grid');

    // Atualiza visibilidade no DOM sem desconectar processos nem fechar sockets
    this.sessions.forEach(s => {
      const belongs = (s.contextKey === contextKey);
      if (s.elTab) s.elTab.style.display = belongs ? '' : 'none';
      if (s.elPane) {
        s.elPane.classList.toggle('context-hidden', !belongs);
        s.elPane.style.display = belongs ? '' : 'none';
      }
    });

    const contextSessions = this.getActiveContextSessions();
    if (contextSessions.length > 0) {
      const activeCurrent = this.activeSessionId ? this.sessions.get(this.activeSessionId) : null;
      if (!activeCurrent || activeCurrent.contextKey !== contextKey) {
        this.selectSession(contextSessions[0].id);
      } else {
        this.selectSession(this.activeSessionId);
      }
    } else if (autoCreate) {
      const defaultRole = contextKey.startsWith('slice:') ? 'agent' : 'orchestrator';
      const defaultName = defaultRole === 'orchestrator' ? 'Orquestrador Staff' : 'Agente da Fatia';
      const newSess = this.createSession({
        contextKey,
        cwd: defaultCwd || this.getActiveProjectRoot(),
        name: defaultName,
        role: defaultRole
      });
      if (newSess) {
        this.selectSession(newSess.id);
      }
    }

    if (this.layout === 'dynamic') {
      this.applyDynamicSplit();
    } else {
      this.fitAll();
    }
    this.updateHeaderBadge();
    this.updatePaneContexts();
    this.setRoleFilter(this.roleFilter);
  }

  async onProjectSwitched(newProjectId) {
    const newRoot = this.getActiveProjectRoot();
    try {
      await this.syncSessionsWithBackend(newProjectId);
    } catch (e) {}
    this.switchContext(`project:${newProjectId}`, newRoot, true);
  }

  onSliceSwitched(sliceId, sliceCwd = null) {
    const projId = currentProjectId || 'default';
    const cwd = sliceCwd || this.getSliceCwd(sliceId, projId);
    this.switchContext(`slice:${projId}:${sliceId}`, cwd, true);
  }

  initTabsBarControls() {
    // terminal-role-filters: filtros de papéis de agentes integrados
    if (!this.tabsBar) this.tabsBar = document.getElementById('terminal-tabs-bar');
  }

  async syncSessionsWithBackend(targetProjectId = null) {
    const pid = targetProjectId || currentProjectId || 'default';
    try {
      const res = await apiFetch(`/api/terminal/sessions?project_id=${encodeURIComponent(pid)}`);
      if (res.ok) {
        const serverSessions = await res.json();
        if (Array.isArray(serverSessions) && serverSessions.length > 0) {
          for (const s of serverSessions) {
            if (!this.sessions.has(s.session_id)) {
              this.createSession({
                id: s.session_id,
                projectId: s.project_id || pid,
                taskId: s.task_id,
                sliceId: s.slice_id,
                role: s.role || 'orchestrator',
                name: s.name,
                agentType: s.agent_type || 'bash',
                agentName: s.agent_name,
                cwd: s.cwd,
                contextKey: `project:${pid}`
              });
            }
          }
        }
      }
    } catch (err) {
      console.warn('[Terminal] Falha sincronizando sessões persistidas do backend:', err);
    }
  }

  getProjectSessions(targetProjectId = null) {
    const pid = targetProjectId || currentProjectId || 'default';
    const list = [];
    for (const session of this.sessions.values()) {
      const sPid = session.projectId || currentProjectId || 'default';
      if (sPid === pid || !targetProjectId) {
        list.push(session);
      }
    }
    return list;
  }

  updateActiveTerminalsCount() {
    const list = this.getProjectSessions();
    const badge = document.getElementById('active-terminals-count');
    if (badge) {
      badge.textContent = String(list.length);
    }
  }

  minimizeSession(id) {
    const session = this.sessions.get(id);
    if (!session) return;
    session.isMinimized = true;
    if (session.elPane) {
      session.elPane.style.display = 'none';
    }
    if (session.elTab) {
      session.elTab.classList.add('tab-minimized');
      session.elTab.style.opacity = '0.6';
    }
    this.updateActiveTerminalsCount();
    const modal = document.getElementById('modal-active-terminals');
    if (modal && modal.style.display === 'flex') {
      this.renderActiveTerminalsList();
    }
  }

  restoreSession(id) {
    const session = this.sessions.get(id);
    if (!session) return;
    session.isMinimized = false;
    if (session.elPane) {
      session.elPane.style.display = 'flex';
      session.elPane.style.zIndex = '10';
    }
    if (session.elTab) {
      session.elTab.classList.remove('tab-minimized');
      session.elTab.style.opacity = '1';
    }
    this.selectSession(id, true);
    if (session.fitAddon) {
      setTimeout(() => session.fitAddon.fit(), 50);
    }
    this.updateActiveTerminalsCount();
    const modal = document.getElementById('modal-active-terminals');
    if (modal && modal.style.display === 'flex') {
      this.renderActiveTerminalsList();
    }
  }

  toggleSessionVisibility(id) {
    const session = this.sessions.get(id);
    if (!session) return;
    if (session.isMinimized) {
      this.restoreSession(id);
    } else {
      this.minimizeSession(id);
    }
  }

  showAllSessions() {
    const list = this.getProjectSessions();
    list.forEach(s => {
      s.isMinimized = false;
      if (s.elPane) s.elPane.style.display = 'flex';
      if (s.elTab) {
        s.elTab.classList.remove('tab-minimized');
        s.elTab.style.opacity = '1';
      }
    });
    this.fitAll();
    this.updateActiveTerminalsCount();
  }

  hideAllSessions() {
    const list = this.getProjectSessions();
    list.forEach(s => {
      s.isMinimized = true;
      if (s.elPane) s.elPane.style.display = 'none';
      if (s.elTab) {
        s.elTab.classList.add('tab-minimized');
        s.elTab.style.opacity = '0.6';
      }
    });
    this.updateActiveTerminalsCount();
  }

  openActiveTerminalsModal() {
    const modal = document.getElementById('modal-active-terminals');
    if (!modal) return;
    modal.style.display = 'flex';
    
    const titleEl = document.getElementById('active-terminals-modal-title');
    const pathEl = document.getElementById('active-terminals-project-path');
    const projRoot = this.getActiveProjectRoot();
    const proj = (knownProjects || []).find(p => p.id === currentProjectId);
    const projName = proj ? proj.name : (projRoot ? projRoot.split('/').pop() : 'Projeto Atual');
    
    if (titleEl) {
      titleEl.innerHTML = `
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
          <polyline points="2 17 12 22 22 17"></polyline>
          <polyline points="2 12 12 17 22 12"></polyline>
        </svg>
        Terminais do Projeto (${escapeHtml(projName)})
      `;
    }
    if (pathEl) {
      pathEl.textContent = projRoot ? `Pasta: ${projRoot}` : '';
    }

    this.renderActiveTerminalsList();
  }

  closeActiveTerminalsModal() {
    const modal = document.getElementById('modal-active-terminals');
    if (modal) modal.style.display = 'none';
  }

  renderActiveTerminalsList() {
    const container = document.getElementById('active-terminals-list');
    if (!container) return;
    container.innerHTML = '';

    const list = this.getProjectSessions();
    if (list.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 28px 16px; color: var(--text-muted); font-size: 13px;">
          Nenhum terminal ativo neste projeto.<br>Clique em <strong>+ Novo Terminal</strong> para abrir uma sessão.
        </div>
      `;
      return;
    }

    list.forEach(session => {
      const item = document.createElement('div');
      item.className = 'active-terminal-card';
      item.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 8px; gap: 12px;';

      const isMin = !!session.isMinimized;
      const statusBadge = isMin
        ? `<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: var(--text-muted); font-size: 11px; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border-subtle);">Oculto</span>`
        : `<span class="badge" style="background: rgba(34, 197, 94, 0.15); color: #16a34a; font-size: 11px; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(34, 197, 94, 0.3);">Visível</span>`;

      const icon = this.getRoleIcon(session.role);
      const agentLabel = (session.agentType || 'bash').toUpperCase();

      item.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1;">
          <span style="font-size: 16px;">${icon}</span>
          <div style="min-width: 0;">
            <div style="font-weight: 600; font-size: 13px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
              ${escapeHtml(session.name)}
            </div>
            <div style="font-size: 11px; color: var(--text-muted); display: flex; gap: 8px; align-items: center;">
              <span>[${agentLabel}]</span>
              <span>PID: ${session.id.slice(0, 10)}</span>
            </div>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          ${statusBadge}
          <button class="btn btn-secondary btn-sm btn-toggle-vis" title="${isMin ? 'Exibir no canvas' : 'Ocultar do canvas'}" style="font-size: 11px; padding: 4px 10px;">
            ${isMin ? '👁️ Exibir' : '🙈 Ocultar'}
          </button>
          <button class="btn btn-secondary btn-sm btn-focus-term" title="Focar e trazer para frente" style="font-size: 11px; padding: 4px 10px;">
            Focar
          </button>
          <button class="btn btn-danger btn-sm btn-close-term" title="Encerrar terminal" style="font-size: 11px; padding: 4px 8px;">
            ×
          </button>
        </div>
      `;

      item.querySelector('.btn-toggle-vis').addEventListener('click', () => {
        this.toggleSessionVisibility(session.id);
      });
      item.querySelector('.btn-focus-term').addEventListener('click', () => {
        if (session.isMinimized) this.restoreSession(session.id);
        this.selectSession(session.id, true);
        this.closeActiveTerminalsModal();
      });
      item.querySelector('.btn-close-term').addEventListener('click', () => {
        this.closeSession(session.id);
        this.renderActiveTerminalsList();
      });

      container.appendChild(item);
    });
  }
}

export const terminalWorkspace = new TerminalWorkspaceManager();
if (typeof window !== 'undefined') {
  window.terminalWorkspace = terminalWorkspace;
}

export function initOrFitTerminal() {
  terminalWorkspace.init();
  terminalWorkspace.fitAll();
}

export function sendTerminalCommand(cmd) {
  terminalWorkspace.sendToActive(cmd);
}
