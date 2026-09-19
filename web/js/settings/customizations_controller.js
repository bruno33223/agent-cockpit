/**
 * Customizations Controller
 * Gestão de Servidores MCP e Skills personalizadas (Issue #16).
 */

import { apiFetch, currentProjectId } from '../state.js';
import { escapeHtml } from '../ui_utils.js';

export let currentCustomizations = { mcp: {}, skills: [] };

export async function loadCustomizations() {
  try {
    const [mcpRes, skillsRes] = await Promise.all([
      apiFetch(`/api/customizations/mcp?project_id=${encodeURIComponent(currentProjectId)}`),
      apiFetch(`/api/customizations/skills?project_id=${encodeURIComponent(currentProjectId)}`)
    ]);
    const mcps = mcpRes.ok ? (await mcpRes.json()).mcp_servers || {} : {};
    const skills = skillsRes.ok ? (await skillsRes.json()).skills || [] : [];
    currentCustomizations = { mcp: mcps, skills };
    renderMcpList(mcps);
    renderSkillsList(skills);
  } catch (err) {
    console.warn('[Customizations] Falha ao carregar customizações:', err);
  }
}

export function renderMcpList(mcps) {
  const container = document.getElementById('mcp-servers-list');
  if (!container) return;
  container.innerHTML = '';
  const entries = Array.isArray(mcps) ? mcps.map(m => [m.id || m.name || 'mcp', m]) : Object.entries(mcps || {});

  if (entries.length === 0) {
    container.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--text-muted); font-size: 12px; border: 1px dashed var(--border-subtle); border-radius: 6px;">Nenhum servidor MCP configurado ainda. Clique em "Adicionar MCP" para cadastrar um servidor Stdio ou SSE.</div>';
    return;
  }

  entries.forEach(([id, mcp]) => {
    const card = document.createElement('div');
    card.className = 'ag-mcp-server-item';
    card.dataset.mcpId = id;
    const isEnabled = mcp.enabled !== false;
    const isSse = mcp.type === 'sse' || !!mcp.url;
    const detail = isSse ? escapeHtml(mcp.url || '') : `${escapeHtml(mcp.command || '')} ${escapeHtml((mcp.args || []).join(' '))}`.trim();

    card.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
        <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
          <span class="pulse-led ${isEnabled ? 'online' : 'stopped'}"></span>
          <div style="min-width: 0;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <strong class="ag-mcp-name" style="font-size: 13px;">${escapeHtml(id)}</strong>
              <span class="lw-badge ${isSse ? '' : 'active'}" style="font-size: 10px; padding: 1px 6px;">${isSse ? 'SSE' : 'Stdio'}</span>
              <span style="font-size: 11px; color: ${isEnabled ? 'var(--color-success, #00ff66)' : 'var(--text-muted)'};">${isEnabled ? 'Ativo' : 'Desativado'}</span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted); font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 380px;">${detail || 'Sem comando especificado'}</div>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <button class="btn btn-secondary btn-sm btn-edit-mcp" data-id="${escapeHtml(id)}" style="padding: 4px 8px; font-size: 11px;">Editar</button>
          <button class="btn btn-secondary btn-sm btn-toggle-mcp" data-id="${escapeHtml(id)}" style="padding: 4px 8px; font-size: 11px;">${isEnabled ? 'Desativar' : 'Ativar'}</button>
          <button class="btn btn-danger btn-sm btn-delete-mcp" data-id="${escapeHtml(id)}" style="padding: 4px 8px; font-size: 11px; color: #ef4444; border-color: rgba(239, 68, 68, 0.3);">Excluir</button>
        </div>
      </div>
    `;
    card.querySelector('.btn-edit-mcp')?.addEventListener('click', () => openMcpModal('edit', id, mcp));
    card.querySelector('.btn-toggle-mcp')?.addEventListener('click', () => toggleMcpServer(id, !isEnabled));
    card.querySelector('.btn-delete-mcp')?.addEventListener('click', () => deleteMcpServer(id));
    container.appendChild(card);
  });
}

export function renderSkillsList(skills) {
  const container = document.getElementById('skills-list');
  if (!container) return;
  container.innerHTML = '';
  const list = Array.isArray(skills) ? skills : [];

  if (list.length === 0) {
    container.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--text-muted); font-size: 12px; border: 1px dashed var(--border-subtle); border-radius: 6px;">Nenhuma skill personalizada encontrada. Clique em "Adicionar Skill" para registrar novas diretrizes e fluxos.</div>';
    return;
  }

  list.forEach(skill => {
    const name = skill.name || skill.id || 'sem-nome';
    const isEnabled = skill.enabled !== false;
    const card = document.createElement('div');
    card.className = 'ag-mcp-server-item';
    card.dataset.skillName = name;

    card.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
        <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
          <span class="pulse-led ${isEnabled ? 'online' : 'stopped'}"></span>
          <div style="min-width: 0;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <strong style="font-size: 13px; color: var(--text-primary);">${escapeHtml(name)}</strong>
              <span style="font-size: 11px; color: ${isEnabled ? 'var(--color-success, #00ff66)' : 'var(--text-muted)'};">${isEnabled ? 'Ativa' : 'Desativada'}</span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 380px;">${escapeHtml(skill.description || 'Sem descrição')}</div>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <button class="btn btn-secondary btn-sm btn-edit-skill" style="padding: 4px 8px; font-size: 11px;">Editar</button>
          <button class="btn btn-secondary btn-sm btn-toggle-skill" style="padding: 4px 8px; font-size: 11px;">${isEnabled ? 'Desativar' : 'Ativar'}</button>
          <button class="btn btn-danger btn-sm btn-delete-skill" style="padding: 4px 8px; font-size: 11px; color: #ef4444; border-color: rgba(239, 68, 68, 0.3);">Excluir</button>
        </div>
      </div>
    `;
    card.querySelector('.btn-edit-skill')?.addEventListener('click', () => openSkillModal('edit', skill));
    card.querySelector('.btn-toggle-skill')?.addEventListener('click', () => toggleSkill(name, !isEnabled));
    card.querySelector('.btn-delete-skill')?.addEventListener('click', () => deleteSkill(name));
    container.appendChild(card);
  });
}

