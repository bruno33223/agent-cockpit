/**
 * Governance Controller
 * Governança de execução, human gates, políticas de autostart e configurações de projetos (/api/projects/).
 */

import { apiFetch, currentProjectId, state } from '../state.js';
export {
  openProjectSettings,
  saveProjectSettings,
  restoreProjectDefaults,
  activeProjectSettingsId,
  currentProjectSettingsData,
  initProjectSettingsEvents,
  renderProjectSettingsUI,
  toggleFieldOverride,
  updateProjectInheritanceSummary
} from './project_settings_controller.js';

let autostartEnabled = false;

export async function checkAutostartStatus() {
  try {
    const res = await apiFetch('/api/autostart');
    if (res.ok) {
      const data = await res.json();
      updateAutostartUI(data.enabled);
    }
  } catch (err) {
    console.warn('[Autostart] Falha ao checar status:', err);
  }
}

export function getBtnAutostart() {
  return document.getElementById("btn-toggle-autostart") || document.getElementById("ag-btn-autostart-on");
}

export function updateAutostartUI(enabled) {
  autostartEnabled = !!enabled;
  const btnOn = document.getElementById('ag-btn-autostart-on');
  const btnOff = document.getElementById('ag-btn-autostart-off');
  if (btnOn && btnOff) {
    if (autostartEnabled) {
      btnOn.classList.add('active');
      btnOff.classList.remove('active');
    } else {
      btnOff.classList.add('active');
      btnOn.classList.remove('active');
    }
  }
}

export async function setSystemAutostart(enable) {
  try {
    const res = await apiFetch('/api/autostart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !!enable })
    });
    if (res.ok) {
      const data = await res.json();
      updateAutostartUI(data.enabled);
    }
  } catch (err) {
    console.error('[Autostart] Falha ao alterar autostart:', err);
  }
}

export function updateHumanGateUI(isApproved) {
  const badge = document.getElementById('ag-gate-badge');
  const btnApprove = document.getElementById('btn-ag-approve-gate');
  if (badge) {
    if (isApproved) {
      badge.className = 'gatekeeper-badge approved';
      badge.textContent = 'Gate: Liberado / Aprovado';
      if (btnApprove) btnApprove.style.display = 'none';
    } else {
      badge.className = 'gatekeeper-badge pending';
      badge.textContent = 'Gate: Pendente';
      if (btnApprove) btnApprove.style.display = 'inline-flex';
    }
  }
}

export async function approveHumanGate() {
  try {
    const btnApprove = document.getElementById('btn-ag-approve-gate');
    if (btnApprove) {
      btnApprove.disabled = true;
      btnApprove.innerHTML = 'Aprovando...';
    }
    const res = await apiFetch('/api/gates/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gate_name: 'gate_ship_approved', project_id: currentProjectId })
    });
    if (res.ok) {
      updateHumanGateUI(true);
    }
  } catch (err) {
    console.error('[HumanGate] Falha ao aprovar portão:', err);
  } finally {
    const btnApprove = document.getElementById('btn-ag-approve-gate');
    if (btnApprove) {
      btnApprove.disabled = false;
      btnApprove.innerHTML = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg> Aprovar Gate';
    }
  }
}

export let currentGovernance = {
  autostart_slices: false,
  security_preset: 'standard',
  human_gate_policy: 'always',
  artifact_review_policy: 'strict'
};

export async function loadGovernanceSettings() {
  try {
    const res = await apiFetch(`/api/governance?project_id=${encodeURIComponent(currentProjectId)}`);
    if (res.ok) {
      const data = await res.json();
      currentGovernance = Object.assign(currentGovernance, data);
      applyGovernanceToUI(currentGovernance);
    }
  } catch (err) {
    console.warn('[Governance] Falha ao carregar governança:', err);
  }
}

export function applyGovernanceToUI(gov) {
  if (!gov) return;
  const btnAutoOn = document.getElementById('ag-toggle-autostart-on');
  const btnAutoOff = document.getElementById('ag-toggle-autostart-off');
  if (btnAutoOn && btnAutoOff) {
    btnAutoOn.classList.toggle('active', !!gov.autostart_slices);
    btnAutoOff.classList.toggle('active', !gov.autostart_slices);
  }

  const secPreset = document.getElementById('ag-security-preset');
  if (secPreset && gov.security_preset) {
    secPreset.value = gov.security_preset;
  }

  const gatePolicy = document.getElementById('ag-gate-policy');
  if (gatePolicy && gov.human_gate_policy) {
    gatePolicy.value = gov.human_gate_policy;
  }

  const artifactPolicy = document.getElementById('ag-artifact-policy');
  if (artifactPolicy && gov.artifact_review_policy) {
    artifactPolicy.value = gov.artifact_review_policy;
  }
}

export async function saveGovernanceSetting(updates) {
  try {
    const payload = Object.assign({ project_id: currentProjectId }, updates);
    const res = await apiFetch('/api/governance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const data = await res.json();
      currentGovernance = Object.assign(currentGovernance, data);
      applyGovernanceToUI(currentGovernance);
      console.log('[Governance] Configurações de governança atualizadas com sucesso.');
    }
  } catch (err) {
    console.error('[Governance] Falha ao atualizar governança:', err);
  }
}

export function initGovernanceEvents() {
  const btnSystemAutoOn = document.getElementById('ag-btn-autostart-on');
  const btnSystemAutoOff = document.getElementById('ag-btn-autostart-off');
  if (btnSystemAutoOn && btnSystemAutoOff) {
    btnSystemAutoOn.addEventListener('click', () => {
      setSystemAutostart(true);
    });
    btnSystemAutoOff.addEventListener('click', () => {
      setSystemAutostart(false);
    });
  }

  const btnApproveGate = document.getElementById('btn-ag-approve-gate');
  if (btnApproveGate) {
    btnApproveGate.addEventListener('click', () => {
      approveHumanGate();
    });
  }

  const btnAutoOn = document.getElementById('ag-toggle-autostart-on');
  const btnAutoOff = document.getElementById('ag-toggle-autostart-off');
  if (btnAutoOn && btnAutoOff) {
    btnAutoOn.addEventListener('click', () => {
      btnAutoOn.classList.add('active');
      btnAutoOff.classList.remove('active');
      saveGovernanceSetting({ autostart_slices: true });
    });
    btnAutoOff.addEventListener('click', () => {
      btnAutoOff.classList.add('active');
      btnAutoOn.classList.remove('active');
      saveGovernanceSetting({ autostart_slices: false });
    });
  }

  const secPreset = document.getElementById('ag-security-preset');
  if (secPreset) {
    secPreset.addEventListener('change', () => {
      saveGovernanceSetting({ security_preset: secPreset.value });
    });
  }

  const gatePolicy = document.getElementById('ag-gate-policy');
  if (gatePolicy) {
    gatePolicy.addEventListener('change', () => {
      saveGovernanceSetting({ human_gate_policy: gatePolicy.value });
    });
  }

  const artifactPolicy = document.getElementById('ag-artifact-policy');
  if (artifactPolicy) {
    artifactPolicy.addEventListener('change', () => {
      saveGovernanceSetting({ artifact_review_policy: artifactPolicy.value });
    });
  }

  checkAutostartStatus();
  if (typeof state !== "undefined" && state && state.human_gates) {
    updateHumanGateUI(state.human_gates.gate_ship_approved);
  }
}
