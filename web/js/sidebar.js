/**
 * Módulo de Navegação e Barra Lateral (Sidebar)
 * Governa a navegação de abas, renderização de projetos fixados e recentes, e modais.
 */

import { escapeHtml } from './ui_utils.js';
import {
  state,
  currentProjectId,
  knownProjects,
  getPinnedProjectIds,
  savePinnedProjectIds,
  getRecentProjectIds,
  switchProject,
  setActiveSliceId,
  getProjectDotClass,
  getProjectDotTitle,
  subscribe
} from './state.js';

let isProjectsExpanded = false;

// Inicialização da Sidebar Retrátil (Hambúrguer)
export function initSidebar() {
  const sidebar = document.getElementById('app-sidebar');
  const toggleBtn = document.getElementById('btn-sidebar-toggle');
  if (!sidebar || !toggleBtn) return;

  const isCollapsed = localStorage.getItem('cockpit_sidebar_collapsed') === 'true';
  if (isCollapsed) {
    sidebar.classList.add('collapsed');
  }

  toggleBtn.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    localStorage.setItem('cockpit_sidebar_collapsed', sidebar.classList.contains('collapsed'));
  });

  // Vincula tabs da navegação principal
  document.querySelectorAll('.nav-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const viewId = btn.getAttribute('data-view');
      switchTab(viewId);
    });
  });

  initOrcaNavigationAndModals();

  // Reatividade a mudanças no State Store
  subscribe('projects', () => renderWorktreeSidebar());
  subscribe('project', () => renderWorktreeSidebar());

  // Render inicial imediato
  renderWorktreeSidebar();
}

// Alternador de Abas Principais (Views)
export function switchTab(viewId) {
  document.querySelectorAll('.nav-tab').forEach(t => {
    t.classList.toggle('active', t.getAttribute('data-view') === viewId);
  });
  document.querySelectorAll('.tab-view').forEach(v => {
    v.classList.toggle('active', v.id === viewId);
  });

  if (viewId === 'view-graph') {
    if (typeof window.initOrRefreshGraph === 'function') window.initOrRefreshGraph();
  } else if (viewId === 'view-handoff') {
    if (typeof window.loadHandoff === 'function') window.loadHandoff();
  } else if (viewId === 'view-worker') {
    if (typeof window.loadLocalWorker === 'function') window.loadLocalWorker();
  } else if (viewId === 'view-terminal') {
    if (typeof window.initOrFitTerminal === 'function') window.initOrFitTerminal();
  } else if (viewId === 'view-settings') {
    if (typeof window.loadSettings === 'function') window.loadSettings();
    if (typeof window.loadOmniRouteSettings === 'function') window.loadOmniRouteSettings();
  }
}

window.switchTab = function(viewId) {
  return switchTab(viewId);
};

// Alterna fixação de projeto
export function togglePinProject(projectId, event) {
  if (event) event.stopPropagation();
  if (!projectId) return;

  let pinnedIds = getPinnedProjectIds();
  if (pinnedIds.includes(projectId)) {
    pinnedIds = pinnedIds.filter(id => id !== projectId);
  } else {
    pinnedIds.push(projectId);
  }
  savePinnedProjectIds(pinnedIds);
  renderWorktreeSidebar();
}

// Alterna exibição expandida da lista recente de projetos
export function toggleShowMoreProjects(event) {
  if (event) event.stopPropagation();
  isProjectsExpanded = !isProjectsExpanded;
  renderWorktreeSidebar();
}

