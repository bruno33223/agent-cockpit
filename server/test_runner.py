import os
import re
import sys
import time
import signal
import subprocess
from typing import Dict, List, Any, Optional

def auto_detect_test_command(working_dir: str = ".") -> str:
    """Detecta automaticamente o comando de teste apropriado para a codebase."""
    working_dir = os.path.abspath(working_dir)

    # 1. C# / .NET (.sln ou .csproj)
    for root, _, files in os.walk(working_dir):
        if any(f.endswith(".sln") or f.endswith(".csproj") for f in files):
            return "dotnet test"
        # Limita busca a 2 níveis de profundidade
        if os.path.relpath(root, working_dir).count(os.sep) >= 2:
            break

    # 2. Python (pytest, unittest)
    if os.path.exists(os.path.join(working_dir, "pytest.ini")) or \
       os.path.exists(os.path.join(working_dir, "conftest.py")) or \
       os.path.exists(os.path.join(working_dir, "tests")):
        return "pytest"

    # 3. Node.js / JavaScript / TypeScript
    if os.path.exists(os.path.join(working_dir, "package.json")):
        return "npm test"

    # 4. Rust
    if os.path.exists(os.path.join(working_dir, "Cargo.toml")):
        return "cargo test"

    return "pytest"

def run_distilled_tests(
    test_command: Optional[str] = None,
    working_dir: str = ".",
    timeout_sec: int = 60,
    save_raw_log: bool = True,
    log_output_dir: Optional[str] = None,
    tdd_mode: str = "standard",  # "standard", "verify_red", "verify_green"
    slice_id: Optional[str] = None,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """Executa a suíte de testes de forma determinística e destila o resultado,
    removendo 95% do lixo de terminal e retornando apenas as falhas reais em JSON compacto.
    Suporta modos de validação TDD rigorosos do Superpowers (Iron Law TDD).
    """
    working_dir = os.path.abspath(working_dir)

    if not test_command or not test_command.strip():
        test_command = auto_detect_test_command(working_dir)

    start_time = time.time()

    try:
        proc = subprocess.Popen(
            test_command,
            shell=True,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore',
            start_new_session=True
        )
        stdout, stderr = proc.communicate(timeout=timeout_sec)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            except Exception:
                proc.kill()
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
        return {
            "status": "TIMEOUT",
            "command": test_command,
            "duration_seconds": timeout_sec,
            "error": f"Execução de testes expirou após {timeout_sec}s."
        }
    except Exception as e:
        if 'proc' in locals() and proc.poll() is None:
            if sys.platform == "win32":
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
                except Exception:
                    proc.kill()
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
        return {
            "status": "ERROR",
            "command": test_command,
            "duration_seconds": round(time.time() - start_time, 2),
            "error": f"Falha ao iniciar comando de teste: {str(e)}"
        }

    duration = round(time.time() - start_time, 2)
    full_output = f"{stdout}\n{stderr}".strip()
    is_pass = exit_code == 0
    failures: List[Dict[str, Any]] = []

    if not is_pass:
        failures = parse_failures(full_output)

    summary = extract_summary(full_output, is_pass)

    # Salva o log bruto completo em disco para auditoria humana sem gastar tokens
    raw_log_path = None
    if save_raw_log:
        try:
            target_dir = log_output_dir if log_output_dir and os.path.exists(log_output_dir) else working_dir
            raw_log_path = os.path.join(target_dir, "TEST_RAW.log")
            with open(raw_log_path, "w", encoding="utf-8") as f:
                f.write(f"=== TEST RUN: {test_command} ===\n")
                f.write(f"Data: {time.strftime('%Y-%m-%d %H:%M:%S')} | Exit Code: {exit_code}\n\n")
                f.write(full_output)
        except Exception as e:
            raw_log_path = f"Aviso salvando log: {e}"

    tdd_result = {"mode": tdd_mode, "compliant": True, "message": "Execução padrão."}
    if tdd_mode == "verify_red":
        if not is_pass and len(failures) > 0:
            tdd_result = {
                "mode": "verify_red",
                "compliant": True,
                "message": "Fase RED confirmada: O teste falhou conforme esperado antes da implementação."
            }
            if slice_id:
                try:
                    from state_store import db
                    db.set_slice_tdd_stage(slice_id, "RED_CONFIRMED", project_id=project_id)
                except Exception:
                    pass
        else:
            tdd_result = {
                "mode": "verify_red",
                "compliant": False,
                "message": "Violação da Iron Law do TDD: O teste deveria FALHAR na fase RED, mas passou ou não gerou falhas."
            }
    elif tdd_mode == "verify_green":
        if is_pass and len(failures) == 0:
            tdd_result = {
                "mode": "verify_green",
                "compliant": True,
                "message": "Fase GREEN confirmada: Todos os testes passaram limpos após a implementação."
            }
            if slice_id:
                try:
                    from state_store import db
                    db.set_slice_tdd_stage(slice_id, "GREEN_CONFIRMED", project_id=project_id)
                except Exception:
                    pass
        else:
            tdd_result = {
                "mode": "verify_green",
                "compliant": False,
                "message": f"Fase GREEN falhou: Existem {len(failures)} testes falhando. Requer depuração sistemática."
            }

    return {
        "status": "PASS" if is_pass else "FAIL",
        "command": test_command,
        "duration_seconds": duration,
        "exit_code": exit_code,
        "summary": summary,
        "failures_count": len(failures),
        "failures": failures[:10],  # Apenas as falhas essenciais
        "tdd_validation": tdd_result,
        "raw_log_file": raw_log_path
    }

def parse_failures(output: str) -> List[Dict[str, Any]]:
    """Extrai cirurgicamente falhas de C# (dotnet test/xUnit/NUnit), Python (pytest) ou JS (Jest/Vitest)."""
    failures: List[Dict[str, Any]] = []
    lines = output.splitlines()

    # 1. dotnet test / C#
    csharp_failed_re = re.compile(r'^\s*Failed\s+([A-Za-z0-9_\.]+)', re.IGNORECASE)
    csharp_stack_re = re.compile(r'^\s*at\s+.*?\s+in\s+(.*?):line\s+(\d+)', re.IGNORECASE)

    # 2. pytest
    pytest_re = re.compile(r'FAILED\s+([^\s:]+)::([^\s\-]+)\s+-\s+(.*)')

    current_test = None
    current_file = None
    current_line = None
    current_msg = []

    for idx, line in enumerate(lines):
        py_m = pytest_re.search(line)
        if py_m:
            failures.append({
                "test_name": py_m.group(2),
                "file": py_m.group(1),
                "line": None,
                "message": py_m.group(3).strip()
            })
            continue

        cs_m = csharp_failed_re.search(line)
        if cs_m:
            if current_test:
                failures.append({
                    "test_name": current_test,
                    "file": current_file,
                    "line": current_line,
                    "message": " ".join(current_msg).strip()[:300]
                })
            current_test = cs_m.group(1)
            current_file = None
            current_line = None
            current_msg = []
            continue

        if current_test:
            stack_m = csharp_stack_re.search(line)
            if stack_m:
                current_file = stack_m.group(1)
                current_line = int(stack_m.group(2))
            elif "Error Message:" in line:
                current_msg.append(line.replace("Error Message:", "").strip())
            elif "Assert." in line or "Expected:" in line or "Actual:" in line:
                current_msg.append(line.strip())

    if current_test:
        failures.append({
            "test_name": current_test,
            "file": current_file,
            "line": current_line,
            "message": " ".join(current_msg).strip()[:300]
        })

    # Fallback caso não pegue pelo formato estruturado
    if not failures:
        error_lines = [l.strip() for l in lines if any(k in l.lower() for k in ['fail', 'error', 'assert', 'exception']) and len(l.strip()) > 5]
        if error_lines:
            failures.append({
                "test_name": "ExecutionFailure",
                "file": None,
                "line": None,
                "message": " | ".join(error_lines[:4])[:350]
            })
        else:
            failures.append({
                "test_name": "ExitCodeFailure",
                "file": None,
                "line": None,
                "message": "Comando de teste finalizou com código de saída diferente de zero."
            })

    return failures

def extract_summary(output: str, is_pass: bool) -> str:
    """Extrai a linha de resumo do teste."""
    for line in reversed(output.splitlines()):
        line_clean = line.strip()
        if re.search(r'\d+\s+(?:passed|failed)', line_clean, re.IGNORECASE):
            return line_clean
        if "Total tests:" in line_clean or "Passed:" in line_clean:
            return line_clean

    return "Todos os testes passaram com sucesso." if is_pass else "Testes falharam com erros."

if __name__ == "__main__":
    res = run_distilled_tests("python -c \"import sys; sys.exit(0)\"")
    print("PASS TEST:", res["status"])
