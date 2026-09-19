#!/usr/bin/env python3
"""
scripts/check_architecture_guardrails.py
Governança e Guardrails Arquiteturais - KISS Threshold & Linters de Dimensionamento de Código.
Issue #36: [Architecture/Governance] Estabelecimento de Linters e Guardrails de Limite de Linhas por Arquivo.
"""

import os
import sys
import argparse
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

GLOBAL_KISS_THRESHOLD = 400

# Baseline Allowlist com tetos congelados para arquivos legados remanescentes
BASELINE_ALLOWLIST: Dict[str, int] = {
    "web/js/terminal_workspace.js": 1984,
    "server/opencode_manager.py": 1284,
    "web/js/local_worker.js": 1000,
    "web/js/slices_chat.js": 981,
    "server/mcp_server.py": 976,
    "web/js/codebase_graph.js": 783,
    "web/js/sidebar.js": 703,
    "server/pty_manager.py": 506,
    "server/code_graph.py": 487,
    "web/js/file_explorer.js": 462,
    "server/customizations_manager.py": 456,
    "server/workers/worker_queue.py": 442,
}

# Regras específicas para módulos refatorados nas Issues #31 a #35
PACKAGE_RULES: Dict[str, dict] = {
    "server/chat": {"max_lines": 250, "ext": ".py", "description": "Issue #31: Chat Engine Modularization"},
    "server/routers": {"max_lines": 300, "ext": ".py", "description": "Issue #32: Web Server Decomposition (Routers)"},
    "server/web_server.py": {"max_lines": 199, "is_file": True, "description": "Issue #32: Web Server Facade (< 200 linhas)"},
    "server/storage": {"max_lines": 300, "ext": ".py", "description": "Issue #33: Storage Repositories & Facade"},
    "server/tools/local_builder": {"max_lines": 300, "ext": ".py", "description": "Issue #33: Local Builder Services"},
    "web/js/chat": {"max_lines": 250, "ext": ".js", "description": "Issue #34: Frontend Chat Modularization"},
    "web/js/settings": {"max_lines": 350, "ext": ".js", "description": "Issue #35: Frontend Settings Modularization"},
}


@dataclass
class FileMetrics:
    file_path: str
    total_lines: int
    sloc: int
    comment_lines: int
    blank_lines: int
    zone: str


@dataclass
class ArchitectureViolation:
    file_path: str
    current_lines: int
    max_allowed: int
    rule_name: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule_name}] {self.file_path}: {self.message} ({self.current_lines} > {self.max_allowed})"


def classify_zone(total_lines: int) -> str:
    """Classifica o arquivo nas zonas KISS / SOLID."""
    if total_lines <= 250:
        return "VERDE (Ideal: 100-250)"
    elif total_lines <= 350:
        return "AMARELA (Atenção: 250-350)"
    elif total_lines <= 400:
        return "LIMITE (Tolerável: 350-400)"
    else:
        return "VERMELHA (Monolito: > 400)"


def count_file_metrics(filepath: str) -> FileMetrics:
    """Calcula total_lines, sloc, comments e blank_lines para arquivos Python e JS."""
    total_lines = 0
    blank_lines = 0
    comment_lines = 0
    sloc = 0
    is_js = filepath.endswith(".js")
    in_block_comment = False

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                total_lines += 1
                line = raw_line.strip()
                if not line:
                    blank_lines += 1
                    continue

                if is_js:
                    if in_block_comment:
                        comment_lines += 1
                        if "*/" in line:
                            in_block_comment = False
                        continue
                    if line.startswith("/*"):
                        comment_lines += 1
                        if "*/" not in line:
                            in_block_comment = True
                        continue
                    if line.startswith("//"):
                        comment_lines += 1
                        continue
                else:  # Python
                    if line.startswith("#"):
                        comment_lines += 1
                        continue

                sloc += 1
    except Exception:
        pass

    return FileMetrics(
        file_path=filepath,
        total_lines=total_lines,
        sloc=sloc,
        comment_lines=comment_lines,
        blank_lines=blank_lines,
        zone=classify_zone(total_lines),
    )


def collect_monitored_files(base_dir: str) -> List[str]:
    """Coleta todos os arquivos sob server/**/*.py e web/js/**/*.js."""
    target_files = []
    scan_configs = [
        (os.path.join(base_dir, "server"), ".py"),
        (os.path.join(base_dir, "web", "js"), ".js"),
    ]
    ignored_dirs = {"__pycache__", ".git", ".worktrees", "scratch", "node_modules"}

    for dir_path, ext in scan_configs:
        if not os.path.exists(dir_path):
            continue
        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for file in files:
                if file.endswith(ext):
                    target_files.append(os.path.join(root, file))

    target_files.sort()
    return target_files