export async function toggleMcpServer(mcpId, enable) {
  try {
    const res = await apiFetch(`/api/customizations/mcp/${encodeURIComponent(mcpId)}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !!enable, project_id: currentProjectId })
    });
    if (res.ok) await loadCustomizations();
  } catch (err) {
    console.error('[Customizations] Erro ao alternar MCP:', err);
  }
}

export async function deleteMcpServer(mcpId) {
  if (typeof confirm === 'function' && !confirm(`Deseja realmente remover o servidor MCP "${mcpId}"?`)) return;
  try {
    const res = await apiFetch(`/api/customizations/mcp/${encodeURIComponent(mcpId)}?project_id=${encodeURIComponent(currentProjectId)}`, {
      method: 'DELETE'
    });
    if (res.ok) await loadCustomizations();
  } catch (err) {
    console.error('[Customizations] Erro ao excluir MCP:', err);
  }
}

export async function saveMcpServer(mcpData) {
  const { id, originalId, mode, ...payload } = mcpData;
  payload.project_id = currentProjectId;
  const isEdit = mode === 'edit';
  const targetId = isEdit ? (originalId || id) : id;
  const endpoint = isEdit ? `/api/customizations/mcp/${encodeURIComponent(targetId)}` : '/api/customizations/mcp';
  const res = await apiFetch(endpoint, {
    method: isEdit ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(isEdit ? { id: targetId, ...payload } : { id, ...payload })
  });
  if (res.ok) {
    closeMcpModal();
    await loadCustomizations();
  } else {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Falha ao salvar servidor MCP');
  }
}

export async function toggleSkill(skillName, enable) {
  try {
    const res = await apiFetch(`/api/customizations/skills/${encodeURIComponent(skillName)}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !!enable, project_id: currentProjectId })
    });
    if (res.ok) await loadCustomizations();
  } catch (err) {
    console.error('[Customizations] Erro ao alternar skill:', err);
  }
}

export async function deleteSkill(skillName) {
  if (typeof confirm === 'function' && !confirm(`Deseja realmente remover a Skill "${skillName}"?`)) return;
  try {
    const res = await apiFetch(`/api/customizations/skills/${encodeURIComponent(skillName)}?project_id=${encodeURIComponent(currentProjectId)}`, {
      method: 'DELETE'
    });
    if (res.ok) await loadCustomizations();
  } catch (err) {
    console.error('[Customizations] Erro ao excluir skill:', err);
  }
}

export async function saveSkill(skillData) {
  const { name, originalName, mode, ...payload } = skillData;
  payload.project_id = currentProjectId;
  const isEdit = mode === 'edit';
  const targetName = isEdit ? (originalName || name) : name;
  const endpoint = isEdit ? `/api/customizations/skills/${encodeURIComponent(targetName)}` : '/api/customizations/skills';
  const res = await apiFetch(endpoint, {
    method: isEdit ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(isEdit ? { name: targetName, ...payload } : { name, ...payload })
  });
  if (res.ok) {
    closeSkillModal();
    await loadCustomizations();
  } else {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Falha ao salvar skill');
  }
}

export function openMcpModal(mode = 'create', id = '', mcp = {}) {
  const modal = document.getElementById('modal-mcp-server');
  if (!modal) return;
  const setValue = (eid, val) => { const el = document.getElementById(eid); if (el) el.value = val; };
  const feedback = document.getElementById('mcp-form-feedback');
  if (feedback) feedback.style.display = 'none';

  const isEdit = mode === 'edit';
  document.getElementById('modal-mcp-title').textContent = isEdit ? `Editar MCP: ${id}` : 'Adicionar Novo MCP';
  setValue('mcp-form-mode', mode);
  setValue('mcp-form-original-id', isEdit ? id : '');
  const nameInput = document.getElementById('mcp-form-name');
  if (nameInput) { nameInput.value = isEdit ? id : ''; nameInput.disabled = isEdit; }
  setValue('mcp-form-type', mcp.type === 'sse' || mcp.url ? 'sse' : 'stdio');
  setValue('mcp-form-command', mcp.command || '');
  setValue('mcp-form-args', Array.isArray(mcp.args) ? JSON.stringify(mcp.args) : (mcp.args || ''));
  setValue('mcp-form-env', mcp.env ? JSON.stringify(mcp.env, null, 2) : '');
  setValue('mcp-form-url', mcp.url || '');
  updateMcpFormTypeFields();
  modal.style.display = 'flex';
}