// Renderiza barra lateral de workspaces (Pinned e Recentes)
export function renderWorktreeSidebar() {
  const pinnedList = document.getElementById('worktree-pinned-list');
  const cardsList = document.getElementById('worktree-cards-list');
  const pinnedCountBadge = document.getElementById('pinned-count');
  const progressCountBadge = document.getElementById('worktree-progress-count');
  const btnShowMore = document.getElementById('btn-show-more-projects');
  const btnShowMoreText = document.getElementById('btn-show-more-text');
  const btnShowMoreIcon = document.getElementById('btn-show-more-icon');

  if (!cardsList) return;

  const pinnedIds = getPinnedProjectIds();
  const recentIds = getRecentProjectIds();

  // 1. Renderiza lista Pinned
  if (pinnedList) {
    pinnedList.innerHTML = '';
    const pinnedProjects = (knownProjects || []).filter(p => pinnedIds.includes(p.id));

    if (pinnedCountBadge) {
      pinnedCountBadge.textContent = String(pinnedProjects.length);
    }

    pinnedProjects.forEach(proj => {
      const card = document.createElement('div');
      const isCardActive = (proj.id === currentProjectId);
      card.className = `worktree-card ${isCardActive ? 'active' : ''}`;
      card.setAttribute('data-project-id', proj.id);
      card.setAttribute('tabindex', '0');

      const dotClass = getProjectDotClass(proj);
      const dotTitle = getProjectDotTitle(dotClass);
      const repoTag = (proj.id || 'cockpit').toLowerCase().slice(0, 10);
      const slicesInfo = proj.total_slices > 0 ? `${proj.approved_slices}/${proj.total_slices}` : 'pinned';

      card.innerHTML = `
        <div class="worktree-header">
          <span class="worktree-title" title="${escapeHtml(proj.name)}">${escapeHtml(proj.name)}</span>
          <div class="worktree-header-actions">
            <button class="btn-pin-action pinned" title="Desafixar da lista Pinned" data-tooltip="Desafixar" onclick="togglePinProject('${escapeHtml(proj.id)}', event)" aria-label="Desafixar">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor">
                <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/>
              </svg>
            </button>
            <span class="agent-state-dot ${dotClass}" title="${escapeHtml(dotTitle)}"></span>
          </div>
        </div>
        <div class="worktree-meta-row">
          <span class="worktree-repo-tag" title="${escapeHtml(repoTag)}">${escapeHtml(repoTag)}</span>
          <span class="worktree-branch" title="main">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="6" y1="3" x2="6" y2="15"></line>
              <circle cx="18" cy="6" r="3"></circle>
              <circle cx="6" cy="18" r="3"></circle>
              <path d="M18 9a9 9 0 0 1-9 9"></path>
            </svg>
            main
          </span>
          <span class="worktree-time">${slicesInfo}</span>
        </div>
      `;

      card.addEventListener('click', () => {
        document.querySelectorAll('.worktree-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        setActiveSliceId(null);
        switchProject(proj.id);
      });

      pinnedList.appendChild(card);
    });
  }

  // 2. Renderiza lista Projects / Recentes (estritamente projetos, sem fatias)
  cardsList.innerHTML = '';
  let progressCount = 0;

  // Projetos não fixados ordenados por histórico recente
  const unpinnedProjects = (knownProjects || []).filter(p => !pinnedIds.includes(p.id));
  unpinnedProjects.sort((a, b) => {
    const idxA = recentIds.indexOf(a.id);
    const idxB = recentIds.indexOf(b.id);
    if (idxA !== -1 && idxB !== -1) return idxA - idxB;
    if (idxA !== -1) return -1;
    if (idxB !== -1) return 1;
    return a.name.localeCompare(b.name);
  });

  const projectsToDisplay = isProjectsExpanded ? unpinnedProjects : unpinnedProjects.slice(0, 3);

  projectsToDisplay.forEach(proj => {
    progressCount++;
    const card = document.createElement('div');
    const isCardActive = (proj.id === currentProjectId);
    card.className = `worktree-card ${isCardActive ? 'active' : ''}`;
    card.setAttribute('data-project-id', proj.id);
    card.setAttribute('tabindex', '0');

    const dotClass = getProjectDotClass(proj);
    const dotTitle = getProjectDotTitle(dotClass);
    const repoTag = (proj.id || 'proj').toLowerCase().slice(0, 10);
    const timeText = proj.total_slices > 0 ? `${proj.approved_slices}/${proj.total_slices}` : 'idle';

    card.innerHTML = `
      <div class="worktree-header">
        <span class="worktree-title" title="${escapeHtml(proj.name)}">${escapeHtml(proj.name)}</span>
        <div class="worktree-header-actions">
          <button class="btn-pin-action" title="Fixar na lista Pinned" data-tooltip="Fixar" onclick="togglePinProject('${escapeHtml(proj.id)}', event)" aria-label="Fixar">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="17" x2="12" y2="22"></line>
              <path d="M5 17h14l-2-7V4h1V2H6v2h1v6l-2 7z"></path>
            </svg>
          </button>
          <span class="agent-state-dot ${dotClass}" title="${escapeHtml(dotTitle)}"></span>
        </div>
      </div>
      <div class="worktree-meta-row">
        <span class="worktree-repo-tag" title="${escapeHtml(repoTag)}">${escapeHtml(repoTag)}</span>
        <span class="worktree-branch" title="main">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="6" y1="3" x2="6" y2="15"></line>
            <circle cx="18" cy="6" r="3"></circle>
            <circle cx="6" cy="18" r="3"></circle>
            <path d="M18 9a9 9 0 0 1-9 9"></path>
          </svg>
          main
        </span>
        <span class="worktree-time">${timeText}</span>
      </div>
    `;

    card.addEventListener('click', () => {
      document.querySelectorAll('.worktree-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      setActiveSliceId(null);
      switchProject(proj.id);
    });

    cardsList.appendChild(card);
  });

  if (progressCountBadge) {
    progressCountBadge.textContent = String(progressCount);
  }

  // 3. Controle do botão Exibir Mais
  if (btnShowMore) {
    if (unpinnedProjects.length > 3) {
      btnShowMore.style.display = 'flex';
      if (isProjectsExpanded) {
        if (btnShowMoreText) btnShowMoreText.textContent = 'Exibir Menos';
        if (btnShowMoreIcon) btnShowMoreIcon.innerHTML = '<polyline points="18 15 12 9 6 15"></polyline>';
      } else {
        const remaining = unpinnedProjects.length - 3;
        if (btnShowMoreText) btnShowMoreText.textContent = `Exibir Mais (+${remaining})`;
        if (btnShowMoreIcon) btnShowMoreIcon.innerHTML = '<polyline points="6 9 12 15 18 9"></polyline>';
      }
    } else {
      btnShowMore.style.display = 'none';
    }
  }
}

// Inicialização de Navegação, Modais e Atalhos
export function initOrcaNavigationAndModals() {
  // 1. Seções Colapsáveis da Sidebar (Pinned, In Progress, Views)
  document.querySelectorAll('.worktree-section-header').forEach(header => {
    header.addEventListener('click', (e) => {
      e.stopPropagation();
      const section = header.closest('.worktree-section');
      if (section) {
        section.classList.toggle('collapsed');
      }
    });
  });

  // 2. Botão (+) Nova Worktree / Sessão (#btn-sidebar-new-worktree)
  const btnNewWorktree = document.getElementById('btn-sidebar-new-worktree');
  if (btnNewWorktree) {
    btnNewWorktree.addEventListener('click', () => {
      const branch = prompt('Nome da nova Worktree / Branch (ex: feature/nova-fatia):');
      if (branch && branch.trim()) {
        const cleanBranch = branch.trim();
        if (typeof window.sendTerminalCommand === 'function') {
          window.sendTerminalCommand(`git checkout -b "${cleanBranch}"\n`);
          switchTab('view-terminal');
        }
      }
    });
  }

  // 2.5. Botão Exibir Mais / Menos Projetos (#btn-show-more-projects)
  const btnShowMoreProjects = document.getElementById('btn-show-more-projects');
  if (btnShowMoreProjects) {
    btnShowMoreProjects.addEventListener('click', toggleShowMoreProjects);
  }

  // 3. Quick-Nav Buttons
  const navQuickSearch = document.getElementById('nav-quick-search');
  if (navQuickSearch) {
    navQuickSearch.addEventListener('click', openQuickSearch);
  }

  const navFooterSettings = document.getElementById('nav-footer-settings');
  if (navFooterSettings) {
    navFooterSettings.addEventListener('click', () => {
      switchTab('view-settings');
    });
  }

  // 4. Modal de Busca Rápida (Command Palette)
  const quickSearchModal = document.getElementById('orca-quick-search-modal');
  const quickSearchInput = document.getElementById('quick-search-input');

  if (quickSearchModal) {
    quickSearchModal.addEventListener('click', (e) => {
      if (e.target === quickSearchModal) closeQuickSearch();
    });
  }
  if (quickSearchInput) {
    quickSearchInput.addEventListener('input', (e) => {
      renderQuickSearchResults(e.target.value);
    });
  }

  // 5. Atalho Global de Teclado (Ctrl+K / Cmd+K / Esc)
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      openQuickSearch();
    } else if (e.key === 'Escape') {
      closeQuickSearch();
    }
  });
}

