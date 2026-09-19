#!/usr/bin/env python3
"""Build script for Agent Cockpit CSS.

Compiles modular CSS files from `web/css/` into the consolidated `web/styles.css`.
Enforces Clean Architecture, Single Responsibility, and 100% test compatibility.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSS_DIR = os.path.join(BASE_DIR, "web", "css")
OUTPUT_FILE = os.path.join(BASE_DIR, "web", "styles.css")
CSS_OUTPUT_FILE = os.path.join(CSS_DIR, "styles.css")

MODULES = [
    "tokens.css",
    "base.css",
    "buttons.css",
    "sidebar.css",
    "topbar.css",
    "views.css",
    "terminal.css",
    "right-sidebar.css",
    "worker.css",
    "modals.css",
    "zeus_chat.css",
    "avatar_3d.css",
]

HEADER = """/* ==========================================================================
   AGENT COCKPIT / ZEUS AGENT - MASTER STYLESHEET
   Bundle compilado a partir dos módulos em `web/css/`.
   Para editar estilos, modifique os arquivos em `web/css/` e execute:
     python3 build_css.py
   ========================================================================== */
"""

def build():
    if not os.path.isdir(CSS_DIR):
        print(f"Erro: Diretório {CSS_DIR} não encontrado.", file=sys.stderr)
        sys.exit(1)

    parts = [HEADER]
    total_lines = 0

    for mod in MODULES:
        path = os.path.join(CSS_DIR, mod)
        if not os.path.isfile(path):
            print(f"Erro: Módulo {mod} não encontrado em {path}", file=sys.stderr)
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            parts.append(content)
            total_lines += len(content.splitlines())

    bundle = "\n\n".join(parts)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(bundle)
    if not (os.path.exists(CSS_OUTPUT_FILE) and os.path.samefile(OUTPUT_FILE, CSS_OUTPUT_FILE)):
        with open(CSS_OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(bundle)

    print(f"Sucesso! {len(MODULES)} módulos compilados em web/styles.css ({len(bundle.splitlines())} linhas).")

import time

def watch():
    print(f"Modo Watch ativo. Monitorando alterações em {CSS_DIR}...")
    build()
    last_mtimes = {}
    for mod in MODULES:
        p = os.path.join(CSS_DIR, mod)
        if os.path.isfile(p):
            last_mtimes[p] = os.path.getmtime(p)

    try:
        while True:
            time.sleep(1)
            changed = False
            for mod in MODULES:
                p = os.path.join(CSS_DIR, mod)
                if os.path.isfile(p):
                    m = os.path.getmtime(p)
                    if p not in last_mtimes or m > last_mtimes[p]:
                        last_mtimes[p] = m
                        changed = True
            if changed:
                print("\nDetectada alteração em arquivo CSS. Recompilando...")
                build()
    except KeyboardInterrupt:
        print("\nWatch encerrado.")

if __name__ == "__main__":
    if "--watch" in sys.argv or "-w" in sys.argv:
        watch()
    else:
        build()
