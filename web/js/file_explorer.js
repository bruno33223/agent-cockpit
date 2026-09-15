/**
 * Módulo de Explorador de Arquivos (FileExplorerManager)
 * Árvore de arquivos com busca dinâmica, preview e integração com a barra lateral direita.
 */

import { escapeHtml } from './ui_utils.js';
import { apiFetch, currentProjectId, knownProjects } from './state.js';
import { sendTerminalCommand } from './terminal_workspace.js';

export class FileExplorerManager {
  constructor() {
    this.projectId = null;
    this.treeData = null;
    this.expandedPaths = new Set();
    this.selectedFilePath = null;
    this.filterQuery = '';
    this.activeRightTab = 'tab-right-files';
    this.debounceTimer = null;
    this.totalFileCount = 0;

    // Elementos DOM
    this.container = document.getElementById('file-explorer-container');
    this.filterInput = document.getElementById('file-filter-input');
    this.btnClearFilter = document.getElementById('btn-clear-file-filter');
    this.countBadge = document.getElementById('file-explorer-count');
    this.projectNameDisplay = document.getElementById('right-sidebar-project-name');
    this.btnRefresh = document.getElementById('btn-refresh-right-sidebar');
    this.btnCollapse = document.getElementById('btn-collapse-right-sidebar');

    // Preview Drawer Elements
    this.previewDrawer = document.getElementById('file-preview-drawer');
    this.previewName = document.getElementById('file-preview-name');
    this.previewSize = document.getElementById('file-preview-size');
    this.previewIcon = document.getElementById('file-preview-icon');
    this.previewContent = document.getElementById('file-preview-content');
    this.btnClosePreview = document.getElementById('btn-close-file-preview');
    this.btnCopyPath = document.getElementById('btn-copy-file-path');
  }

  init() {
    // 1. Alternância de abas da barra lateral direita
    document.querySelectorAll('.right-sidebar-tab').forEach(tabBtn => {
      tabBtn.addEventListener('click', () => {
        const panelId = tabBtn.getAttribute('data-panel');
        this.switchRightTab(tabBtn.id, panelId);
      });
    });

    // 2. Filtro em tempo real com debounce
    if (this.filterInput) {
      this.filterInput.addEventListener('input', (e) => {
        clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => {
          this.filterQuery = e.target.value.trim().toLowerCase();
          if (this.btnClearFilter) {
            this.btnClearFilter.style.display = this.filterQuery ? 'block' : 'none';
          }
          this.renderTree();
        }, 120);
      });
    }

    if (this.btnClearFilter) {
      this.btnClearFilter.addEventListener('click', () => {
        if (this.filterInput) this.filterInput.value = '';
        this.filterQuery = '';
        this.btnClearFilter.style.display = 'none';
        this.renderTree();
      });
    }

    // 3. Botão Refresh (⟳)
    if (this.btnRefresh) {
      this.btnRefresh.addEventListener('click', () => {
        this.btnRefresh.style.transform = 'rotate(360deg)';
        this.btnRefresh.style.transition = 'transform 0.4s ease';
        setTimeout(() => {
          if (this.btnRefresh) {
            this.btnRefresh.style.transform = 'none';
            this.btnRefresh.style.transition = 'none';
          }
        }, 400);
        this.loadFileTree(currentProjectId, true);
      });
    }

    // 4. Botão Alternar/Colapsar barra lateral
    if (this.btnCollapse) {
      this.btnCollapse.addEventListener('click', () => {
        const wrapper = document.querySelector('.workspace-wrapper');
        if (wrapper) {
          wrapper.classList.toggle('collapse-sidebar');
          const isCollapsed = wrapper.classList.contains('collapse-sidebar');
          this.btnCollapse.title = isCollapsed ? 'Expandir Barra Lateral' : 'Colapsar Barra Lateral';
          this.btnCollapse.textContent = isCollapsed ? '⇤' : '⇥';
        }
      });
    }

    // 5. Botões do Preview Drawer
    if (this.btnClosePreview) {
      this.btnClosePreview.addEventListener('click', () => {
        this.closeFilePreview();
      });
    }

    if (this.btnCopyPath) {
      this.btnCopyPath.addEventListener('click', () => {
        if (this.selectedFilePath) {
          navigator.clipboard.writeText(this.selectedFilePath).then(() => {
            const originalText = this.btnCopyPath.innerHTML;
            this.btnCopyPath.innerHTML = '✓ Copiado!';
            this.btnCopyPath.classList.add('copied');
            setTimeout(() => {
              if (this.btnCopyPath) {
                this.btnCopyPath.innerHTML = originalText;
                this.btnCopyPath.classList.remove('copied');
              }
            }, 1800);
          }).catch(err => {
            console.error('[FileExplorer] Falha ao copiar caminho:', err);
          });
        }
      });
    }