export function closeMcpModal() {
  const modal = document.getElementById('modal-mcp-server');
  if (modal) modal.style.display = 'none';
}

export function updateMcpFormTypeFields() {
  const typeSelect = document.getElementById('mcp-form-type');
  const stdioGroup = document.getElementById('mcp-form-stdio-group');
  const sseGroup = document.getElementById('mcp-form-sse-group');
  if (!typeSelect) return;
  const isSse = typeSelect.value === 'sse';
  if (stdioGroup) stdioGroup.style.display = isSse ? 'none' : 'flex';
  if (sseGroup) sseGroup.style.display = isSse ? 'flex' : 'none';
}

export function openSkillModal(mode = 'create', skill = {}) {
  const modal = document.getElementById('modal-skill');
  if (!modal) return;
  const setValue = (eid, val) => { const el = document.getElementById(eid); if (el) el.value = val; };
  const feedback = document.getElementById('skill-form-feedback');
  if (feedback) feedback.style.display = 'none';
  const skillName = skill.name || skill.id || '';
  const isEdit = mode === 'edit';

  document.getElementById('modal-skill-title').textContent = isEdit ? `Editar Skill: ${skillName}` : 'Adicionar Nova Skill';
  setValue('skill-form-mode', mode);
  setValue('skill-form-original-name', isEdit ? skillName : '');
  const nameInput = document.getElementById('skill-form-name');
  if (nameInput) { nameInput.value = isEdit ? skillName : ''; nameInput.disabled = isEdit; }
  setValue('skill-form-desc', skill.description || '');
  setValue('skill-form-content', skill.content || skill.instructions || '');
  modal.style.display = 'flex';
}

export function closeSkillModal() {
  const modal = document.getElementById('modal-skill');
  if (modal) modal.style.display = 'none';
}

export function initCustomizationsEvents() {
  document.getElementById('btn-add-mcp')?.addEventListener('click', () => openMcpModal('create'));
  document.getElementById('btn-close-mcp-modal')?.addEventListener('click', closeMcpModal);
  document.getElementById('btn-cancel-mcp-form')?.addEventListener('click', closeMcpModal);
  document.getElementById('mcp-form-type')?.addEventListener('change', updateMcpFormTypeFields);

  document.getElementById('btn-save-mcp')?.addEventListener('click', async () => {
    const mode = document.getElementById('mcp-form-mode')?.value || 'create';
    const originalId = document.getElementById('mcp-form-original-id')?.value || '';
    const name = document.getElementById('mcp-form-name')?.value?.trim();
    const type = document.getElementById('mcp-form-type')?.value || 'stdio';
    if (!name) return;
    let mcpPayload = { id: name, originalId, mode, type };
    if (type === 'sse') {
      mcpPayload.url = document.getElementById('mcp-form-url')?.value?.trim() || '';
    } else {
      mcpPayload.command = document.getElementById('mcp-form-command')?.value?.trim() || '';
      const rawArgs = document.getElementById('mcp-form-args')?.value?.trim() || '';
      const rawEnv = document.getElementById('mcp-form-env')?.value?.trim() || '';
      mcpPayload.args = rawArgs.startsWith('[') ? JSON.parse(rawArgs || '[]') : rawArgs.split(' ').filter(Boolean);
      mcpPayload.env = rawEnv.startsWith('{') ? JSON.parse(rawEnv || '{}') : {};
    }
    await saveMcpServer(mcpPayload);
  });

  document.getElementById('btn-add-skill')?.addEventListener('click', () => openSkillModal('create'));
  document.getElementById('btn-close-skill-modal')?.addEventListener('click', closeSkillModal);
  document.getElementById('btn-cancel-skill-form')?.addEventListener('click', closeSkillModal);

  document.getElementById('btn-save-skill')?.addEventListener('click', async () => {
    const mode = document.getElementById('skill-form-mode')?.value || 'create';
    const originalName = document.getElementById('skill-form-original-name')?.value || '';
    const name = document.getElementById('skill-form-name')?.value?.trim();
    const description = document.getElementById('skill-form-desc')?.value?.trim();
    const content = document.getElementById('skill-form-content')?.value?.trim();
    if (!name || !content) return;
    await saveSkill({ name, originalName, mode, description, content });
  });

  document.getElementById('ag-tab-btn-customizations')?.addEventListener('click', () => loadCustomizations());
}
