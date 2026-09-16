import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS_DIR = os.path.join(BASE_DIR, "web", "css")
STYLES_FILE = os.path.join(BASE_DIR, "web", "styles.css")
os.makedirs(CSS_DIR, exist_ok=True)

with open(STYLES_FILE, "r", encoding="utf-8") as f:
    lines = f.readlines()

def extract(start_idx, end_idx):
    return "".join(lines[start_idx-1:end_idx])

# Build files with semantic theme replacements
tokens_content = """/* ==========================================================================
   MODULE: TOKENS & THEMES
   Design tokens canônicos, variáveis reativas e temas (dark, light, classic, sepia).
   ========================================================================== */

@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root,
[data-theme="dark"] {
  color-scheme: dark;

  /* Superfícies e Fundos */
  --bg-void: #0c0e11;
  --bg-sidebar: #0c0e11;
  --bg-main: #111417;
  --bg-surface: #0c0e11;
  --bg-card: #181b20;
  --bg-card-hover: rgba(255, 255, 255, 0.05);
  --bg-card-active: #23282f;
  --bg-active: #23282f;
  --background: #0c0e11;
  --foreground: #f4f4f5;
  --card: #181b20;
  --card-foreground: #f4f4f5;
  --sidebar: #0c0e11;
  --worktree-sidebar: #0c0e11;
  --worktree-sidebar-accent: #23282f;

  /* Bordas */
  --border: #23282f;
  --border-subtle: #23282f;
  --border-strong: #272c35;
  --border-focus: #00ff66;

  /* Tipografia */
  --text-primary: #ffffff;
  --text-secondary: #a1a1aa;
  --text-muted: #71717a;
  --muted-foreground: #a1a1aa;
  --muted: #181b20;
  --accent: #23282f;

  /* Botões e Seleções Semânticas */
  --btn-secondary-bg: #181b20;
  --btn-secondary-border: #272c35;
  --btn-secondary-text: #f4f4f5;
  --btn-secondary-hover-bg: #23282f;
  --btn-active-bg: #23282f;
  --btn-active-text: #ffffff;
  --active-project-text: #00ff66;
  --active-project-dot: #00ff66;

  /* Acentos e Status */
  --primary: #2563eb;
  --status-success: #00ff66;
  --agent-question: #f97316;
  --destructive: #ff6568;
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Geist', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', monospace;

  /* Git Decorations Orca */
  --git-decoration-added: #81b88b;
  --git-decoration-modified: #e2c08d;
  --git-decoration-deleted: #c74e39;
  --git-decoration-renamed: #73c991;
  --git-decoration-untracked: #73c991;
  --git-decoration-ignored: #6e6e6e;

  /* Elevation & Radius */
  --radius: 6px;
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-xl: 12px;
  --shadow-floating: 0 10px 24px rgba(0, 0, 0, 0.5);
  --shadow-subtle: 0 2px 8px rgba(0, 0, 0, 0.3);

  /* Cores funcionais do Cockpit */
  --cyan-bright: #38bdf8;
  --cyan-dim: rgba(56, 189, 248, 0.08);
  --green-bright: #00ff66;
  --green-dim: rgba(0, 255, 102, 0.1);
  --amber-bright: #f59e0b;
  --amber-dim: rgba(245, 158, 11, 0.12);
  --red-bright: var(--destructive);
  --red-dim: rgba(255, 101, 104, 0.12);
  --purple-bright: #a855f7;
  --purple-dim: rgba(168, 85, 247, 0.12);

  /* Escala de fonte dinâmica */
  --app-font-scale: 1;
}

html {
  font-size: calc(13px * var(--app-font-scale, 1));
}

/* ── TEMA CLARO (ALTO CONTRASTE) ── */
[data-theme="light"] {
  color-scheme: light;
  --bg-void: #f8fafc;
  --bg-sidebar: #f1f5f9;
  --bg-main: #ffffff;
  --bg-surface: #f1f5f9;
  --bg-card: #ffffff;
  --bg-card-hover: #f1f5f9;
  --bg-card-active: #e2e8f0;
  --bg-active: #e2e8f0;
  --background: #f8fafc;
  --foreground: #0f172a;
  --card: #ffffff;
  --card-foreground: #0f172a;
  --sidebar: #f1f5f9;
  --worktree-sidebar: #f1f5f9;
  --worktree-sidebar-accent: #e2e8f0;

  --border: #e2e8f0;
  --border-subtle: #e2e8f0;
  --border-strong: #cbd5e1;
  --border-focus: #2563eb;

  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-muted: #64748b;
  --muted-foreground: #64748b;
  --muted: #e2e8f0;
  --accent: #e2e8f0;

  --btn-secondary-bg: #ffffff;
  --btn-secondary-border: #cbd5e1;
  --btn-secondary-text: #0f172a;
  --btn-secondary-hover-bg: #f1f5f9;
  --btn-active-bg: #e2e8f0;
  --btn-active-text: #0f172a;
  --active-project-text: #15803d;
  --active-project-dot: #16a34a;

  --primary: #2563eb;
  --status-success: #16a34a;
  --agent-question: #ea580c;
  --destructive: #dc2626;

  --cyan-bright: #0284c7;
  --cyan-dim: rgba(2, 132, 199, 0.1);
  --green-bright: #16a34a;
  --green-dim: rgba(22, 163, 74, 0.12);
  --amber-bright: #d97706;
  --amber-dim: rgba(217, 119, 6, 0.12);
  --red-bright: #dc2626;
  --red-dim: rgba(220, 38, 38, 0.12);
  --purple-bright: #9333ea;
  --purple-dim: rgba(147, 51, 234, 0.12);
}

/* ── TEMA CLÁSSICO (TERMINAL ESCURO) ── */
[data-theme="classic"] {
  color-scheme: dark;
  --bg-void: #181818;
  --bg-sidebar: #1e1e1e;
  --bg-main: #181818;
  --bg-surface: #1e1e1e;
  --bg-card: #1e1e1e;
  --bg-card-hover: #2d2d2d;
  --bg-card-active: #37373d;
  --bg-active: #37373d;
  --background: #181818;
  --foreground: #d4d4d4;
  --card: #1e1e1e;
  --card-foreground: #d4d4d4;
  --sidebar: #1e1e1e;
  --worktree-sidebar: #252526;
  --worktree-sidebar-accent: #2d2d2d;

  --border: #2d2d2d;
  --border-subtle: #252526;
  --border-strong: #3e3e42;
  --border-focus: #00ff66;

  --text-primary: #d4d4d4;
  --text-secondary: #858585;
  --text-muted: #606060;
  --muted-foreground: #858585;
  --muted: #2d2d2d;
  --accent: #37373d;

  --btn-secondary-bg: #252526;
  --btn-secondary-border: #3e3e42;
  --btn-secondary-text: #d4d4d4;
  --btn-secondary-hover-bg: #2d2d2d;
  --btn-active-bg: #37373d;
  --btn-active-text: #ffffff;
  --active-project-text: #00ff66;
  --active-project-dot: #00ff66;

  --primary: #00ff66;
  --status-success: #00ff66;
  --agent-question: #f97316;
  --destructive: #ff6568;
}

/* ── TEMA PAPEL ANTIGO (SEPIA) ── */
[data-theme="sepia"] {
  color-scheme: light;
  --bg-void: #f4ecd8;
  --bg-sidebar: #eee4cc;
  --bg-main: #faf4e8;
  --bg-surface: #eee4cc;
  --bg-card: #faf4e8;
  --bg-card-hover: #e5dac0;
  --bg-card-active: #dcd0b5;
  --bg-active: #dcd0b5;
  --background: #f4ecd8;
  --foreground: #382c1e;
  --card: #faf4e8;
  --card-foreground: #382c1e;
  --sidebar: #eee4cc;
  --worktree-sidebar: #e5dac0;
  --worktree-sidebar-accent: #dcd0b5;

  --border: rgba(90, 65, 35, 0.15);
  --border-subtle: rgba(90, 65, 35, 0.12);
  --border-strong: rgba(90, 65, 35, 0.25);
  --border-focus: #5a4123;

  --text-primary: #382c1e;
  --text-secondary: #7d6b54;
  --text-muted: #9e8c75;
  --muted-foreground: #7d6b54;
  --muted: #e5dac0;
  --accent: #dcd0b5;

  --btn-secondary-bg: #faf4e8;
  --btn-secondary-border: #dcd0b5;
  --btn-secondary-text: #382c1e;
  --btn-secondary-hover-bg: #e5dac0;
  --btn-active-bg: #dcd0b5;
  --btn-active-text: #382c1e;
  --active-project-text: #2e7d32;
  --active-project-dot: #2e7d32;

  --primary: #5a4123;
  --status-success: #2e7d32;
  --agent-question: #c2410c;
  --destructive: #b91c1c;
}
"""

