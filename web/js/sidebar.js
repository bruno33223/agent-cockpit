/**
 * Módulo de Navegação e Barra Lateral (Sidebar)
 * Governa a navegação de abas, renderização de projetos fixados e recentes, e modais.
 */

import { escapeHtml } from './ui_utils.js';
import {
  apiFetch,
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
  const topbarToggleBtn = document.getElementById('btn-topbar-sidebar-toggle');
  const reopenBtn = document.getElementById('btn-reopen-left-sidebar');
  if (!sidebar) return;

  function setSidebarCollapsed(collapsed) {
    sidebar.classList.toggle('collapsed', collapsed);
    sidebar.classList.toggle('sidebar-pinned-hidden', collapsed);
    document.body.classList.toggle('sidebar-pinned-hidden', collapsed);
    localStorage.setItem('cockpit_sidebar_collapsed', collapsed ? 'true' : 'false');
  }

  function toggleSidebar() {
    const isCurrentlyHidden = document.body.classList.contains('sidebar-pinned-hidden');
    setSidebarCollapsed(!isCurrentlyHidden);
  }

  // Padrão: SEMPRE ABERTO por padrão (redefine legado uma única vez para garantir experiência do usuário)
  if (localStorage.getItem('cockpit_sidebar_reset_v3') !== 'done') {
    localStorage.removeItem('cockpit_sidebar_collapsed');
    localStorage.setItem('cockpit_sidebar_reset_v3', 'done');
  }
  const isCollapsed = localStorage.getItem('cockpit_sidebar_collapsed') === 'true';
  setSidebarCollapsed(isCollapsed);

  if (toggleBtn) {
    toggleBtn.addEventListener('click', toggleSidebar);
  }
  if (topbarToggleBtn) {
    topbarToggleBtn.addEventListener('click', toggleSidebar);
  }
  if (reopenBtn) {
    reopenBtn.addEventListener('click', () => setSidebarCollapsed(false));
  }

  // Atalho global de teclado Ctrl+B / Cmd+B para alternar menu lateral
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      toggleSidebar();
    }
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
    openSettingsModal();
    return;
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

  // Deduplicação estrita de projetos por pasta física (project_root)
  const dedupedProjects = [];
  const seenFolders = new Set();
  (knownProjects || []).forEach(p => {
    const folderKey = (p.project_root ? p.project_root.trim().toLowerCase() : (p.id || '').toLowerCase());
    if (folderKey && !seenFolders.has(folderKey)) {
      seenFolders.add(folderKey);
      dedupedProjects.push(p);
    }
  });

  // 1. Renderiza lista Pinned
  if (pinnedList) {
    pinnedList.innerHTML = '';
    const pinnedProjects = dedupedProjects.filter(p => pinnedIds.includes(p.id));

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
      const repoTag = (proj.name || proj.id || 'cockpit').toLowerCase().slice(0, 14);
      const slicesInfo = proj.total_slices > 0 ? `${proj.approved_slices}/${proj.total_slices}` : 'pinned';
      const termCount = (typeof window !== 'undefined' && window.terminalWorkspace) ? window.terminalWorkspace.getProjectSessions(proj.id).length : 0;
      const termBadge = termCount > 0 ? `<span class="worktree-term-badge" title="${termCount} terminal(is) ativo(s)" style="display: inline-flex; align-items: center; gap: 3px; font-size: 10px; color: var(--text-secondary); margin-left: 6px;"><svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg> ${termCount}</span>` : '';

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
          <span class="worktree-time">${slicesInfo}${termBadge}</span>
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
  const unpinnedProjects = dedupedProjects.filter(p => !pinnedIds.includes(p.id));
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
    const repoTag = (proj.name || proj.id || 'proj').toLowerCase().slice(0, 14);
    const timeText = proj.total_slices > 0 ? `${proj.approved_slices}/${proj.total_slices}` : 'idle';
    const termCount = (typeof window !== 'undefined' && window.terminalWorkspace) ? window.terminalWorkspace.getProjectSessions(proj.id).length : 0;
    const termBadge = termCount > 0 ? `<span class="worktree-term-badge" title="${termCount} terminal(is) ativo(s)" style="display: inline-flex; align-items: center; gap: 3px; font-size: 10px; color: var(--text-secondary); margin-left: 6px;"><svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg> ${termCount}</span>` : '';

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
      openSettingsModal();
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

  // 5. Atalho Global de Teclado (Ctrl+K / Ctrl+, / Esc)
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      openQuickSearch();
    } else if ((e.ctrlKey || e.metaKey) && e.key === ',') {
      e.preventDefault();
      openSettingsModal();
    } else if (e.key === 'Escape') {
      closeQuickSearch();
      closeAboutModal();
      closeSettingsModal();
    }
  });

  // 6. Modal Sobre o ZEUS AGENT (Issue #10)
  const zeusBrand = document.getElementById('zeus-brand');
  if (zeusBrand) {
    zeusBrand.style.cursor = 'pointer';
    zeusBrand.addEventListener('click', openAboutModal);
  }

  const btnCloseAbout = document.getElementById('btn-close-about-zeus');
  if (btnCloseAbout) {
    btnCloseAbout.addEventListener('click', closeAboutModal);
  }

  const btnAboutOk = document.getElementById('btn-about-zeus-ok');
  if (btnAboutOk) {
    btnAboutOk.addEventListener('click', closeAboutModal);
  }

  const modalAbout = document.getElementById('modal-about-zeus');
  if (modalAbout) {
    modalAbout.addEventListener('click', (e) => {
      if (e.target === modalAbout) closeAboutModal();
    });
  }

  // 7. Modal de Configurações Estilo Antigravity
  initAntigravitySettingsModal();
}

