/**
 * MessageRenderer - Renderizador unificado do DOM de mensagens, thinking e tools.
 * Issue #34 (Deduplicação e Arquitetura Modular do Zeus Chat)
 */

export const safeEscapeHtml = (str) => {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

export class MessageRenderer {
  createThinkingBox(content = '', isStreaming = false) {
    const box = document.createElement('details');
    box.className = 'zeus-thinking-box opencode-thinking-box zeus-step-item type-thought';
    if (isStreaming) {
      box.open = true;
      box.setAttribute('open', '');
    }
    box.innerHTML = `
      <summary class="zeus-thinking-summary zeus-step-summary">
        <span class="zeus-step-label">Thought <span class="thought-duration" style="opacity:0.75; font-weight:normal;"></span></span>
        <span class="zeus-step-chevron">›</span>
      </summary>
      <div class="zeus-thinking-content thinking-text zeus-step-body">${safeEscapeHtml(content)}</div>
    `;
    return box;
  }

  appendThinkingChunk(thinkBox, chunkText) {
    if (!thinkBox) return;
    const contentDiv = thinkBox.querySelector('.thinking-text') || thinkBox.querySelector('.zeus-thinking-content');
    if (contentDiv) contentDiv.innerHTML += safeEscapeHtml(chunkText);
    thinkBox.open = true;
  }

  formatStepTitle(tool = {}) {
    const name = (tool.name || tool.tool || 'Ação').toLowerCase();
    let cmd = tool.command || tool.detail || '';
    if (!cmd && tool.params) {
      cmd = typeof tool.params === 'string' ? tool.params : (tool.params.command || tool.params.path || tool.params.pattern || tool.params.query || tool.params.target_file || '');
    }
    if (cmd === '{}' || cmd === 'null') cmd = '';

    if (name.includes('bash') || name.includes('cmd') || name.includes('exec') || name.includes('terminal')) {
      return cmd ? `Ran ${cmd.replace(/\n/g, ' ').trim().slice(0, 67)}` : 'Ran command';
    }
    if (name.includes('grep')) return (tool.params?.pattern || cmd) ? `Grep "${tool.params?.pattern || cmd}"` : 'Searched codebase';
    if (name.includes('glob') || name.includes('find')) return cmd ? `Find ${cmd}` : 'Explored directory';
    if (name.includes('read') || name.includes('get') || name.includes('view') || name.includes('cat')) return `Read ${cmd ? cmd.split('/').pop() : 'file'}`;
    if (name.includes('write') || name.includes('edit') || name.includes('replace') || name.includes('create')) return `Edited ${cmd ? cmd.split('/').pop() : 'file'}`;
    if (name.includes('subagent') || name.includes('task')) return `Explored 1 task (${tool.role || cmd || 'specialist'})`;
    return cmd ? `${tool.tool || tool.name || 'Ação'} ${cmd.slice(0, 45)}` : `Executed ${tool.tool || tool.name || 'action'}`;
  }

  createStepElement(tool = {}) {
    const step = document.createElement('details');
    step.className = 'zeus-step-item';
    const title = this.formatStepTitle(tool);
    let cmd = tool.command || tool.detail || '';
    if (!cmd && tool.params) {
      cmd = typeof tool.params === 'string' ? tool.params : (tool.params.command || tool.params.path || tool.params.pattern || tool.params.query || '');
      if (!cmd && Object.keys(tool.params).length > 0) cmd = JSON.stringify(tool.params, null, 2);
    }
    if (cmd === '{}' || cmd === 'null') cmd = '';

    let bodyHtml = cmd ? `<div class="zeus-step-command"><code>${safeEscapeHtml(cmd)}</code></div>` : '';
    if (tool.output && typeof tool.output === 'string' && tool.output.trim().length > 0) {
      bodyHtml += `<div class="zeus-step-output"><pre><code>${safeEscapeHtml(tool.output)}</code></pre></div>`;
    }
    if (!bodyHtml) bodyHtml = `<div class="zeus-step-command"><span style="opacity:0.6;">(Ação executada com sucesso)</span></div>`;

    step.innerHTML = `
      <summary class="zeus-step-summary">
        <span class="zeus-step-label">${safeEscapeHtml(title)}</span>
        <span class="zeus-step-chevron">›</span>
      </summary>
      <div class="zeus-step-body">${bodyHtml}</div>
    `;
    return step;
  }

  createToolCard(tool = {}) {
    const step = this.createStepElement(tool);
    step.className += ' zeus-tool-card opencode-tool-card';
    const toolName = (tool.name || tool.tool || 'tool').toLowerCase();
    let badgeType = 'TOOL';
    if (toolName.includes('read') || toolName.includes('get') || toolName.includes('view') || toolName.includes('list') || toolName.includes('grep')) badgeType = 'READ';
    else if (toolName.includes('write') || toolName.includes('edit') || toolName.includes('replace') || toolName.includes('create')) badgeType = 'WRITE';
    else if (toolName.includes('bash') || toolName.includes('cmd') || toolName.includes('exec') || toolName.includes('terminal')) badgeType = 'EXEC';

    step.innerHTML += `<span class="zeus-tool-badge tool-badge" style="display:none;">${badgeType} ${toolName}</span>`;
    return step;
  }

  createLiveAssistantCard(container) {
    if (!container) return null;
    const card = document.createElement('div');
    card.className = 'zeus-msg-card zeus-msg-assistant live-streaming zeus-chat-msg role-assistant';
    card.innerHTML = `
      <div class="zeus-msg-header">
        <div class="zeus-msg-author-wrap">
          <img src="/zeus_terminal_god.svg" class="zeus-msg-god-icon" alt="Zeus" onerror="this.style.display='none'" />
          <strong class="zeus-msg-author">ZEUS Agent</strong>
        </div>
        <span class="zeus-msg-time">${new Date().toLocaleTimeString()}</span>
      </div>
      <details class="zeus-activity-group" open>
        <summary class="zeus-activity-header">
          <span class="zeus-activity-title">Worked for <span class="activity-time">0s</span></span>
          <span class="zeus-activity-chevron">▾</span>
        </summary>
        <div class="zeus-activity-steps zeus-tools-container"></div>
      </details>
      <div class="zeus-msg-body"><span class="typing-indicator" style="opacity:0.7; font-style:italic;">⚡ Processando instrução...</span></div>
    `;

    const activityGroup = card.querySelector('.zeus-activity-group');
    const activityHeader = card.querySelector('.zeus-activity-header');
    const activitySteps = card.querySelector('.zeus-activity-steps');
    const body = card.querySelector('.zeus-msg-body');

    const thinkBox = this.createThinkingBox('', true);
    thinkBox.style.display = 'none';
    activitySteps.appendChild(thinkBox);

    container.appendChild(card);
    container.scrollTop = container.scrollHeight;

    return {
      card,
      activityGroup,
      activityHeader,
      activitySteps,
      thinkBox,
      thinkContent: thinkBox.querySelector('.zeus-thinking-content') || thinkBox.querySelector('.thinking-text'),
      toolsContainer: activitySteps,
      body,
      startedContent: false,
      toolsList: [],
      startTime: Date.now()
    };
  }

  cleanPlaceholders(liveMsg) {
    if (!liveMsg) return;
    if (liveMsg.card) {
      liveMsg.card.classList.remove('live-streaming');
      const indicators = liveMsg.card.querySelectorAll('.typing-indicator, .thinking-indicator, [data-indicator="typing"]');
      indicators.forEach(el => el.remove());
    }
    if (liveMsg.body) {
      const bodyIndicators = liveMsg.body.querySelectorAll('.typing-indicator, .thinking-indicator');
      bodyIndicators.forEach(el => el.remove());
      if (liveMsg.body.innerHTML && liveMsg.body.innerHTML.includes('Processando instrução')) {
        liveMsg.body.innerHTML = liveMsg.body.innerHTML
          .replace(/<span[^>]*class="[^"]*(?:typing|thinking)-indicator[^"]*"[^>]*>.*?<\/span>/gi, '')
          .replace(/⚡ Processando instrução\.\.\./g, '')
          .trim();
      }
    }
  }

  renderCompletionMetrics(liveMsg, duration, tokens = 0, backend = 'zeus') {
    if (!liveMsg || !liveMsg.card) return;
    const div = document.createElement('div');
    div.className = 'zeus-msg-metrics';
    div.style.cssText = 'font-size: 11px; color: var(--text-muted, #71717a); margin-top: 8px; opacity: 0.85; font-family: monospace;';
    div.textContent = `⚡ Concluído em ${duration}s · ${tokens} tokens · backend: ${backend}`;
    liveMsg.card.appendChild(div);
  }

  renderMessage(msg = {}, container = null) {
    if (!container) return null;
    const { role = 'assistant', author = 'ZEUS', content = '', thinking = null, tools = [], images = [], timestamp = '', duration_seconds = null } = msg;

    const card = document.createElement('div');
    card.className = `zeus-chat-card opencode-chat-card role-${role} zeus-chat-msg`;

    const authorHtml = role === 'assistant' ? '<img src="/zeus_terminal_god.svg" class="zeus-msg-god-icon" alt="Zeus" onerror="this.style.display=\'none\'" />' : '';
    let headerHtml = `
      <div class="zeus-card-header zeus-msg-header">
        <div class="zeus-msg-author-wrap">${authorHtml}<strong class="card-author zeus-msg-author">${safeEscapeHtml(author)}</strong></div>
        <span class="card-timestamp zeus-msg-time">${safeEscapeHtml(timestamp || new Date().toLocaleTimeString())}</span>
      </div>
    `;

    const hasThinking = Boolean(thinking && thinking.trim());
    const hasTools = Array.isArray(tools) && tools.length > 0;
    let activityHtml = '';
    if (hasThinking || hasTools) {
      const count = (hasThinking ? 1 : 0) + (hasTools ? tools.length : 0);
      activityHtml = `
        <details class="zeus-activity-group" open>
          <summary class="zeus-activity-header">
            <span class="zeus-activity-title">Worked for ${duration_seconds || '12'}s (${count} ações)</span>
            <span class="zeus-activity-chevron">▾</span>
          </summary>
          <div class="zeus-activity-steps zeus-tools-container"></div>
        </details>
      `;
    }

    let imagesHtml = '';
    if (Array.isArray(images) && images.length > 0) {
      imagesHtml = `<div class="zeus-message-images-grid">${images.map(img => `<img src="${typeof img === 'string' ? img : (img.dataUrl || '')}" class="zeus-message-image-preview" alt="Anexo" />`).join('')}</div>`;
    }

    card.innerHTML = `${headerHtml}${activityHtml}${imagesHtml}<div class="zeus-msg-body zeus-card-body">${safeEscapeHtml(content).replace(/\n/g, '<br>')}</div>`;

    if (hasThinking || hasTools) {
      const steps = card.querySelector('.zeus-activity-steps');
      if (hasThinking) steps.appendChild(this.createThinkingBox(thinking, false));
      if (hasTools) tools.forEach(t => steps.appendChild(this.createToolCard(t)));
    }

    container.appendChild(card);
    container.scrollTop = container.scrollHeight;
    return card;
  }
}

export const messageRenderer = new MessageRenderer();

if (typeof window !== 'undefined') {
  window.MessageRenderer = MessageRenderer;
  window.messageRenderer = messageRenderer;
}