base_content = """/* ==========================================================================
   MODULE: BASE & LAYOUT
   Reset universal, scrollbars, html/body e wrappers de layout.
   ========================================================================== */

/* UNIVERSAL SELECT & DARK MODE RESET */
select {
  color-scheme: inherit;
  -webkit-appearance: none;
  -moz-appearance: none;
  appearance: none;
  background-color: var(--bg-card);
  color: var(--text-primary);
}

select option {
  background-color: var(--bg-surface);
  color: var(--text-primary);
}

/* CUSTOM SLICK SCROLLBARS */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: var(--bg-void);
}
::-webkit-scrollbar-thumb {
  background: var(--border-subtle);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--border-strong);
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  background-color: var(--bg-void);
  color: var(--text-primary);
  font-family: var(--font-sans);
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  -webkit-font-smoothing: antialiased;
}

/* APP LAYOUT */
.app-layout {
  display: flex;
  width: 100vw;
  height: calc(100vh - 38px);
  flex: 1;
  overflow: hidden;
  background-color: var(--bg-void);
}

/* MAIN CONTENT WRAPPER */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  min-width: 0;
}
"""

sidebar_content = "/* ==========================================================================\n   MODULE: SIDEBAR & WORKSPACES\n   Barra lateral retrátil, navegação (.nav-tab), workspaces e worktree-cards.\n   ========================================================================== */\n\n" + extract(244, 581) + "\n\n" + extract(5321, 5618) + "\n\n" + extract(6106, 6403)

