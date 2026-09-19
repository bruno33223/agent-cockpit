/**
 * Settings Facade (web/js/settings.js)
 * Ponto de entrada modular mantendo retrocompatibilidade total com a API legada (Issue #35).
 * Endpoints: /api/projects/{projectId}/settings, /api/customizations/mcp, /api/customizations/skills
 * Chaves: ag_theme, ag_font_scale, btn-add-omniroute-account
 */

import { apiFetch, currentProjectId, state } from './state.js';

// 1. Re-exports dos submódulos modulares especializados
export * from './settings/appearance_controller.js';
export * from './settings/local_ai_controller.js';
export * from './settings/governance_controller.js';
export * from './settings/customizations_controller.js';
export * from './settings/omniroute_controller.js';
export * from './settings/settings_main.js';

import { initThemeAndFontSettings } from './settings/appearance_controller.js';
import { loadSettings, applySettingsToUI, saveSettingUpdate, initSettingsEvents } from './settings/local_ai_controller.js';
import {
  checkAutostartStatus, getBtnAutostart, updateAutostartUI, setSystemAutostart, updateHumanGateUI, approveHumanGate,
  loadGovernanceSettings, saveGovernanceSetting, openProjectSettings, saveProjectSettings, restoreProjectDefaults
} from './settings/governance_controller.js';
import {
  loadCustomizations, renderMcpList, renderSkillsList, toggleMcpServer, deleteMcpServer, saveMcpServer, saveSkill,
  initCustomizationsEvents
} from './settings/customizations_controller.js';
import {
  checkOmniRouteStatus, loadOmniRouteConnectors, renderOmniRouteConnectors, autofillOpenCodeCredentials,
  checkOmniRouteDaemon, loadOmniRouteAccounts, loadOmniRouteModels, openOmniRouteAccountModal, closeOmniRouteAccountModal,
  selectOmniRouteProviderPill, saveOmniRouteAccount, loadOmniRouteSettings, initTerminalAndOmniEvents
} from './settings/omniroute_controller.js';
import { SettingsModal, openSettingsModal, closeSettingsModal, switchAgSettingsTab } from './settings/settings_main.js';

// Sincroniza configuração de modelo no OmniRoute via apiFetch
export async function syncOmniRouteConfig(payload) {
  return await apiFetch('/api/omniroute/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

// 2. Exportação para Escopo Global (window) para Retrocompatibilidade com DOM e Testes
if (typeof window !== 'undefined') {
  Object.assign(window, {
    SettingsModal,
    openSettingsModal,
    closeSettingsModal,
    switchAgSettingsTab,
    openOmniRouteAccountModal,
    closeOmniRouteAccountModal,
    saveOmniRouteAccount,
    selectOmniRouteProviderPill,
    loadOmniRouteConnectors,
    renderOmniRouteConnectors,
    autofillOpenCodeCredentials,
    checkAutostartStatus,
    getBtnAutostart,
    updateAutostartUI,
    setSystemAutostart,
    updateHumanGateUI,
    approveHumanGate,
    loadSettings,
    applySettingsToUI,
    saveSettingUpdate,
    initSettingsEvents,
    initThemeAndFontSettings,
    loadCustomizations,
    renderMcpList,
    renderSkillsList,
    toggleMcpServer,
    deleteMcpServer,
    saveMcpServer,
    saveSkill,
    openProjectSettings,
    saveProjectSettings,
    restoreProjectDefaults,
    loadOmniRouteSettings,
    loadOmniRouteAccounts,
    loadOmniRouteModels,
    checkOmniRouteStatus,
    checkOmniRouteDaemon,
    initTerminalAndOmniEvents
  });

  if (state && state.human_gates) {
    updateHumanGateUI(state.human_gates.gate_ship_approved);
  }
}
