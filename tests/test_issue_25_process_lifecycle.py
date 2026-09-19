import os
import sys
import time
import signal
import subprocess
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from server.process_lifecycle import (
    ProcessLifecycleManager,
    get_process_lifecycle_manager,
    terminate_process_tree,
    scan_and_cleanup_orphans,
    is_orphan_cockpit_process
)
from server.pty_manager import PTYSessionManager
import run_cockpit


class TestIssue25ProcessLifecycle(unittest.TestCase):
    def setUp(self):
        self.lifecycle_manager = ProcessLifecycleManager()
        self.spawned_pids = []

    def tearDown(self):
        # Limpeza defensiva de qualquer processo residual de teste
        for pid in self.spawned_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        self.lifecycle_manager.shutdown(timeout=1.0)

    def _is_pid_alive(self, pid: int) -> bool:
        """Verifica se um PID ainda está vivo no sistema operacional."""
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, OSError):
            return False

    def test_lifecycle_manager_register_and_unregister(self):
        """Gerenciador deve registrar e desregistrar subprocessos e instâncias MCP."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        self.spawned_pids.append(proc.pid)

        self.lifecycle_manager.register_process(proc.pid, name="test_worker")
        self.assertIn(proc.pid, self.lifecycle_manager.registered_pids)

        self.lifecycle_manager.register_mcp_instance(proc.pid, server_name="agent-cockpit")
        self.assertIn(proc.pid, self.lifecycle_manager.registered_mcps)

        # Desregistro manual
        self.lifecycle_manager.unregister_process(proc.pid)
        self.assertNotIn(proc.pid, self.lifecycle_manager.registered_pids)
        self.assertNotIn(proc.pid, self.lifecycle_manager.registered_mcps)

    def test_terminate_process_tree_cascading(self):
        """Deve encerrar em cascata árvore de processos (pai e filhos), sem deixar zumbis."""
        # Cria um script filho que spawna um neto
        child_script = (
            "import subprocess, sys, time\n"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "print(p.pid, flush=True)\n"
            "time.sleep(30)\n"
        )
        parent_proc = subprocess.Popen(
            [sys.executable, "-c", child_script],
            stdout=subprocess.PIPE,
            text=True
        )
        self.spawned_pids.append(parent_proc.pid)

        # Lê o PID do processo neto
        grandchild_pid_line = parent_proc.stdout.readline().strip()
        self.assertTrue(grandchild_pid_line.isdigit(), "Deve obter PID do processo neto")
        grandchild_pid = int(grandchild_pid_line)
        self.spawned_pids.append(grandchild_pid)

        self.assertTrue(self._is_pid_alive(parent_proc.pid))
        self.assertTrue(self._is_pid_alive(grandchild_pid))

        # Encerramento em cascata a partir do pai
        terminated = terminate_process_tree(parent_proc.pid, timeout=2.0)
        self.assertIn(parent_proc.pid, terminated)

        time.sleep(0.2)
        self.assertFalse(self._is_pid_alive(parent_proc.pid), "Processo pai deve ter sido encerrado")
        self.assertFalse(self._is_pid_alive(grandchild_pid), "Processo neto deve ter sido encerrado em cascata")

    def test_mcp_and_pty_processes_do_not_survive_shutdown(self):
        """Nenhum subprocesso MCP stdio ou PTY deve sobreviver ao hook de shutdown do servidor."""
        # 1. Spawna um processo simulando mcp_server.py
        mcp_proc = subprocess.Popen(
            [sys.executable, os.path.join(SERVER_DIR, "mcp_server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        self.spawned_pids.append(mcp_proc.pid)
        self.lifecycle_manager.register_mcp_instance(mcp_proc.pid, server_name="mcp_test")

        # 2. Spawna uma sessão PTY real
        pty_mgr = PTYSessionManager()
        pty_session = pty_mgr.get_or_create(session_id="term_shutdown_test", cwd=BASE_DIR)
        if not pty_session.is_spawned:
            pty_session.spawn()
        self.assertIsNotNone(pty_session.pid)
        pty_pid = pty_session.pid
        self.spawned_pids.append(pty_pid)
        self.lifecycle_manager.register_process(pty_pid, name="pty_shutdown_test")

        self.assertTrue(self._is_pid_alive(mcp_proc.pid), "MCP deve estar vivo antes do shutdown")
        self.assertTrue(self._is_pid_alive(pty_pid), "PTY deve estar vivo antes do shutdown")

        # 3. Executa o shutdown completo do lifecycle manager
        pty_mgr.stop_all()
        self.lifecycle_manager.shutdown(timeout=2.0)

        time.sleep(0.3)
        self.assertFalse(self._is_pid_alive(mcp_proc.pid), "Processo MCP stdio NÃO deve sobreviver ao shutdown")
        self.assertFalse(self._is_pid_alive(pty_pid), "Processo PTY NÃO deve sobreviver ao shutdown")

    def test_stubborn_process_killed_with_sigkill_fallback(self):
        """Processos que ignoram SIGTERM devem ser finalizados forçadamente via fallback SIGKILL."""
        # Script que ignora SIGTERM
        stubborn_code = (
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "while True:\n"
            "    time.sleep(0.5)\n"
        )
        proc = subprocess.Popen([sys.executable, "-c", stubborn_code])
        self.spawned_pids.append(proc.pid)

        self.assertTrue(self._is_pid_alive(proc.pid))
        terminated = terminate_process_tree(proc.pid, timeout=0.8)

        self.assertIn(proc.pid, terminated)
        time.sleep(0.2)
        self.assertFalse(self._is_pid_alive(proc.pid), "Processo stubborn deve ser morto com SIGKILL após timeout")

    def test_orphan_process_scanner_and_cleanup(self):
        """Varredura de boot deve identificar e limpar processos órfãos com assinatura Cockpit."""
        # Simula processo com assinatura do Cockpit
        orphan_cmd = f"cockpit_dummy_test_orphan_{time.time()}"
        code = f"import time\n# {orphan_cmd}\ntime.sleep(30)\n"
        proc = subprocess.Popen([sys.executable, "-c", code])
        self.spawned_pids.append(proc.pid)

        # Deve reconhecer assinatura Cockpit personalizada ou de mcp_server
        self.assertTrue(is_orphan_cockpit_process(proc.pid, custom_keywords=[orphan_cmd]))

        # Limpeza de órfãos
        cleaned = scan_and_cleanup_orphans(custom_keywords=[orphan_cmd], timeout=1.5)
        self.assertIn(proc.pid, cleaned)

        time.sleep(0.2)
        self.assertFalse(self._is_pid_alive(proc.pid), "Processo órfão deve ter sido limpo na varredura")

    def test_run_cockpit_boot_cleans_orphans(self):
        """run_cockpit.py deve ter função de varredura no boot eliminando processos zumbis."""
        self.assertTrue(
            hasattr(run_cockpit, "cleanup_orphan_cockpit_processes") or hasattr(run_cockpit, "clean_orphan_processes"),
            "run_cockpit deve expor função de limpeza de processos órfãos no boot"
        )


if __name__ == "__main__":
    unittest.main()
