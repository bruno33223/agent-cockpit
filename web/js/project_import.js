/**
 * Módulo de Importação Explícita de Projetos (Issue #37)
 * Permite selecionar ou informar o caminho canônico de uma pasta física de projeto.
 */

import { apiFetch, switchProject } from './state.js';
import { escapeHtml } from './ui_utils.js';

export function openImportProjectModal() {
  const modal = document.getElementById('modal-import-project');
  const pathInput = document.getElementById('import-project-path');
  const nameInput = document.getElementById('import-project-name');
  const feedback = document.getElementById('import-project-feedback');

  if (!modal) return;
  if (pathInput) pathInput.value = '';
  if (nameInput) nameInput.value = '';
  if (feedback) {
    feedback.textContent = '';
    feedback.style.display = 'none';
  }
  modal.style.display = 'flex';
  if (pathInput) setTimeout(() => pathInput.focus(), 50);
}

export function closeImportProjectModal() {
  const modal = document.getElementById('modal-import-project');
  if (modal) modal.style.display = 'none';
}

export async function submitProjectImport() {
  const pathInput = document.getElementById('import-project-path');
  const nameInput = document.getElementById('import-project-name');
  const feedback = document.getElementById('import-project-feedback');
  const btnSubmit = document.getElementById('btn-import-project-confirm');

  const rawPath = pathInput ? pathInput.value.trim() : '';
  const rawName = nameInput ? nameInput.value.trim() : '';

  if (!rawPath) {
    showFeedback('Por favor, informe o caminho absoluto ou relativo da pasta.', true);
    return;
  }

  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.textContent = 'Importando...';
  }

  try {
    const res = await apiFetch('/api/projects/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: rawPath, name: rawName || null, switch: true })
    });

    const data = await res.json();
    if (!res.ok) {
      const errMsg = data.detail || data.message || 'Falha ao importar diretório informado.';
      showFeedback(errMsg, true);
      return;
    }

    showFeedback('Projeto importado com sucesso!', false);
    setTimeout(() => {
      closeImportProjectModal();
      if (data.current_project_id) {
        switchProject(data.current_project_id);
      }
    }, 400);
  } catch (err) {
    showFeedback(`Erro de comunicação com o servidor: ${err.message}`, true);
  } finally {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.textContent = 'Importar Projeto';
    }
  }
}

function showFeedback(text, isError) {
  const feedback = document.getElementById('import-project-feedback');
  if (!feedback) return;
  feedback.textContent = text;
  feedback.style.display = 'block';
  feedback.style.color = isError ? 'var(--color-danger, #ef4444)' : 'var(--color-success, #10b981)';
  feedback.style.background = isError ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)';
  feedback.style.padding = '8px 12px';
  feedback.style.borderRadius = '6px';
  feedback.style.fontSize = '12px';
  feedback.style.marginTop = '10px';
}

export function initProjectImport() {
  const btnTrigger = document.getElementById('btn-sidebar-import-project');
  if (btnTrigger) {
    btnTrigger.addEventListener('click', (e) => {
      e.stopPropagation();
      openImportProjectModal();
    });
  }

  const btnClose = document.getElementById('btn-close-import-modal');
  if (btnClose) btnClose.addEventListener('click', closeImportProjectModal);

  const btnCancel = document.getElementById('btn-import-project-cancel');
  if (btnCancel) btnCancel.addEventListener('click', closeImportProjectModal);

  const btnConfirm = document.getElementById('btn-import-project-confirm');
  if (btnConfirm) btnConfirm.addEventListener('click', submitProjectImport);

  const modal = document.getElementById('modal-import-project');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeImportProjectModal();
    });
  }

  const pathInput = document.getElementById('import-project-path');
  if (pathInput) {
    pathInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submitProjectImport();
    });
  }
}