export function openAboutModal() {
  const modal = document.getElementById('modal-about-zeus');
  if (modal) modal.style.display = 'flex';
}

export function closeAboutModal() {
  const modal = document.getElementById('modal-about-zeus');
  if (modal) modal.style.display = 'none';
}

export function openSettingsModal() {
  const modal = document.getElementById('modal-settings-antigravity');
  if (modal) {
    modal.style.display = 'flex';
    renderSettingsProjects();
    syncSettingsValues();
    if (typeof window.loadOmniRouteSettings === 'function') {
      window.loadOmniRouteSettings();
    }
  }
}

export function closeSettingsModal() {
  const modal = document.getElementById('modal-settings-antigravity');
  if (modal) modal.style.display = 'none';
}

export function switchAgSettingsTab(tabName) {
  document.querySelectorAll('.ag-nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-ag-tab') === tabName);
  });
  document.querySelectorAll('.ag-tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `ag-panel-${tabName}`);
  });
  if (tabName === 'models' && typeof window.loadOmniRouteSettings === 'function') {
    window.loadOmniRouteSettings();
  }
}

export function renderSettingsProjects() {
  const container = document.getElementById('ag-projects-nav-list');
  if (!container) return;
  container.innerHTML = '';
  (knownProjects || []).forEach(p => {
    const item = document.createElement('button');
    const isCurrent = (p.id === currentProjectId);
    item.className = `ag-project-nav-item ${isCurrent ? 'active' : ''}`;
    item.innerHTML = `
      <span class="ag-project-dot ${isCurrent ? 'active' : ''}"></span>
      <span class="ag-project-name" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</span>
    `;
    item.addEventListener('click', () => {
      switchProject(p.id);
      closeSettingsModal();
    });
    container.appendChild(item);
  });
}

export function syncSettingsValues() {
  const urlInput = document.getElementById('ag-omniroute-url');
  const keyInput = document.getElementById('ag-omniroute-key');
  const modelInput = document.getElementById('ag-omniroute-model');
  const origUrl = document.getElementById('omniroute-url-input');
  const origKey = document.getElementById('omniroute-key-input');
  const origModel = document.getElementById('omniroute-model-input');

  if (urlInput && origUrl) urlInput.value = origUrl.value || 'http://localhost:20128/v1';
  if (keyInput && origKey) keyInput.value = origKey.value || 'omniroute-local';
  if (modelInput && origModel) modelInput.value = origModel.value || 'auto';

  const workerToggle = document.getElementById('ag-toggle-local-worker');
  const origWorkerToggle = document.getElementById('toggle-local-ai-worker');
  if (workerToggle && origWorkerToggle) {
    workerToggle.checked = origWorkerToggle.checked;
  }

  const agSelectModel = document.getElementById('ag-select-local-model');
  const origSelectModel = document.getElementById('lw-sidebar-select') || document.getElementById('lw-topbar-select');
  if (agSelectModel && origSelectModel) {
    agSelectModel.innerHTML = origSelectModel.innerHTML;
    agSelectModel.value = origSelectModel.value;
  }
}