    // Adiciona a raiz como expandida
    this.expandedPaths.add('');
  }

  switchRightTab(tabId, panelId) {
    this.activeRightTab = tabId;
    document.querySelectorAll('.right-sidebar-tab').forEach(t => {
      const isSelected = t.id === tabId;
      t.classList.toggle('active', isSelected);
      t.setAttribute('aria-selected', isSelected ? 'true' : 'false');
    });

    document.querySelectorAll('.right-sidebar-panel').forEach(p => {
      p.classList.toggle('active', p.id === panelId);
    });

    // Se mudou para a aba de arquivos e não carregou ainda, carrega
    if (panelId === 'right-panel-files' && (!this.treeData || this.projectId !== currentProjectId)) {
      this.loadFileTree(currentProjectId);
    }
  }

  async loadFileTree(projectId, forceRefresh = false) {
    const targetPid = projectId || currentProjectId || 'default';
    if (!forceRefresh && this.projectId === targetPid && this.treeData) {
      this.updateProjectHeader();
      return;
    }

    this.projectId = targetPid;
    this.selectedFilePath = null;
    this.closeFilePreview();

    if (this.container) {
      this.container.innerHTML = '<div class="file-tree-loading">Carregando arquivos do projeto...</div>';
    }

    try {
      const res = await apiFetch(`/api/fs/tree?project_id=${encodeURIComponent(targetPid)}&max_depth=5`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      this.treeData = await res.json();
      this.updateProjectHeader();
      this.renderTree();
    } catch (err) {
      console.error('[FileExplorer] Erro ao carregar árvore:', err);
      if (this.container) {
        this.container.innerHTML = `<div class="file-tree-empty">Erro ao carregar árvore de arquivos.<br><small style="color:var(--text-muted)">${escapeHtml(err.message)}</small></div>`;
      }
    }
  }

  updateProjectHeader() {
    if (!this.projectNameDisplay) return;
    let name = (this.treeData && this.treeData.name) || '';
    if (!name && state && state.epic && state.epic.name) {
      name = state.epic.name;
    }
    if (!name) {
      name = currentProjectId || 'Projeto Ativo';
    }
    this.projectNameDisplay.textContent = name;
    this.projectNameDisplay.title = `${name} (${this.treeData ? this.treeData.root : ''})`;
  }

  renderTree() {
    if (!this.container || !this.treeData) return;

    const entries = this.treeData.entries || [];
    this.totalFileCount = 0;

    if (entries.length === 0) {
      this.container.innerHTML = '<div class="file-tree-empty">Nenhum arquivo encontrado neste projeto.</div>';
      if (this.countBadge) this.countBadge.textContent = '0 itens';
      return;
    }

    // Filtra e conta
    const filteredEntries = this.filterEntries(entries, this.filterQuery);

    this.container.innerHTML = '';
    const fragment = document.createDocumentFragment();

    filteredEntries.forEach(entry => {
      const nodeEl = this.createTreeNodeElement(entry, 0);
      fragment.appendChild(nodeEl);
    });

    this.container.appendChild(fragment);

    if (this.countBadge) {
      this.countBadge.textContent = `${this.totalFileCount} ${this.totalFileCount === 1 ? 'item' : 'itens'}`;
    }
  }

  filterEntries(entries, query) {
    if (!query) {
      this.countEntriesRecursive(entries);
      return entries;
    }

    const result = [];
    for (const entry of entries) {
      const matchesSelf = entry.name.toLowerCase().includes(query) || entry.path.toLowerCase().includes(query);
      if (entry.type === 'directory') {
        const matchingChildren = this.filterEntries(entry.children || [], query);
        if (matchesSelf || matchingChildren.length > 0) {
          // Auto-expande para exibir resultados no filtro
          this.expandedPaths.add(entry.path);
          result.push({
            ...entry,
            children: matchingChildren
          });
          this.totalFileCount++;
        }
      } else {
        if (matchesSelf) {
          result.push(entry);
          this.totalFileCount++;
        }
      }
    }
    return result;
  }

  countEntriesRecursive(entries) {
    for (const entry of entries) {
      this.totalFileCount++;
      if (entry.type === 'directory' && entry.children) {
        this.countEntriesRecursive(entry.children);
      }
    }
  }

  createTreeNodeElement(entry, depth = 0) {
    const isDir = entry.type === 'directory';
    const isExpanded = this.expandedPaths.has(entry.path);
    const isSelected = this.selectedFilePath === entry.path;

    const node = document.createElement('div');
    node.className = `tree-node${isExpanded ? ' expanded' : ''}`;
    node.dataset.path = entry.path;

    const row = document.createElement('div');
    row.className = `tree-row${isSelected ? ' selected' : ''}`;
    row.style.paddingLeft = `${depth * 14 + 6}px`;

    // Seta toggle para pastas
    const toggle = document.createElement('span');
    toggle.className = 'tree-toggle';
    toggle.textContent = isDir ? '›' : '';
    row.appendChild(toggle);

    // Ícone
    const icon = document.createElement('span');
    icon.className = 'tree-icon';
    if (isDir) {
      icon.className += ' ext-folder';
      icon.textContent = isExpanded ? '📂' : '📁';
    } else {
      const fileIconMeta = this.getFileIconInfo(entry.name);
      icon.className += ` ${fileIconMeta.className}`;
      icon.textContent = fileIconMeta.icon;
    }
    row.appendChild(icon);

    // Label
    const label = document.createElement('span');
    label.className = 'tree-label';
    label.textContent = entry.name;
    label.title = entry.path;
    row.appendChild(label);

    // Tamanho para arquivos
    if (!isDir && entry.size !== undefined) {
      const sizeSpan = document.createElement('span');
      sizeSpan.className = 'tree-size';
      sizeSpan.textContent = this.formatFileSize(entry.size);
      row.appendChild(sizeSpan);
    }

    // Evento de clique
    row.addEventListener('click', (e) => {
      e.stopPropagation();
      if (isDir) {
        this.toggleDirectory(entry.path, node, icon);
      } else {
        this.selectAndOpenFile(entry.path, entry.name, row);
      }
    });

    node.appendChild(row);

    // Filhos do diretório
    if (isDir && entry.children && entry.children.length > 0) {
      const childrenContainer = document.createElement('div');
      childrenContainer.className = 'tree-children';
      entry.children.forEach(child => {
        childrenContainer.appendChild(this.createTreeNodeElement(child, depth + 1));
      });
      node.appendChild(childrenContainer);
    }

    return node;
  }

  toggleDirectory(dirPath, nodeEl, iconEl) {
    if (this.expandedPaths.has(dirPath)) {
      this.expandedPaths.delete(dirPath);
      nodeEl.classList.remove('expanded');
      if (iconEl) iconEl.textContent = '📁';
    } else {
      this.expandedPaths.add(dirPath);
      nodeEl.classList.add('expanded');
      if (iconEl) iconEl.textContent = '📂';
    }
  }

  async selectAndOpenFile(filePath, fileName, rowEl) {
    document.querySelectorAll('.tree-row.selected').forEach(r => r.classList.remove('selected'));
    if (rowEl) rowEl.classList.add('selected');

    this.selectedFilePath = filePath;

    if (!this.previewDrawer) return;

    this.previewDrawer.style.display = 'flex';
    if (this.previewName) this.previewName.textContent = fileName;
    if (this.previewSize) this.previewSize.textContent = 'Carregando...';
    if (this.previewIcon) {
      const info = this.getFileIconInfo(fileName);
      this.previewIcon.textContent = info.icon;
    }
    if (this.previewContent) {
      this.previewContent.innerHTML = '<code>Carregando conteúdo...</code>';
    }

    try {
      const res = await apiFetch(`/api/fs/read?path=${encodeURIComponent(filePath)}&project_id=${encodeURIComponent(this.projectId || currentProjectId)}`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      if (this.previewSize) {
        this.previewSize.textContent = this.formatFileSize(data.size) + (data.truncated ? ' (truncado)' : '');
      }
      if (this.previewContent) {
        if (data.is_binary) {
          this.previewContent.innerHTML = `<span style="color:var(--amber-bright);">${escapeHtml(data.error || 'Arquivo binário não suportado para visualização')}</span>`;
        } else {
          this.previewContent.textContent = data.content;
        }
      }
    } catch (err) {
      if (this.previewSize) this.previewSize.textContent = 'Erro';
      if (this.previewContent) {
        this.previewContent.innerHTML = `<span style="color:var(--red-bright)">Erro ao ler arquivo: ${escapeHtml(err.message)}</span>`;
      }
    }
  }

  closeFilePreview() {
    if (this.previewDrawer) {
      this.previewDrawer.style.display = 'none';
    }
    this.selectedFilePath = null;
    document.querySelectorAll('.tree-row.selected').forEach(r => r.classList.remove('selected'));
  }

  getFileIconInfo(fileName) {
    const parts = fileName.split('.');
    const ext = parts.length > 1 ? parts.pop().toLowerCase() : '';
    switch (ext) {
      case 'js':
      case 'mjs':
      case 'cjs':
        return { icon: '📄', className: 'ext-js' };
      case 'ts':
      case 'tsx':
        return { icon: '🔷', className: 'ext-ts' };
      case 'py':
      case 'pyw':
        return { icon: '🐍', className: 'ext-py' };
      case 'html':
      case 'htm':
        return { icon: '🌐', className: 'ext-html' };
      case 'css':
      case 'scss':
      case 'sass':
      case 'less':
        return { icon: '🎨', className: 'ext-css' };
      case 'json':
      case 'json5':
        return { icon: '⚙️', className: 'ext-json' };
      case 'md':
      case 'markdown':
        return { icon: '📝', className: 'ext-md' };
      case 'sh':
      case 'bash':
      case 'zsh':
        return { icon: '💻', className: 'ext-sh' };
      case 'yml':
      case 'yaml':
        return { icon: '📋', className: 'ext-json' };
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif':
      case 'svg':
      case 'webp':
        return { icon: '🖼️', className: 'ext-file' };
      default:
        return { icon: '📄', className: 'ext-file' };
    }
  }

  formatFileSize(bytes) {
    if (bytes === undefined || bytes === null || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }
}

// Instância global

export const fileExplorerManager = new FileExplorerManager();