export function openQuickSearch() {
  const modal = document.getElementById('orca-quick-search-modal');
  const input = document.getElementById('quick-search-input');
  if (!modal || !input) return;
  modal.style.display = 'flex';
  input.value = '';
  renderQuickSearchResults('');
  setTimeout(() => input.focus(), 50);
}

export function closeQuickSearch() {
  const modal = document.getElementById('orca-quick-search-modal');
  if (modal) modal.style.display = 'none';
}

export function renderQuickSearchResults(query) {
  const resultsContainer = document.getElementById('quick-search-results');
  if (!resultsContainer) return;
  resultsContainer.innerHTML = '';

  const items = [];
  // Views principais
  items.push({ label: 'Visão Geral do Cockpit', badge: 'VIEW', action: () => switchTab('view-overview') });
  items.push({ label: 'Fluxo & Kanban das Fatias', badge: 'VIEW', action: () => switchTab('view-flow') });
  items.push({ label: 'Codebase Knowledge Graph', badge: 'VIEW', action: () => switchTab('view-graph') });
  items.push({ label: 'Gauntlet Verdicts Log', badge: 'VIEW', action: () => switchTab('view-gauntlet') });
  items.push({ label: 'Handoff & Master Blueprint', badge: 'VIEW', action: () => switchTab('view-handoff') });
  items.push({ label: 'Terminal / OpenCode Runner', badge: 'TOOL', action: () => switchTab('view-terminal') });
  items.push({ label: 'Local Worker & Ollama Manager', badge: 'AI', action: () => switchTab('view-worker') });
  items.push({ label: 'Configurações do Cockpit', badge: 'SETTINGS', action: () => switchTab('view-settings') });

  // Fatias verticais
  (state.nodes || []).forEach(n => {
    items.push({
      label: `${n.id.toUpperCase()}: ${n.title}`,
      badge: `SLICE (${n.kanban_status})`,
      action: () => {
        setActiveSliceId(n.id);
        switchTab('view-flow');
        if (typeof window.openDrawer === 'function') window.openDrawer(n.id);
      }
    });
  });

  // Projetos conhecidos
  (knownProjects || []).forEach(p => {
    items.push({
      label: `Workspace: ${p.name}`,
      badge: 'PROJECT',
      action: () => switchProject(p.id)
    });
  });

  const q = (query || '').toLowerCase().trim();
  const filtered = q
    ? items.filter(it => it.label.toLowerCase().includes(q) || it.badge.toLowerCase().includes(q))
    : items;

  if (filtered.length === 0) {
    resultsContainer.innerHTML = '<div style="padding: 12px; color: var(--muted-foreground); text-align: center; font-size: 12px;">Nenhum resultado encontrado.</div>';
    return;
  }

  filtered.forEach((it, idx) => {
    const el = document.createElement('div');
    el.className = `orca-command-item ${idx === 0 ? 'selected' : ''}`;
    el.innerHTML = `
      <div class="orca-command-item-left">
        <span>${escapeHtml(it.label)}</span>
      </div>
      <span class="orca-command-item-badge">${escapeHtml(it.badge)}</span>
    `;
    el.addEventListener('click', () => {
      closeQuickSearch();
      it.action();
    });
    resultsContainer.appendChild(el);
  });
}
