import unittest
import asyncio
import inspect
import sys
import os
import time
from unittest.mock import patch, MagicMock

# Ajusta path para importar módulos de server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'server')))

import mcp_server


class TestIssue22MCPNonblocking(unittest.TestCase):

    def test_01_handle_call_tool_exists_and_is_coroutine(self):
        """Verifica se handle_call_tool existe e é uma função assíncrona (corrotina)."""
        self.assertTrue(
            hasattr(mcp_server, "handle_call_tool"),
            "mcp_server deve definir a função assíncrona 'handle_call_tool'"
        )
        self.assertTrue(
            inspect.iscoroutinefunction(mcp_server.handle_call_tool),
            "handle_call_tool deve ser uma corrotina (async def)"
        )

    def test_02_run_project_tests_delegates_to_worker_thread(self):
        """Verifica se run_project_tests é despachado via asyncio.to_thread para não bloquear o loop."""
        async def run_test():
            with patch("asyncio.to_thread", wraps=asyncio.to_thread) as spy_to_thread, \
                 patch("test_runner.run_distilled_tests") as mock_runner:
                mock_runner.return_value = {"status": "SUCCESS", "exit_code": 0}

                args = {
                    "test_command": "echo test",
                    "working_dir": ".",
                    "tdd_mode": "verify_red",
                    "slice_id": "slice-2"
                }
                res = await mcp_server.handle_call_tool("run_project_tests", args)
                self.assertIn("content", res)
                self.assertTrue(spy_to_thread.called, "run_project_tests deve chamar asyncio.to_thread")

        asyncio.run(run_test())

    def test_03_execute_local_builder_delegates_to_worker_thread(self):
        """Verifica se execute_local_builder é despachado via asyncio.to_thread para não bloquear o loop."""
        async def run_test():
            with patch("asyncio.to_thread", wraps=asyncio.to_thread) as spy_to_thread, \
                 patch("tools.local_builder_tool.execute_local_builder") as mock_builder:
                mock_builder.return_value = {"status": "SUCCESS", "patch": "diff"}

                args = {
                    "slice_id": "slice-2",
                    "instruction": "Fix non-blocking MCP",
                    "target_file": "server/mcp_server.py"
                }
                res = await mcp_server.handle_call_tool("execute_local_builder", args)
                self.assertIn("content", res)
                self.assertTrue(spy_to_thread.called, "execute_local_builder deve chamar asyncio.to_thread")

        asyncio.run(run_test())

    def test_04_heavy_tools_do_not_block_concurrent_event_loop_tasks(self):
        """Verifica se uma tool pesada permite que outras tarefas no loop assíncrono progridam concorrentemente."""
        async def run_test():
            execution_order = []

            def slow_blocking_builder(**kwargs):
                time.sleep(0.15)
                execution_order.append("slow_tool_finished")
                return {"status": "SUCCESS"}

            async def fast_concurrent_task():
                await asyncio.sleep(0.02)
                execution_order.append("fast_task_finished")
                return "fast_done"

            with patch("tools.local_builder_tool.execute_local_builder", side_effect=slow_blocking_builder):
                heavy_task = asyncio.create_task(
                    mcp_server.handle_call_tool("execute_local_builder", {
                        "slice_id": "slice-2",
                        "instruction": "slow task",
                        "target_file": "dummy.py"
                    })
                )
                fast_task = asyncio.create_task(fast_concurrent_task())

                await asyncio.gather(heavy_task, fast_task)

            self.assertEqual(
                execution_order,
                ["fast_task_finished", "slow_tool_finished"],
                "A tarefa rápida concorrente deve finalizar antes da ferramenta bloqueante, provando que o event loop não foi congelado"
            )

        asyncio.run(run_test())

    def test_05_legacy_handle_tool_call_compatibility(self):
        """Verifica se a interface síncrona legada handle_tool_call continua funcionando perfeitamente."""
        self.assertTrue(hasattr(mcp_server, "handle_tool_call"))
        with patch("tools.local_builder_tool.execute_local_builder") as mock_builder:
            mock_builder.return_value = {"status": "SUCCESS", "patch": "diff"}
            res = mcp_server.handle_tool_call("execute_local_builder", {
                "slice_id": "slice-2",
                "instruction": "sync call",
                "target_file": "dummy.py"
            })
            self.assertIn("content", res)


if __name__ == "__main__":
    unittest.main()
