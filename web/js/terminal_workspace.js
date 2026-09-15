/**
 * Módulo de Terminal Workspace (TerminalWorkspaceManager)
 * Governa sessões PTY 1:N concorrentes, abas estilo Chrome, layouts de split e statusline.
 */

import { escapeHtml, formatRelativeCwd } from './ui_utils.js';
import { currentProjectId, activeSliceId, state, knownProjects, recordRecentProject, apiFetch } from './state.js';
import { renderWorktreeSidebar } from './sidebar.js';

export class TerminalWorkspaceManager {
  constructor() {
    this.sessions = new Map(); // id -> { id, name, role, sliceId, agentType, cwd, term, fitAddon, socket, isConnected, elPane, elTab, resizeObserver, contextKey, projectId, taskId }
    this.contextSessions = new Map(); // contextKey -> Set of sessionIds
    this.activeSessionId = null;
    this.activeContextKey = null;
    this.roleFilter = 'all'; // 'all' | 'orchestrator' | 'agent' | 'subagent'
    this.layout = localStorage.getItem('cockpit_terminal_layout') || 'dynamic';
    this.counter = 0;
    this.tabsBar = null;
    this.gridContainer = null;
    this.isInitialized = false;
  }

  getRoleIcon(role) {
    switch (role) {
      case 'orchestrator': return '👑';
      case 'agent': return '⚡';
      case 'subagent': return '🔬';
      default: return '💻';
    }
  }

  getRoleTitle(role) {
    switch (role) {
      case 'orchestrator': return 'Orquestrador Staff';
      case 'agent': return 'Agente Executor';
      case 'subagent': return 'Subagente Efêmero';
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
      default:
        return '⚡ bypass permissions on (shift+tab to cycle) - for agents';
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

  getAgentCommand(agentType) {
    switch (agentType) {
      case 'claude': return 'claude';
      case 'opencode': return 'opencode';
      case 'codex': return 'codex';
      case 'bash':
      default: return '';
    }
  }

  getCurrentModel() {
    if (typeof localWorkerStatus !== 'undefined' && localWorkerStatus && localWorkerStatus.model) {
      return localWorkerStatus.model;
    }
    if (typeof state !== 'undefined' && state && state.config && state.config.model) {
      return state.config.model;
    }
    return 'Fable 5 1M';
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

    // Seletor de layouts (Tabs, Split, Grid)
    const layoutPicker = document.getElementById('terminal-layout-picker');
    if (layoutPicker) {
      layoutPicker.querySelectorAll('.layout-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const l = btn.getAttribute('data-layout');
          if (l) this.setLayout(l);
        });
      });
    }

    // Botão novo terminal (+ Novo Terminal)
    const btnNewTerm = document.getElementById('btn-new-terminal');
    if (btnNewTerm) {
      btnNewTerm.addEventListener('click', () => {
        if (currentProjectId) {
          recordRecentProject(currentProjectId);
          renderWorktreeSidebar();
        }
        this.createSession();
      });
    }

    // Botão global executar opencode
    const btnRunOpenCode = document.getElementById('btn-run-opencode');
    if (btnRunOpenCode) {
      btnRunOpenCode.addEventListener('click', () => {
        this.sendToActive('opencode');
      });
    }