export function initAntigravitySettingsModal() {
  document.querySelectorAll('.ag-nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const tabName = btn.getAttribute('data-ag-tab');
      if (tabName) switchAgSettingsTab(tabName);
    });
  });

  const btnClose = document.getElementById('btn-close-ag-settings');
  if (btnClose) btnClose.addEventListener('click', closeSettingsModal);

  const modal = document.getElementById('modal-settings-antigravity');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeSettingsModal();
    });
  }

  const btnShortcuts = document.getElementById('btn-ag-shortcuts');
  if (btnShortcuts) {
    btnShortcuts.addEventListener('click', () => switchAgSettingsTab('shortcuts'));
  }


  const btnTestOmni = document.getElementById('btn-ag-test-omniroute');
  if (btnTestOmni) {
    btnTestOmni.addEventListener('click', async () => {
      const urlInput = document.getElementById('ag-omniroute-url');
      const feedback = document.getElementById('ag-omniroute-feedback');
      const targetUrl = urlInput ? urlInput.value.trim() : 'http://localhost:20128/v1';

      btnTestOmni.disabled = true;
      const originalText = btnTestOmni.textContent;
      btnTestOmni.textContent = 'Testando...';

      if (feedback) {
        feedback.style.display = 'block';
        feedback.className = 'ag-feedback-msg testing';
        feedback.style.background = 'rgba(59, 130, 246, 0.12)';
        feedback.style.borderColor = 'rgba(59, 130, 246, 0.3)';
        feedback.style.color = '#60a5fa';
        feedback.textContent = 'Testando conexão com OmniRoute...';
      }

      const startTime = performance.now();
      try {
        const query = targetUrl ? `?base_url=${encodeURIComponent(targetUrl)}` : '';
        const res = await apiFetch(`/api/omniroute/status${query}`);
        const data = await res.json();
        const latency = Math.round(performance.now() - startTime);

        if (feedback) {
          feedback.style.display = 'block';
          if (data.online) {
            const modelsCount = (data.models && Array.isArray(data.models)) ? data.models.length : 0;
            const modelsPreview = modelsCount > 0 ? ` [${data.models.slice(0, 3).join(', ')}${modelsCount > 3 ? ` +${modelsCount - 3}` : ''}]` : '';
            feedback.className = 'ag-feedback-msg success';
            feedback.style.background = 'rgba(16, 185, 129, 0.12)';
            feedback.style.borderColor = 'rgba(16, 185, 129, 0.3)';
            feedback.style.color = '#34d399';
            feedback.textContent = `✓ OmniRoute Conectado (${latency}ms) — ${modelsCount} modelo(s) detectado(s)${modelsPreview}`;
          } else {
            feedback.className = 'ag-feedback-msg error';
            feedback.style.background = 'rgba(239, 68, 68, 0.12)';
            feedback.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            feedback.style.color = '#f87171';
            feedback.textContent = `✗ Falha na conexão: ${data.message || 'Serviço OmniRoute inacessível no endpoint especificado.'}`;
          }
        }
      } catch (err) {
        if (feedback) {
          feedback.style.display = 'block';
          feedback.className = 'ag-feedback-msg error';
          feedback.style.background = 'rgba(239, 68, 68, 0.12)';
          feedback.style.borderColor = 'rgba(239, 68, 68, 0.3)';
          feedback.style.color = '#f87171';
          feedback.textContent = `✗ Erro de rede/requisição: ${err.message || 'Não foi possível contatar o servidor'}`;
        }
      } finally {
        btnTestOmni.disabled = false;
        btnTestOmni.textContent = originalText;
      }
    });
  }

  // Worker toggle no modal
  const workerToggle = document.getElementById('ag-toggle-local-worker');
  if (workerToggle) {
    workerToggle.addEventListener('change', () => {
      const origWorkerToggle = document.getElementById('toggle-local-ai-worker');
      if (origWorkerToggle) {
        origWorkerToggle.checked = workerToggle.checked;
        origWorkerToggle.dispatchEvent(new Event('change'));
      }
    });
  }

  // Autostart toggles no modal
  const btnAutoOn = document.getElementById('ag-toggle-autostart-on');
  const btnAutoOff = document.getElementById('ag-toggle-autostart-off');
  if (btnAutoOn && btnAutoOff) {
    btnAutoOn.addEventListener('click', () => {
      btnAutoOn.classList.add('active');
      btnAutoOff.classList.remove('active');
      const origBtn = document.getElementById('btn-autostart-toggle') || document.getElementById('btn-autostart-toggle-overview');
      if (origBtn && !document.body.classList.contains('autostart-active')) {
        origBtn.click();
      }
    });
    btnAutoOff.addEventListener('click', () => {
      btnAutoOff.classList.add('active');
      btnAutoOn.classList.remove('active');
      const origBtn = document.getElementById('btn-autostart-toggle') || document.getElementById('btn-autostart-toggle-overview');
      if (origBtn && document.body.classList.contains('autostart-active')) {
        origBtn.click();
      }
    });
  }
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
  // Views principais (Terminal é primário)
  items.push({ label: 'Terminal / OpenCode Runner', badge: 'PRIMARY', action: () => switchTab('view-terminal') });
  items.push({ label: 'Fluxo & Kanban das Fatias', badge: 'VIEW', action: () => switchTab('view-flow') });
  items.push({ label: 'Codebase Knowledge Graph', badge: 'VIEW', action: () => switchTab('view-graph') });
  items.push({ label: 'Gauntlet Verdicts Log', badge: 'VIEW', action: () => switchTab('view-gauntlet') });
  items.push({ label: 'Handoff & Master Blueprint', badge: 'VIEW', action: () => switchTab('view-handoff') });
  items.push({ label: 'Local Worker & Ollama Manager', badge: 'AI', action: () => switchTab('view-worker') });
  items.push({ label: 'Configurações do Cockpit', badge: 'SETTINGS', action: () => openSettingsModal() });

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
