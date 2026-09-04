import os
import re
import json
import time
import hashlib
from typing import Dict, List, Any, Optional

def compute_criteria_hash(criteria_str: str) -> str:
    """Gera um hash SHA-256 dos critérios para lock determinístico."""
    clean = re.sub(r"\s+", " ", (criteria_str or "").strip())
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]

def create_blueprint_lock(
    blueprint_dir: str,
    epic_name: str,
    goal: str,
    slices: List[Dict[str, Any]]
) -> str:
    """Gera o arquivo blueprint.lock.json declarativo e determinístico."""
    os.makedirs(blueprint_dir, exist_ok=True)
    lock_path = os.path.join(blueprint_dir, "blueprint.lock.json")

    lock_slices = []
    for s in slices:
        raw_crit = s.get("acceptance_criteria", "")
        lock_slices.append({
            "id": s.get("id"),
            "title": s.get("title"),
            "criteria_hash": compute_criteria_hash(raw_crit),
            "max_attempts": s.get("max_attempts", 5),
            "target_files": s.get("target_files", [])
        })

    data = {
        "schema_version": "2.0",
        "epic_name": epic_name,
        "goal": goal,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "slices": lock_slices,
        "human_gates": {
            "gate_plan_approved": True,
            "gate_ship_approved": False
        }
    }

    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return lock_path

def write_handoff_document(
    blueprint_dir: str,
    epic_name: str,
    summary: str,
    files_touched: List[str],
    tests_passed: bool,
    test_details: Optional[Dict[str, Any]] = None,
    remaining_risks: Optional[List[str]] = None,
    next_steps: Optional[str] = None
) -> str:
    """Gera o HANDOFF.md padronizado no formato Maestro."""
    os.makedirs(blueprint_dir, exist_ok=True)
    handoff_path = os.path.join(blueprint_dir, "HANDOFF.md")

    lines = []
    lines.append(f"# HANDOFF: {epic_name}")
    lines.append(f"**Data:** {time.strftime('%Y-%m-%d %H:%M:%S')} | **Status Testes:** {'PASSOU' if tests_passed else 'FALHOU'}\n")
    lines.append("## 1. Resumo da Entrega")
    lines.append(summary.strip() if summary else "Entrega concluída pelo Orquestrador.")
    lines.append("\n## 2. Arquivos Modificados / Criados")
    if files_touched:
        for f in files_touched:
            lines.append(f"- `{f}`")
    else:
        lines.append("- Nenhum arquivo específico reportado.")

    lines.append("\n## 3. Evidência de Verificação & Testes")
    if test_details:
        lines.append(f"- **Comando:** `{test_details.get('command', 'test_runner')}`")
        lines.append(f"- **Total de Testes:** {test_details.get('total_tests', 0)}")
        lines.append(f"- **Falhas:** {test_details.get('failed', 0)}")
    else:
        lines.append(f"- Testes unitários e de integração: {'Aprovados sem regressão' if tests_passed else 'Falhas detectadas'}.")

    lines.append("\n## 4. Riscos Remanescentes & Notas de Domínio")
    if remaining_risks:
        for r in remaining_risks:
            lines.append(f"- {r}")
    else:
        lines.append("- Nenhum risco crítico remanescente identificado.")

    lines.append("\n## 5. Próximo Passo para a Próxima Sessão")
    lines.append(next_steps.strip() if next_steps else "Pronto para deploy ou início da próxima blueprint numerada.")

    content = "\n".join(lines) + "\n"
    with open(handoff_path, "w", encoding="utf-8") as f:
        f.write(content)

    return handoff_path

def find_latest_blueprint_dir(base_dir: str = ".") -> Optional[str]:
    """Encontra a pasta de blueprint numerada mais recente (ex: 02_..., 01_...)."""
    try:
        dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d)) and re.match(r"^\d\d_", d)]
        if not dirs:
            return None
        dirs.sort(reverse=True)
        return os.path.abspath(os.path.join(base_dir, dirs[0]))
    except Exception:
        return None

def read_latest_handoff(base_dir: str = ".") -> Optional[Dict[str, Any]]:
    """Lê o último HANDOFF.md disponível no repositório."""
    latest_dir = find_latest_blueprint_dir(base_dir)
    if not latest_dir:
        return None

    handoff_path = os.path.join(latest_dir, "HANDOFF.md")
    if not os.path.exists(handoff_path):
        return None

    try:
        with open(handoff_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {
            "blueprint_dir": os.path.basename(latest_dir),
            "handoff_path": handoff_path,
            "content": content
        }
    except Exception as e:
        return {"error": str(e)}