    // Botão global executar claude code
    const btnRunClaude = document.getElementById('btn-run-claude');
    if (btnRunClaude) {
      btnRunClaude.addEventListener('click', () => {
        this.sendToActive('claude');
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

    // Redimensionamento global da janela
    window.addEventListener('resize', () => {
      this.fitAll();
    });

    // Aplica layout configurado
    if (this.layout === 'dynamic') {
      this.applyDynamicSplit();
    } else {
      this.setLayout(this.layout, false);
    }

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
  }

  getActiveProjectRoot() {
    if (typeof knownProjects !== 'undefined' && Array.isArray(knownProjects)) {
      const activeProj = knownProjects.find(p => p.id === currentProjectId);
      if (activeProj && activeProj.project_root) return activeProj.project_root;
    }
    if (typeof state !== 'undefined' && state) {
      if (state.project_root) return state.project_root;
      if (state.config && state.config.project_root) return state.config.project_root;
    }
    return '';
  }

  getSliceCwd(sliceId, projectId = null) {
    const pid = projectId || currentProjectId;
    const proj = (typeof knownProjects !== 'undefined' && Array.isArray(knownProjects)) ? knownProjects.find(p => p.id === pid) : null;
    const root = proj && proj.project_root ? proj.project_root : this.getActiveProjectRoot();
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

    if (typeof Terminal === 'undefined') {
      if (this.gridContainer) {
        this.gridContainer.innerHTML = '<div style="color: #ef4444; padding: 20px; font-family: monospace;">Aguardando carregamento da biblioteca xterm.js...</div>';
      }
      return null;
    }

    if (!this.tabsBar || !this.gridContainer) {
      return null;
    }

    this.counter++;
    const id = options.id || `term-${Date.now()}-${this.counter}`;
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
    const agentType = options.agentType || (options.name && options.name.toLowerCase().includes('claude') ? 'claude' : (options.name && options.name.toLowerCase().includes('opencode') ? 'opencode' : 'bash'));
    const defaultName = role === 'orchestrator'
      ? (this.counter === 1 ? 'Orquestrador Staff' : `Orquestrador #${this.counter}`)
      : (role === 'agent'
        ? (sliceId ? `Agente (${sliceId})` : `Agente da Frota #${this.counter}`)
        : (taskId ? `Subagente (${taskId})` : `Subagente #${this.counter}`));
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

    // 1. Instância do Xterm
    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: 13,
      lineHeight: 1.25,
      theme: {
        background: '#09090b',
        foreground: '#f4f4f5',
        cursor: '#f4f4f5',
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
      }
    });

    let fitAddon = null;
    if (typeof FitAddon !== 'undefined' && FitAddon.FitAddon) {
      fitAddon = new FitAddon.FitAddon();
      term.loadAddon(fitAddon);
    }
    if (typeof WebLinksAddon !== 'undefined' && WebLinksAddon.WebLinksAddon) {
      term.loadAddon(new WebLinksAddon.WebLinksAddon());
    }

    // 2. Elementos DOM (Aba estilo Chrome e Painel com badge e permissões)
    const elTab = document.createElement('div');
    elTab.className = `term-tab orca-tab role-${role}`;
    elTab.id = `tab-${id}`;
    elTab.setAttribute('data-session-id', id);
    elTab.setAttribute('data-role', role);
    elTab.innerHTML = `
      <span class="term-tab-dot disconnected" title="Status de Conexão"></span>
      <span class="term-tab-icon">${iconHtml}</span>
      <span class="term-tab-title orca-tab-title" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
      ${roleBadgeHtml}
      <button class="term-tab-close orca-tab-close" title="Encerrar terminal">×</button>
    `;

    const elPane = document.createElement('div');
    elPane.className = 'terminal-pane orca-split-pane';
    elPane.id = `pane-${id}`;
    elPane.setAttribute('data-session-id', id);
    elPane.setAttribute('data-role', role);
    elPane.innerHTML = `
      <div class="orca-pane-header">
        <div class="orca-tab-strip">
          <div class="orca-tab active">
            <span class="orca-tab-icon">${iconHtml}</span>
            <span class="orca-tab-title">${escapeHtml(name)}</span>
          </div>
          <span class="orca-role-badge role-${role}" title="${roleTitle}">${roleIcon} ${roleTitle}</span>
          <div class="orca-agent-picker-wrap">
            <select class="orca-agent-select" title="Trocar tipo de ferramenta no painel">
              <option value="bash" ${agentType === 'bash' ? 'selected' : ''}>&gt; Bash</option>
              <option value="opencode" ${agentType === 'opencode' ? 'selected' : ''}>⚡ OpenCode</option>
              <option value="claude" ${agentType === 'claude' ? 'selected' : ''}>Claude Code</option>
              <option value="codex" ${agentType === 'codex' ? 'selected' : ''}>&gt;_ Codex</option>
            </select>
          </div>
          <div class="orca-pane-controls ml-auto">
            ${role === 'subagent' ? '<button class="orca-pane-btn orca-btn-terminate-subagent danger" title="Encerrar Subagente (Limpeza de Processo)">Encerrar Subagente</button>' : ''}
            <button class="orca-pane-btn orca-btn-split" title="Dividir terminal ([|] Split)">[|]</button>
            <button class="orca-pane-btn orca-btn-clear" title="Limpar buffer (⌧)">⌧</button>
            <button class="orca-pane-btn orca-btn-restart" title="Reconectar sessão PTY (⟳)">⟳</button>
            <button class="orca-pane-btn orca-btn-close danger" title="Fechar sessão (×)">×</button>
          </div>
        </div>
        <div class="orca-pane-subtitle" title="${model} · ${branchOrSlice} · ${cwd || 'Padrão'}">
          <span class="orca-pane-sub-item orca-sub-model">${model}</span>
          <span class="orca-sub-separator">·</span>
          <span class="orca-pane-sub-item orca-sub-branch">${branchOrSlice}</span>
          <span class="orca-sub-separator">·</span>
          <span class="orca-pane-sub-item orca-sub-cwd">${relCwd}</span>
        </div>
      </div>
      <div class="pane-body">
        <div class="xterm-mount" style="width: 100%; height: 100%; position: relative;"></div>
      </div>
      <div class="orca-terminal-statusline">
        <div class="orca-statusline-item orca-statusline-model orca-status-model" title="Modelo ativo do worker">
          <span class="orca-status-dot-active">●</span>
          <span class="orca-status-text orca-status-model-text">${model}</span>
        </div>
        <div class="orca-statusline-item orca-statusline-branch orca-status-branch" title="Fatia ou branch ativa">
          <span class="orca-status-icon">🌱</span>
          <span class="orca-status-text orca-status-branch-text">${branchOrSlice}</span>
        </div>
        <div class="orca-statusline-item orca-statusline-perms orca-status-perms" title="Permissões do Papel">
          <span class="orca-status-text">${rolePerms}</span>
        </div>
        <div class="orca-statusline-item orca-statusline-mcp orca-status-mcp" title="Telemetria MCP Live">
          <span class="orca-status-mcp-indicator live">●</span>
          <span class="orca-status-text">MCP Live</span>
        </div>
      </div>
    `;

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

    const mountEl = elPane.querySelector('.xterm-mount');
    term.open(mountEl);

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
      elPane,
      elTab,
      resizeObserver: null
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

    // 4. WebSocket Conexão
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

    // 6. Eventos de Interação DOM
    elTab.addEventListener('click', (e) => {
      if (e.target.classList.contains('term-tab-close') || e.target.classList.contains('orca-tab-close')) {
        this.closeSession(id);
      } else {
        this.selectSession(id);
      }
    });

    elPane.addEventListener('mousedown', () => {
      this.selectSession(id, false);
    });

    // Controles do cabeçalho do painel Orca
    const btnSplit = elPane.querySelector('.orca-btn-split');
    if (btnSplit) {
      btnSplit.addEventListener('click', (e) => {
        e.stopPropagation();
        this.splitSession(id);
      });
    }

    const btnClear = elPane.querySelector('.orca-btn-clear');
    if (btnClear) {
      btnClear.addEventListener('click', (e) => {
        e.stopPropagation();
        term.clear();
        term.focus();
      });
    }

    const btnRestart = elPane.querySelector('.orca-btn-restart');
    if (btnRestart) {
      btnRestart.addEventListener('click', (e) => {
        e.stopPropagation();
        term.clear();
        this.connectSessionSocket(session);
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
      ro.observe(elPane);
      session.resizeObserver = ro;
    }

    // Seleciona a sessão criada
    this.selectSession(id);
    if (this.layout === 'dynamic') {
      this.applyDynamicSplit();
    } else {
      this.fitAll();
    }

    return session;
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
      setTimeout(() => {
        if (session.fitAddon && session.term) {
          try {
            session.fitAddon.fit();
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({
                type: 'resize',
                cols: session.term.cols,
                rows: session.term.rows
              }));
            }
          } catch (e) {}
        }
      }, 50);
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
    const model = this.getCurrentModel();
    const branchOrSlice = this.getCurrentSliceOrBranch();

    this.sessions.forEach(session => {
      const relCwd = this.formatRelativeCwd(session.cwd);

      const subModel = session.elPane.querySelector('.orca-sub-model');
      if (subModel) subModel.textContent = model;
      const subBranch = session.elPane.querySelector('.orca-sub-branch');
      if (subBranch) subBranch.textContent = branchOrSlice;
      const subCwd = session.elPane.querySelector('.orca-sub-cwd');
      if (subCwd) subCwd.textContent = relCwd;

      const statusModel = session.elPane.querySelector('.orca-status-model-text');
      if (statusModel) statusModel.textContent = model;
      const statusBranch = session.elPane.querySelector('.orca-status-branch-text');
      if (statusBranch) statusBranch.textContent = branchOrSlice;
    });
  }

