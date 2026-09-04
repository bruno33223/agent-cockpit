import os
import re
import sys
import time
import subprocess
from typing import Dict, List, Any

def run_distilled_tests(test_command: str, working_dir: str = ".", timeout_sec: int = 60) -> Dict[str, Any]:
    """Executa a suíte de testes de forma determinística e destila o resultado,

    removendo 95% do lixo de terminal e retornando apenas as falhas reais.
    """
    working_dir = os.path.abspath(working_dir)
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
            errors='ignore'
        )
        stdout, stderr = proc.communicate(timeout=timeout_sec)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        return {
            "status": "TIMEOUT",
            "duration_seconds": timeout_sec,
            "error": f"Execução de testes expirou após {timeout_sec}s."
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "duration_seconds": round(time.time() - start_time, 2),
            "error": f"Falha ao iniciar comando de teste: {str(e)}"
        }

    duration = round(time.time() - start_time, 2)
    full_output = f"{stdout}\n{stderr}".strip()

    # Identifica padrão de runner
    is_pass = exit_code == 0
    failures: List[Dict[str, Any]] = []

    if not is_pass:
        failures = parse_failures(full_output)

    # Contagem resumida
    summary = extract_summary(full_output, is_pass)

    return {
        "status": "PASS" if is_pass else "FAIL",
        "command": test_command,
        "duration_seconds": duration,
        "exit_code": exit_code,
        "summary": summary,
        "failures_count": len(failures),
        "failures": failures[:10]  # Limita às 10 primeiras falhas mais críticas
    }

def parse_failures(output: str) -> List[Dict[str, Any]]:
    """Extrai cirurgicamente falhas de C# (dotnet test/MSTest/NUnit/xUnit), Python (pytest) ou JS (Jest/Vitest)."""
    failures: List[Dict[str, Any]] = []
    lines = output.splitlines()

    # 1. dotnet test / C# (Failed ... [ErrorMessage] ... at ...)
    csharp_failed_re = re.compile(r'^\s*Failed\s+([A-Za-z0-9_\.]+)', re.IGNORECASE)
    csharp_stack_re = re.compile(r'^\s*at\s+.*?\s+in\s+(.*?):line\s+(\d+)', re.IGNORECASE)

    # 2. pytest (FAILED tests/test_x.py::test_func - AssertionError: ...)
    pytest_re = re.compile(r'FAILED\s+([^\s:]+)::([^\s\-]+)\s+-\s+(.*)')

    current_test = None
    current_file = None
    current_line = None
    current_msg = []

    for idx, line in enumerate(lines):
        # Checa pytest
        py_m = pytest_re.search(line)
        if py_m:
            failures.append({
                "test_name": py_m.group(2),
                "file": py_m.group(1),
                "line": None,
                "message": py_m.group(3).strip()
            })
            continue

        # Checa dotnet / C#
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

    # Se não capturou pelos regexes estruturados, captura as últimas linhas de erro
    if not failures:
        error_lines = [l.strip() for l in lines if any(k in l.lower() for k in ['fail', 'error', 'assert', 'exception']) and len(l.strip()) > 5]
        if error_lines:
            failures.append({
                "test_name": "GenericFailure",
                "file": None,
                "line": None,
                "message": " | ".join(error_lines[:4])[:350]
            })

    return failures

def extract_summary(output: str, is_pass: bool) -> str:
    """Extrai a linha de resumo do teste."""
    for line in reversed(output.splitlines()):
        line_clean = line.strip()
        # pytest: === 5 passed, 1 failed in 0.12s ===
        if re.search(r'\d+\s+(?:passed|failed)', line_clean, re.IGNORECASE):
            return line_clean
        # dotnet: Total tests: 12. Passed: 10. Failed: 2.
        if "Total tests:" in line_clean or "Passed:" in line_clean:
            return line_clean

    return "Todos os testes passaram." if is_pass else "Testes falharam com erros."

if __name__ == "__main__":
    # Teste local
    res = run_distilled_tests("python -c \"import sys; sys.exit(0)\"")
    print("PASS TEST:", res["status"])
    res_fail = run_distilled_tests("python -c \"raise AssertionError('Esperado 200, recebido 500')\"")
    print("FAIL TEST:", res_fail["status"], res_fail["failures"])
