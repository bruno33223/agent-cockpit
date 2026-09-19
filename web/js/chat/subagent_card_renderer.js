/**
 * SubagentCardRenderer - Renderização de cartões de subagentes e integração de terminais.
 * Issue #34 (Deduplicação e Arquitetura Modular do Zeus Chat)
 */

import { openSubagentTab, focusSubagentTab, getSubagentRoleMeta } from '../subagent_tabs.js';

const safeEscapeHtml = (str) => {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

export class SubagentCardRenderer {
  normalizeData(data = {}) {
    const subagentId = data.id || data.subagentId || data.subagent_id || `subagent-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    const role = data.role || data.type || data.subagent_type || 'builder';
    const sliceId = data.sliceId || data.slice_id || (data.taskId ? `task-${data.taskId}` : 'slice-1');
    const status = (data.status || 'RUNNING').toUpperCase();
    const agentType = data.agentType || data.agent_type || 'opencode';
    const targetFiles = Array.isArray(data.target_files) ? data.target_files : (Array.isArray(data.targetFiles) ? data.targetFiles : []);
    const worktreePath = data.worktree_path || data.worktreePath || '';
    const meta = (typeof getSubagentRoleMeta === 'function') ? getSubagentRoleMeta(role) : { icon: '🤖', label: 'Builder' };
    const title = data.title || `${meta.icon} [${meta.label}] ${sliceId}`;
    const description = data.description || data.task || `Subagente ${meta.label} para execução da fatia ${sliceId}.`;

    return {
      id: subagentId,
      subagentId,
      role,
      type: role,
      sliceId,
      status,
      agentType,
      title,
      description,
      targetFiles,
      target_files: targetFiles,
      worktreePath,
      worktree_path: worktreePath,
      meta,
      timestamp: new Date().toLocaleTimeString()
    };
  }

  createSubagentCard(subagentData = {}) {
    const d = this.normalizeData(subagentData);
    const stepDetails = document.createElement('details');
    stepDetails.className = 'zeus-step-item zeus-subagent-card-step';
    stepDetails.open = true;

    let filesHtml = '';
    if (d.targetFiles.length > 0) {
      filesHtml = `<div class="subagent-files" style="margin-top: 4px; font-size: 0.85em;">📁 Arquivos: ${d.targetFiles.map(f => `<code>${safeEscapeHtml(f)}</code>`).join(' ')}</div>`;
    }
    let worktreeHtml = '';
    if (d.worktreePath) {
      worktreeHtml = `<div class="subagent-worktree" style="margin-top: 4px; font-size: 0.85em;">🌿 Worktree: <code>${safeEscapeHtml(d.worktreePath)}</code></div>`;
    }

    stepDetails.innerHTML = `
      <summary class="zeus-step-summary" style="background: rgba(80, 160, 255, 0.08); border-left: 3px solid var(--accent, #3b82f6);">
        <span class="zeus-step-label">🤖 [${safeEscapeHtml(d.role.toUpperCase())}] Fatia <strong>${safeEscapeHtml(d.sliceId)}</strong></span>
        <span class="zeus-step-chevron">›</span>
      </summary>
      <div class="zeus-step-body" style="padding: 8px 12px;">
        <div style="font-weight: 500; margin-bottom: 4px;">${safeEscapeHtml(d.title)}</div>
        ${worktreeHtml}
        ${filesHtml}
        <div style="margin-top: 8px;">
          <button type="button" class="btn-open-subagent-terminal action-btn primary btn-sm" data-slice-id="${safeEscapeHtml(d.sliceId)}" data-subagent-id="${safeEscapeHtml(d.subagentId)}">
            Abrir Terminal do Subagente ↗
          </button>
        </div>
      </div>
    `;

    const btn = stepDetails.querySelector('.btn-open-subagent-terminal');
    if (btn) {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.navigateToSubagentTab(d);
      });
    }

    return stepDetails;
  }

  renderSubagentCardInContainer(subagentData = {}, container = null) {
    if (!container) return null;
    const d = this.normalizeData(subagentData);

    let existingCard = container.querySelector ? container.querySelector(`#subagent-card-${d.subagentId}`) : null;
    if (!existingCard && document.getElementById) {
      existingCard = document.getElementById(`subagent-card-${d.subagentId}`);
    }
    if (!existingCard) {
      existingCard = document.createElement('div');
      existingCard.id = `subagent-card-${d.subagentId}`;
      existingCard.className = 'zeus-subagent-card';
      container.appendChild(existingCard);
    }

    let metaTagsHtml = `
      <span class="meta-tag">⚡ Fatia: <code>${safeEscapeHtml(d.sliceId)}</code></span>
      <span class="meta-tag">🛠️ Motor: <code>${safeEscapeHtml(d.agentType)}</code></span>
    `;
    if (d.worktreePath) {
      metaTagsHtml += `<span class="meta-tag">🌿 Worktree: <code>${safeEscapeHtml(d.worktreePath)}</code></span>`;
    }

    let targetFilesHtml = '';
    if (d.targetFiles.length > 0) {
      targetFilesHtml = `
        <div class="subagent-target-files" style="margin-top: 6px; font-size: 0.85em; opacity: 0.9;">
          <span style="font-weight: 600;">📁 Arquivos afetados:</span>
          ${d.targetFiles.map(f => `<code style="margin-right: 4px; padding: 2px 4px; background: rgba(255,255,255,0.06); border-radius: 3px;">${safeEscapeHtml(f)}</code>`).join('')}
        </div>
      `;
    }

    existingCard.innerHTML = `
      <div class="zeus-subagent-card-header">
        <div class="subagent-title-wrap">
          <span class="subagent-icon">${d.meta.icon || '🤖'}</span>
          <strong class="subagent-name">${safeEscapeHtml(d.title)}</strong>
          <span class="subagent-badge role-${d.role}">${safeEscapeHtml(d.role.toUpperCase())}</span>
        </div>
        <span class="subagent-status status-${d.status.toLowerCase()}" id="chat-badge-${d.subagentId}">${d.status}</span>
      </div>
      <div class="zeus-subagent-card-body">
        <p class="subagent-task-desc">${safeEscapeHtml(d.description)}</p>
        <div class="subagent-meta-info">${metaTagsHtml}</div>
        ${targetFilesHtml}
      </div>
      <div class="zeus-subagent-card-actions">
        <button type="button" class="action-btn primary btn-sm btn-open-subagent-terminal" data-subagent-id="${d.subagentId}" title="Focar ou abrir aba dedicada do subagente sem fechar a sessão de chat">
          <span>Abrir Terminal do Subagente</span> <span>↗</span>
        </button>
      </div>
    `;

    const btnOpen = existingCard.querySelector('.btn-open-subagent-terminal');
    if (btnOpen) {
      btnOpen.addEventListener('click', (e) => {
        e.stopPropagation();
        this.navigateToSubagentTab(d);
      });
    }

    if (container.scrollTop !== undefined) {
      container.scrollTop = container.scrollHeight;
    }

    return existingCard;
  }

  navigateToSubagentTab(subagentData = {}) {
    const d = this.normalizeData(subagentData);
    let record = null;
    if (typeof openSubagentTab === 'function') {
      record = openSubagentTab(d);
    } else if (typeof window !== 'undefined' && typeof window.openSubagentTab === 'function') {
      record = window.openSubagentTab(d);
    }

    const targetId = (record && record.id) || d.subagentId;
    if (typeof focusSubagentTab === 'function') {
      focusSubagentTab(targetId);
    } else if (typeof window !== 'undefined' && typeof window.focusSubagentTab === 'function') {
      window.focusSubagentTab(targetId);
    }

    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('subagent_spawn', { detail: d }));
    }

    const badge = typeof document !== 'undefined' ? document.getElementById(`chat-badge-${d.subagentId}`) : null;
    if (badge && badge.classList) {
      badge.classList.add('focused-pulse');
      setTimeout(() => badge.classList.remove('focused-pulse'), 1500);
    }
  }
}

export const subagentCardRenderer = new SubagentCardRenderer();

if (typeof window !== 'undefined') {
  window.SubagentCardRenderer = SubagentCardRenderer;
  window.subagentCardRenderer = subagentCardRenderer;
}