  updateHeaderBadge() {
    const badge = document.getElementById('terminal-session-badge');
    if (!badge) return;

    const total = this.getActiveContextSessions().length;
    const active = this.activeSessionId ? this.sessions.get(this.activeSessionId) : null;
    const activeName = active ? active.name : 'Nenhum';
    const status = active && active.isConnected ? 'Conectado' : 'Pronto';
    const layoutName = this.layout ? this.layout.toUpperCase() : 'DYNAMIC';

    badge.textContent = `${total} PTYs | ${activeName} (${status}) | Layout: ${layoutName}`;
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
    if (!this.tabsBar) this.tabsBar = document.getElementById('terminal-tabs-bar');
    if (!this.tabsBar) return;

    // 1. Container de filtros rápidos por papel
    let filtersContainer = document.getElementById('terminal-role-filters');
    if (!filtersContainer) {
      filtersContainer = document.createElement('div');
      filtersContainer.id = 'terminal-role-filters';
      filtersContainer.className = 'terminal-role-filters';
      filtersContainer.innerHTML = `
        <button class="term-filter-chip active" data-filter="all">Todos</button>
        <button class="term-filter-chip" data-filter="orchestrator">👑 Orquestrador</button>
        <button class="term-filter-chip" data-filter="agent">⚡ Agentes</button>
        <button class="term-filter-chip" data-filter="subagent">🔬 Subagentes</button>
      `;
      filtersContainer.querySelectorAll('.term-filter-chip').forEach(btn => {
        btn.addEventListener('click', () => {
          filtersContainer.querySelectorAll('.term-filter-chip').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          this.setRoleFilter(btn.getAttribute('data-filter'));
        });
      });
      if (this.tabsBar.parentNode) {
        this.tabsBar.parentNode.insertBefore(filtersContainer, this.tabsBar);
      }
    }

    // 2. Popover / Dropdown de adição de terminais especializados
    let btnAddTab = document.getElementById('btn-tab-add-wrap');
    if (!btnAddTab) {
      const oldBtn = document.getElementById('btn-tab-add');
      if (oldBtn && oldBtn.parentNode) oldBtn.parentNode.removeChild(oldBtn);

      btnAddTab = document.createElement('div');
      btnAddTab.id = 'btn-tab-add-wrap';
      btnAddTab.className = 'term-tab-add-wrap';
      btnAddTab.innerHTML = `
        <button id="btn-tab-add" class="term-tab-add orca-tab" title="Criar terminal especializado">
          + Novo <span class="tab-add-arrow">▾</span>
        </button>
        <div class="terminal-add-dropdown" id="terminal-add-dropdown" style="display: none;">
          <div class="terminal-add-item" data-role="orchestrator">
            <span class="role-icon">👑</span>
            <div class="role-text">
              <span class="role-name">Orquestrador Staff</span>
              <span class="role-desc">Comando do blueprint</span>
            </div>
          </div>
          <div class="terminal-add-item" data-role="agent">
            <span class="role-icon">⚡</span>
            <div class="role-text">
              <span class="role-name">Agente da Fatia</span>
              <span class="role-desc">Worktree isolada</span>
            </div>
          </div>
          <div class="terminal-add-item" data-role="subagent">
            <span class="role-icon">🔬</span>
            <div class="role-text">
              <span class="role-name">Subagente Efêmero</span>
              <span class="role-desc">Pesquisa, testes e refactor</span>
            </div>
          </div>
        </div>
      `;
      const btn = btnAddTab.querySelector('#btn-tab-add');
      const dropdown = btnAddTab.querySelector('#terminal-add-dropdown');
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdown.style.display = (dropdown.style.display === 'none' || !dropdown.style.display) ? 'block' : 'none';
      });
      dropdown.querySelectorAll('.terminal-add-item').forEach(item => {
        item.addEventListener('click', (e) => {
          e.stopPropagation();
          const targetRole = item.getAttribute('data-role');
          dropdown.style.display = 'none';
          if (currentProjectId) {
            recordRecentProject(currentProjectId);
            renderWorktreeSidebar();
          }
          this.createSession({ role: targetRole });
        });
      });
      document.addEventListener('click', () => {
        dropdown.style.display = 'none';
      });
      this.tabsBar.appendChild(btnAddTab);
    }
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
}

export const terminalWorkspace = new TerminalWorkspaceManager();

export function initOrFitTerminal() {
  terminalWorkspace.init();
  terminalWorkspace.fitAll();
}

export function sendTerminalCommand(cmd) {
  terminalWorkspace.sendToActive(cmd);
}
