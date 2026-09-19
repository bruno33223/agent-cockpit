/**
 * Project Settings Controller
 * Gestão de configurações e overrides específicos por projeto (Issue #17).
 */

import { apiFetch, currentProjectId, knownProjects } from '../state.js';

export let activeProjectSettingsId = null;
export let currentProjectSettingsData = {
  project_id: null,
  effective_settings: {},
  general_defaults: {},
  overrides: {}
};

const PROJECT_CONFIG_FIELDS = [
  'enable_local_ai',
  'model',
  'delegate_styles_to_cloud',
  'circuit_breaker_threshold',
  'security_preset',
  'autostart_slices'
];

function getFieldInputId(field) {
  switch (field) {
    case 'enable_local_ai': return 'proj-toggle-enable-local-ai';
    case 'model': return 'proj-input-model';
    case 'delegate_styles_to_cloud': return 'proj-toggle-delegate-styles';
    case 'circuit_breaker_threshold': return 'proj-input-breaker-threshold';
    case 'security_preset': return 'proj-select-security-preset';
    case 'autostart_slices': return 'proj-toggle-autostart-slices';
    default: return null;
  }
}

function getFieldValueFromDOM(field) {
  const elId = getFieldInputId(field);
  const el = document.getElementById(elId);
  if (!el) return undefined;
  if (el.type === 'checkbox') return el.checked;
  if (el.type === 'number') return parseInt(el.value, 10) || 1;
  return el.value;
}

function setFieldDomValue(field, val) {
  const elId = getFieldInputId(field);
  const el = document.getElementById(elId);
  if (!el) return;
  if (el.type === 'checkbox') {
    el.checked = !!val;
  } else {
    el.value = (val !== undefined && val !== null) ? val : '';
  }
}

function updateFieldInheritanceBadge(field, isOverridden) {
  const tag = document.getElementById(`tag-proj-${field}`);
  const btn = document.querySelector(`.btn-toggle-override[data-field="${field}"]`);
  if (tag) {
    if (isOverridden) {
      tag.textContent = 'CUSTOMIZADO';
      tag.className = 'inheritance-tag tag-custom';
      tag.style.background = 'rgba(245, 158, 11, 0.15)';
      tag.style.color = '#f59e0b';
    } else {
      tag.textContent = 'HERDADO';
      tag.className = 'inheritance-tag tag-inherited';
      tag.style.background = 'rgba(59, 130, 246, 0.15)';
      tag.style.color = '#3b82f6';
    }
  }
  if (btn) {
    btn.textContent = isOverridden ? 'Herdar Padrão' : 'Personalizar';
  }
}

export function updateProjectInheritanceSummary() {
  const summaryEl = document.getElementById('project-inheritance-summary');
  if (!summaryEl) return;
  const overrides = currentProjectSettingsData.overrides || {};
  const count = Object.keys(overrides).length;
  if (count === 0) {
    summaryEl.textContent = 'HERDADO (100% Padrão Geral)';
    summaryEl.style.color = '#3b82f6';
  } else {
    summaryEl.textContent = `CUSTOMIZADO (${count} override${count > 1 ? 's' : ''})`;
    summaryEl.style.color = '#f59e0b';
  }
}