# Make sure sidebar uses semantic variables for themes
sidebar_content = sidebar_content.replace("background-color: #23282f;", "background-color: var(--bg-active);")
sidebar_content = sidebar_content.replace("border: 1px solid #23282f;", "border: 1px solid var(--border-subtle);")
sidebar_content = sidebar_content.replace("background-color: #181b20;", "background-color: var(--btn-secondary-bg);")

topbar_content = "/* ==========================================================================\n   MODULE: TOPBAR & BRANDING\n   Barra superior (.topbar, .orca-titlebar), marca ZEUS e busca rápida.\n   ========================================================================== */\n\n" + extract(592, 723) + "\n\n" + extract(5113, 5320)

buttons_content = "/* ==========================================================================\n   MODULE: BUTTONS & CONTROLS\n   Botões de ação do sistema (.action-btn), variantes e toggles.\n   ========================================================================== */\n\n" + extract(724, 879)
buttons_content = buttons_content.replace("background-color: #181b20;", "background-color: var(--btn-secondary-bg);")
buttons_content = buttons_content.replace("border-color: #272c35;", "border-color: var(--btn-secondary-border);")
buttons_content = buttons_content.replace("background-color: #23282f;", "background-color: var(--btn-secondary-hover-bg);")

views_content = "/* ==========================================================================\n   MODULE: CORE VIEWS\n   Visão Geral, Fluxo, Kanban, Code Graph, Gauntlet e Handoff.\n   ========================================================================== */\n\n" + extract(880, 1684) + "\n\n" + extract(4051, 4478) + "\n\n" + extract(6404, 6944)
views_content = views_content.replace("border-bottom: 1px solid #23282f;", "border-bottom: 1px solid var(--border-subtle);")
views_content = views_content.replace("background: #0c0e11;", "background: var(--bg-surface);")
views_content = views_content.replace("background: #23282f;", "background: var(--bg-active);")

right_sidebar_content = "/* ==========================================================================\n   MODULE: RIGHT SIDEBAR & FILE EXPLORER\n   Barra lateral direita, árvore de arquivos, Git e chat feed.\n   ========================================================================== */\n\n" + extract(1685, 2547) + "\n\n" + extract(5981, 6105)
right_sidebar_content = right_sidebar_content.replace("border-bottom: 1px solid #23282f;", "border-bottom: 1px solid var(--border-subtle);")
right_sidebar_content = right_sidebar_content.replace("background: #0c0e11;", "background: var(--bg-surface);")
right_sidebar_content = right_sidebar_content.replace("background: #23282f;", "background: var(--bg-active);")

worker_content = "/* ==========================================================================\n   MODULE: LOCAL WORKER & OLLAMA\n   Console de IA local na GPU, cards de modelos e progresso de download.\n   ========================================================================== */\n\n" + extract(2548, 4050)

terminal_content = "/* ==========================================================================\n   MODULE: TERMINAL WORKSPACE\n   Grid de terminais multi-agentes, abas (.orca-tab) e painéis split.\n   ========================================================================== */\n\n" + extract(4479, 5108) + "\n\n" + extract(5619, 5980)
terminal_content = terminal_content.replace("background-color: #23282f;", "background-color: var(--bg-active);")

modals_content = "/* ==========================================================================\n   MODULE: MODALS & DIALOGS\n   Popup de configurações Antigravity, modal Zeus e canvas virtual.\n   ========================================================================== */\n\n" + extract(6945, len(lines))
modals_content = modals_content.replace("background: #0c0e11;", "background: var(--bg-surface);")
modals_content = modals_content.replace("background: #111417;", "background: var(--bg-card);")
modals_content = modals_content.replace("background: #23282f;", "background: var(--bg-active);")
modals_content = modals_content.replace("border: 1px solid #23282f;", "border: 1px solid var(--border-subtle);")
modals_content = modals_content.replace("border-right: 1px solid #23282f;", "border-right: 1px solid var(--border-subtle);")

modules = [
    ("tokens.css", tokens_content),
    ("base.css", base_content),
    ("buttons.css", buttons_content),
    ("sidebar.css", sidebar_content),
    ("topbar.css", topbar_content),
    ("views.css", views_content),
    ("terminal.css", terminal_content),
    ("right-sidebar.css", right_sidebar_content),
    ("worker.css", worker_content),
    ("modals.css", modals_content),
]

for filename, content in modules:
    path = os.path.join(CSS_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    print(f"Created web/css/{filename} ({len(content.splitlines())} lines)")

print("Split completed successfully!")
