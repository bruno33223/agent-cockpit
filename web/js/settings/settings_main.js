/**
 * Settings Main Controller
 * Orquestrador principal do Modal de Configurações, troca de abas e despacho de eventos.
 */

import { initThemeAndFontSettings } from './appearance_controller.js';
import { initSettingsEvents, loadSettings } from './local_ai_controller.js';
import {
  initGovernanceEvents,
  loadGovernanceSettings,
  initProjectSettingsEvents
} from './governance_controller.js';
import {
  initCustomizationsEvents,
  loadCustomizations
} from './customizations_controller.js';
import {
  initTerminalAndOmniEvents,
  loadOmniRouteSettings
} from './omniroute_controller.js';

export function openSettingsModal() {
  const modal = document.getElementById('modal-settings-antigravity');
  if (modal) {
    modal.style.display = 'flex';
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
  if (tabName === 'models') {
    loadOmniRouteSettings();
  } else if (tabName === 'customizations') {
    loadCustomizations();
  }
}

export function initSettingsMain() {
  // Configura navegação pelas abas
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

  // Inicializa todos os sub-controladores
  initThemeAndFontSettings();
  initSettingsEvents();
  initGovernanceEvents();
  loadGovernanceSettings();
  initProjectSettingsEvents();
  initCustomizationsEvents();
  loadCustomizations();
  initTerminalAndOmniEvents();
}

export const SettingsModal = {
  open: openSettingsModal,
  close: closeSettingsModal,
  switchTab: switchAgSettingsTab,
  init: initSettingsMain
};

if (typeof window !== 'undefined') {
  window.SettingsModal = SettingsModal;
  window.openSettingsModal = openSettingsModal;
  window.closeSettingsModal = closeSettingsModal;
  window.switchAgSettingsTab = switchAgSettingsTab;
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSettingsMain);
  } else {
    initSettingsMain();
  }
}