export async function openProjectSettings(projectId) {
  if (!projectId) {
    projectId = currentProjectId || (knownProjects && knownProjects[0] && knownProjects[0].id) || 'default';
  }
  activeProjectSettingsId = projectId;

  // 1. Ativa a aba #ag-panel-project-settings sem fechar o modal
  document.querySelectorAll('.ag-nav-item').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.ag-tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === 'ag-panel-project-settings');
  });

  // 2. Destaca visualmente o projeto selecionado na lista lateral
  const navItems = document.querySelectorAll('.ag-project-nav-item');
  navItems.forEach(item => {
    const isTarget = (item.getAttribute('data-project-id') === projectId) ||
                     (item.querySelector('.ag-project-name')?.textContent?.trim() === projectId);
    item.classList.toggle('active', isTarget);
  });

  // 3. Atualiza cabeçalho com nome do projeto
  const projObj = (knownProjects || []).find(p => p.id === projectId);
  const projName = projObj ? projObj.name : projectId;
  const titleName = document.getElementById('project-settings-current-name');
  const titleId = document.getElementById('project-settings-current-id');
  if (titleName) titleName.textContent = `Projeto: ${projName}`;
  if (titleId) titleId.textContent = `ID: ${projectId}`;

  // 4. Carrega da API /api/projects/{projectId}/settings
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/settings`);
    if (res.ok) {
      const data = await res.json();
      currentProjectSettingsData = data;
      renderProjectSettingsUI(data);
    } else {
      console.warn(`[ProjectSettings] Falha ao carregar configurações do projeto ${projectId}:`, res.status);
    }
  } catch (err) {
    console.error(`[ProjectSettings] Erro de rede ao buscar configurações do projeto ${projectId}:`, err);
  }
}

export function renderProjectSettingsUI(data) {
  if (!data) return;
  const eff = data.effective_settings || {};
  const defaults = data.general_defaults || {};
  const overrides = data.overrides || {};

  PROJECT_CONFIG_FIELDS.forEach(field => {
    const isOverridden = Object.prototype.hasOwnProperty.call(overrides, field) && overrides[field] !== null;
    const value = isOverridden ? overrides[field] : (eff[field] !== undefined ? eff[field] : defaults[field]);
    setFieldDomValue(field, value);
    updateFieldInheritanceBadge(field, isOverridden);
  });

  updateProjectInheritanceSummary();
}

export function toggleFieldOverride(field) {
  if (!currentProjectSettingsData) return;
  if (!currentProjectSettingsData.overrides) {
    currentProjectSettingsData.overrides = {};
  }
  const overrides = currentProjectSettingsData.overrides;
  const isCurrentlyOverridden = Object.prototype.hasOwnProperty.call(overrides, field) && overrides[field] !== null;

  if (isCurrentlyOverridden) {
    delete overrides[field];
    const defaultVal = currentProjectSettingsData.general_defaults ? currentProjectSettingsData.general_defaults[field] : undefined;
    setFieldDomValue(field, defaultVal);
    updateFieldInheritanceBadge(field, false);
  } else {
    const currentVal = getFieldValueFromDOM(field);
    overrides[field] = currentVal;
    updateFieldInheritanceBadge(field, true);
  }

  updateProjectInheritanceSummary();
}

export async function saveProjectSettings(projectId) {
  const targetId = projectId || activeProjectSettingsId || currentProjectId;
  if (!targetId) return;

  const btnSave = document.getElementById('btn-save-project-settings');
  const feedback = document.getElementById('proj-settings-feedback');

  const overrides = {};
  const activeOverridesKeys = Object.keys(currentProjectSettingsData.overrides || {});
  activeOverridesKeys.forEach(field => {
    overrides[field] = getFieldValueFromDOM(field);
  });

  try {
    if (btnSave) {
      btnSave.disabled = true;
      btnSave.textContent = 'Salvando...';
    }
    const res = await apiFetch(`/api/projects/${encodeURIComponent(targetId)}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ overrides, project_id: targetId })
    });

    if (res.ok) {
      const data = await res.json();
      currentProjectSettingsData = data;
      renderProjectSettingsUI(data);

      if (feedback) {
        feedback.style.display = 'inline-block';
        feedback.style.background = 'rgba(16, 185, 129, 0.15)';
        feedback.style.color = '#10b981';
        feedback.textContent = 'Configurações e overrides salvos com sucesso!';
        setTimeout(() => { feedback.style.display = 'none'; }, 3500);
      }
    } else {
      throw new Error(`Erro ao salvar overrides (HTTP ${res.status})`);
    }
  } catch (err) {
    console.error('[ProjectSettings] Falha ao salvar overrides:', err);
    if (feedback) {
      feedback.style.display = 'inline-block';
      feedback.style.background = 'rgba(239, 68, 68, 0.15)';
      feedback.style.color = '#ef4444';
      feedback.textContent = `Falha: ${err.message}`;
    }
  } finally {
    if (btnSave) {
      btnSave.disabled = false;
      btnSave.textContent = 'Salvar Overrides';
    }
  }
}

export async function restoreProjectDefaults(projectId) {
  const targetId = projectId || activeProjectSettingsId || currentProjectId;
  if (!targetId) return;

  const btnRestore = document.getElementById('btn-restore-project-defaults');
  const feedback = document.getElementById('proj-settings-feedback');

  try {
    if (btnRestore) {
      btnRestore.disabled = true;
    }
    const res = await apiFetch(`/api/projects/${encodeURIComponent(targetId)}/settings/overrides`, {
      method: 'DELETE'
    });

    if (res.ok) {
      const data = await res.json();
      currentProjectSettingsData = data;
      renderProjectSettingsUI(data);

      if (feedback) {
        feedback.style.display = 'inline-block';
        feedback.style.background = 'rgba(59, 130, 246, 0.15)';
        feedback.style.color = '#3b82f6';
        feedback.textContent = 'Padrões gerais restaurados com sucesso! Todos os overrides foram limpos.';
        setTimeout(() => { feedback.style.display = 'none'; }, 3500);
      }
    } else {
      throw new Error(`Erro ao restaurar padrões gerais (HTTP ${res.status})`);
    }
  } catch (err) {
    console.error('[ProjectSettings] Falha ao restaurar padrões gerais:', err);
    if (feedback) {
      feedback.style.display = 'inline-block';
      feedback.style.background = 'rgba(239, 68, 68, 0.15)';
      feedback.style.color = '#ef4444';
      feedback.textContent = `Falha ao restaurar: ${err.message}`;
    }
  } finally {
    if (btnRestore) {
      btnRestore.disabled = false;
    }
  }
}

export function initProjectSettingsEvents() {
  const projectsNavList = document.getElementById('ag-projects-nav-list');
  if (projectsNavList) {
    projectsNavList.addEventListener('click', (e) => {
      const item = e.target.closest('.ag-project-nav-item');
      if (!item) return;

      e.stopImmediatePropagation();
      e.preventDefault();

      let pid = item.getAttribute('data-project-id');
      if (!pid) {
        const nameSpan = item.querySelector('.ag-project-name');
        const name = nameSpan ? nameSpan.textContent.trim() : '';
        const found = (knownProjects || []).find(p => p.name === name || p.id === name);
        pid = found ? found.id : (name || currentProjectId);
      }

      if (pid) {
        openProjectSettings(pid);
      }
    }, true);
  }

  document.querySelectorAll('.btn-toggle-override').forEach(btn => {
    btn.addEventListener('click', () => {
      const field = btn.getAttribute('data-field');
      if (field) toggleFieldOverride(field);
    });
  });

  const btnSave = document.getElementById('btn-save-project-settings');
  if (btnSave) {
    btnSave.addEventListener('click', () => saveProjectSettings());
  }

  const btnRestore = document.getElementById('btn-restore-project-defaults');
  if (btnRestore) {
    btnRestore.addEventListener('click', () => restoreProjectDefaults());
  }
}