def validate_architecture_guardrails(
    target_paths: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
    allowlist: Optional[Dict[str, int]] = None,
    package_rules: Optional[Dict[str, dict]] = None,
    global_max: int = GLOBAL_KISS_THRESHOLD,
) -> List[ArchitectureViolation]:
    """Valida guardrails de limite de linhas contra teto global, pacotes e allowlist."""
    if base_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if allowlist is None:
        allowlist = BASELINE_ALLOWLIST
    if package_rules is None:
        package_rules = PACKAGE_RULES

    if target_paths is None:
        target_paths = collect_monitored_files(base_dir)

    violations: List[ArchitectureViolation] = []

    for path in target_paths:
        rel_path = os.path.relpath(path, base_dir).replace("\\", "/")
        metrics = count_file_metrics(path)
        lines = metrics.total_lines

        # 1. Checagem de Regras Específicas por Pacote
        matched_pkg_rule = None
        for pkg_key, rule in package_rules.items():
            is_file = rule.get("is_file", False)
            if is_file and rel_path == pkg_key:
                matched_pkg_rule = (pkg_key, rule)
                break
            elif not is_file and (rel_path.startswith(pkg_key + "/") or rel_path == pkg_key):
                if path.endswith(rule.get("ext", "")):
                    matched_pkg_rule = (pkg_key, rule)
                    break

        if matched_pkg_rule:
            pkg_key, rule = matched_pkg_rule
            pkg_max = rule["max_lines"]
            if lines > pkg_max:
                violations.append(ArchitectureViolation(
                    file_path=rel_path,
                    current_lines=lines,
                    max_allowed=pkg_max,
                    rule_name=f"PACKAGE_LIMIT:{pkg_key}",
                    message=f"Arquivo excede limite específico do pacote ({rule.get('description', '')})",
                ))
            continue

        # 2. Checagem de Allowlist (Baseline com tetos congelados)
        if rel_path in allowlist:
            ceiling = allowlist[rel_path]
            if lines > ceiling:
                violations.append(ArchitectureViolation(
                    file_path=rel_path,
                    current_lines=lines,
                    max_allowed=ceiling,
                    rule_name="ALLOWLIST_CEILING_GROWTH",
                    message=f"Arquivo legado excedeu teto congelado da allowlist",
                ))
            continue

        # 3. Checagem Global (KISS Threshold)
        if lines > global_max:
            violations.append(ArchitectureViolation(
                file_path=rel_path,
                current_lines=lines,
                max_allowed=global_max,
                rule_name="GLOBAL_KISS_THRESHOLD",
                message=f"Arquivo monolítico excede o teto máximo tolerável de {global_max} linhas fora da allowlist",
            ))

    return violations


def print_report(base_dir: str, as_json: bool = False, verbose: bool = False) -> int:
    """Executa a verificação completa e imprime o relatório."""
    files = collect_monitored_files(base_dir)
    violations = validate_architecture_guardrails(base_dir=base_dir)

    metrics_list = [count_file_metrics(f) for f in files]
    total_files = len(files)
    total_loc = sum(m.total_lines for m in metrics_list)
    total_sloc = sum(m.sloc for m in metrics_list)

    if as_json:
        data = {
            "summary": {
                "total_files": total_files,
                "total_loc": total_loc,
                "total_sloc": total_sloc,
                "violations_count": len(violations),
                "status": "PASS" if not violations else "FAIL",
            },
            "violations": [
                {
                    "file": v.file_path,
                    "lines": v.current_lines,
                    "max_allowed": v.max_allowed,
                    "rule": v.rule_name,
                    "message": v.message,
                }
                for v in violations
            ],
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 1 if violations else 0

    print("=" * 80)
    print("🛡️  GUARDRAILS DE ARQUITETURA E GOVERNANÇA (KISS THRESHOLD) - AGENT COCKPIT")
    print("=" * 80)
    print(f"Total de Arquivos Monitorados: {total_files}")
    print(f"Total de Linhas (LOC): {total_loc} | Linhas Efetivas de Código (SLOC): {total_sloc}")
    print(f"Teto Máximo Tolerável (KISS): {GLOBAL_KISS_THRESHOLD} linhas")
    print(f"Arquivos na Baseline Allowlist: {len(BASELINE_ALLOWLIST)}")
    print("-" * 80)

    if verbose:
        print(f"{'Arquivo':<45} | {'LOC':>5} | {'SLOC':>5} | {'Zona':<20}")
        print("-" * 80)
        for m in sorted(metrics_list, key=lambda x: x.total_lines, reverse=True):
            rel = os.path.relpath(m.file_path, base_dir).replace("\\", "/")
            print(f"{rel:<45} | {m.total_lines:>5} | {m.sloc:>5} | {m.zone:<20}")
        print("-" * 80)

    if violations:
        print(f"❌ FORAM ENCONTRADAS {len(violations)} VIOLAÇÕES ARQUITETURAIS:")
        for v in violations:
            print(f"  • {v}")
        print("=" * 80)
        return 1
    else:
        print("✅ 100% CONFORME! Todos os arquivos respeitam os limites arquiteturais estabelecidos.")
        print("=" * 80)
        return 0


def main():
    parser = argparse.ArgumentParser(description="Verificador de Guardrails Arquiteturais (KISS Threshold).")
    parser.add_argument("--base-dir", default=None, help="Diretório raiz do projeto.")
    parser.add_argument("--summary", action="store_true", help="Exibe sumário de conformidade.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Exibe lista detalhada de arquivos e zonas.")
    parser.add_argument("--json", action="store_true", help="Saída em formato JSON.")
    args = parser.parse_args()

    base_dir = args.base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exit_code = print_report(base_dir=base_dir, as_json=args.json, verbose=args.verbose or args.summary)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
