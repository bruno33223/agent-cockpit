"""
tests/test_issue_31_chat_engine_modularization.py
Validação da modularização arquitetural do Zeus Chat Engine (Issue #31).

Cobre:
1. Decomposição física no pacote server/chat/ e server/chat/providers/.
2. Limite rígido de linhas por arquivo (<= 250 linhas).
3. Retrocompatibilidade total de importações com server.zeus_chat_engine e zeus_chat_engine.
4. Validação funcional desacoplada de cada componente (SessionManager, AudioTranscriber,
   providers de stream, ZeusChatEngine).
"""

import io
import os
import sys
import json
import time
import wave
import struct
import unittest
from unittest.mock import patch, MagicMock

# Assegura que o diretório raiz e o server estejam no sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestChatEngineArchitectureDecomposition(unittest.TestCase):
    """Verifica a decomposição física e limites de linhas conforme Issue #31."""

    REQUIRED_FILES = [
        os.path.join("server", "chat", "__init__.py"),
        os.path.join("server", "chat", "session_manager.py"),
        os.path.join("server", "chat", "audio_transcriber.py"),
        os.path.join("server", "chat", "providers", "__init__.py"),
        os.path.join("server", "chat", "providers", "opencode_stream.py"),
        os.path.join("server", "chat", "providers", "omniroute_stream.py"),
        os.path.join("server", "chat", "providers", "ollama_stream.py"),
        os.path.join("server", "chat", "zeus_engine.py"),
        os.path.join("server", "zeus_chat_engine.py"),
    ]

    def test_all_modular_files_exist(self):
        """Todos os arquivos propostos na Issue #31 devem existir fisicamente no disco."""
        missing = []
        for rel_path in self.REQUIRED_FILES:
            full_path = os.path.join(BASE_DIR, rel_path)
            if not os.path.exists(full_path):
                missing.append(rel_path)
        self.assertEqual(missing, [], f"Arquivos modulares ausentes: {missing}")

    def test_all_chat_modules_within_line_limit(self):
        """Nenhum arquivo no pacote server/chat/ ou server/zeus_chat_engine.py pode exceder 250 linhas."""
        oversized = {}
        chat_dir = os.path.join(SERVER_DIR, "chat")

        files_to_check = []
        if os.path.exists(chat_dir):
            for root, _, files in os.walk(chat_dir):
                for f in files:
                    if f.endswith(".py"):
                        files_to_check.append(os.path.join(root, f))

        zeus_legacy = os.path.join(SERVER_DIR, "zeus_chat_engine.py")
        if os.path.exists(zeus_legacy):
            files_to_check.append(zeus_legacy)

        for path in files_to_check:
            with open(path, "r", encoding="utf-8") as fp:
                lines = fp.readlines()
                line_count = len(lines)
                if line_count > 250:
                    rel_p = os.path.relpath(path, BASE_DIR)
                    oversized[rel_p] = line_count

        self.assertEqual(
            oversized,
            {},
            f"Arquivos excederam o limite de 250 linhas: {oversized}"
        )


class TestChatEngineBackwardCompatibility(unittest.TestCase):
    """Garante 100% de retrocompatibilidade com importações de zeus_chat_engine e server.zeus_chat_engine."""

    def test_import_from_server_zeus_chat_engine(self):
        """Importação completa a partir do módulo qualificado 'server.zeus_chat_engine'."""
        try:
            from server.zeus_chat_engine import (
                ZeusChatEngine,
                zeus_engine,
                SessionManager,
                AudioTranscriber,
                InMemorySTTEngine,
                PromptOptimizer,
                DEFAULT_ZEUS_SYSTEM_PROMPT,
                AVAILABLE_TOOLS,
                ZEUS_TOOLS,
                is_vision_model,
                validate_image_payload,
            )
        except ImportError as e:
            self.fail(f"Falha ao importar de server.zeus_chat_engine: {e}")

        self.assertIsNotNone(ZeusChatEngine)
        self.assertIsNotNone(zeus_engine)
        self.assertIsNotNone(SessionManager)
        self.assertIsNotNone(AudioTranscriber)
        self.assertIsNotNone(InMemorySTTEngine)
        self.assertIsNotNone(PromptOptimizer)
        self.assertIsInstance(DEFAULT_ZEUS_SYSTEM_PROMPT, str)
        self.assertIsInstance(AVAILABLE_TOOLS, list)
        self.assertIsInstance(ZEUS_TOOLS, list)
        self.assertTrue(callable(is_vision_model))
        self.assertTrue(callable(validate_image_payload))

    def test_import_from_unqualified_zeus_chat_engine(self):
        """Importação direta a partir de 'zeus_chat_engine' (quando server/ está no sys.path)."""
        try:
            import zeus_chat_engine
            from zeus_chat_engine import (
                ZeusChatEngine,
                zeus_engine,
                SessionManager,
                AudioTranscriber,
                InMemorySTTEngine,
            )
        except ImportError as e:
            self.fail(f"Falha ao importar de zeus_chat_engine: {e}")

        self.assertTrue(hasattr(zeus_chat_engine, "ZeusChatEngine"))
        self.assertTrue(hasattr(zeus_chat_engine, "SessionManager"))
        self.assertTrue(hasattr(zeus_chat_engine, "AudioTranscriber"))
        self.assertTrue(hasattr(zeus_chat_engine, "InMemorySTTEngine"))
        self.assertTrue(hasattr(zeus_chat_engine, "zeus_engine"))

    def test_import_from_new_chat_package(self):
        """Importação a partir do novo pacote 'server.chat'."""
        try:
            from server.chat import (
                ZeusChatEngine,
                zeus_engine,
                SessionManager,
                AudioTranscriber,
                InMemorySTTEngine,
                ChatMessage,
            )
        except ImportError as e:
            self.fail(f"Falha ao importar do novo pacote server.chat: {e}")

        self.assertIsNotNone(ZeusChatEngine)
        self.assertIsNotNone(SessionManager)
        self.assertIsNotNone(AudioTranscriber)
        self.assertIsNotNone(ChatMessage)


class TestSessionManagerComponent(unittest.TestCase):
    """Testes unitários e thread-safety do componente SessionManager desacoplado."""

    def setUp(self):
        from server.chat.session_manager import SessionManager, ChatMessage
        self.SessionManager = SessionManager
        self.ChatMessage = ChatMessage
        self.manager = SessionManager()

    def test_session_lifecycle(self):
        s_id = "test-session-123"
        session = self.manager.get_or_create_session(s_id)
        self.assertEqual(session["session_id"], s_id)
        self.assertEqual(session["messages"], [])

        msg = self.manager.append_message(
            session_id=s_id,
            role="user",
            content="Olá Zeus",
            thinking="Processando...",
            tool_calls=[{"tool": "bash", "command": "ls"}],
            subagents=[{"slice_id": "slice-1", "role": "builder"}]
        )
        self.assertIn("id", msg)
        self.assertEqual(msg["role"], "user")
        self.assertEqual(msg["content"], "Olá Zeus")
        self.assertEqual(msg["thinking"], "Processando...")

        history = self.manager.get_history(s_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["content"], "Olá Zeus")

        cleared = self.manager.clear_session(s_id)
        self.assertTrue(cleared)
        self.assertEqual(self.manager.get_history(s_id), [])

        deleted = self.manager.delete_session(s_id)
        self.assertTrue(deleted)
        self.assertNotIn(s_id, self.manager.list_sessions())

    def test_thread_safe_concurrent_access(self):
        import threading
        s_id = "concurrent-session"
        errors = []

        def worker(idx):
            try:
                for i in range(20):
                    self.manager.append_message(
                        session_id=s_id,
                        role="user",
                        content=f"Thread {idx} Msg {i}"
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        history = self.manager.get_history(s_id)
        self.assertEqual(len(history), 100)


class TestAudioTranscriberComponent(unittest.TestCase):
    """Testes unitários do AudioTranscriber desacoplado."""

    def setUp(self):
        from server.chat.audio_transcriber import AudioTranscriber, InMemorySTTEngine
        self.AudioTranscriber = AudioTranscriber
        self.transcriber = AudioTranscriber()
        self.stt_legacy = InMemorySTTEngine()

    def _create_mock_wav(self, duration_sec: float = 0.5, framerate: int = 16000, metadata_prompt: str = None) -> bytes:
        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            n_samples = int(duration_sec * framerate)
            samples = [int(10000 * (i % 20 - 10) / 10) for i in range(n_samples)]
            raw_frames = struct.pack(f"<{n_samples}h", *samples)
            wf.writeframes(raw_frames)

        wav_bytes = bio.getvalue()
        if metadata_prompt:
            prompt_bytes = metadata_prompt.encode("utf-8") + b"\x00"
            chunk_len = len(prompt_bytes)
            info_chunk = b"INAM" + struct.pack("<I", chunk_len) + prompt_bytes
            wav_bytes = wav_bytes + info_chunk

        return wav_bytes

    def test_transcribe_empty_and_hints(self):
        res = self.transcriber.transcribe(b"")
        self.assertEqual(res, "Nenhum áudio detectado.")

        res_hint = self.transcriber.transcribe(b"audio_bytes", hint="Instrução direta")
        self.assertEqual(res_hint, "Instrução direta")

    def test_transcribe_wav_metadata(self):
        wav = self._create_mock_wav(metadata_prompt="Criar microsserviço de autenticação")
        res = self.transcriber.transcribe(wav)
        self.assertIn("Criar microsserviço de autenticação", res)

    def test_transcribe_acoustic_heuristic(self):
        wav = self._create_mock_wav(duration_sec=0.2)
        res = self.transcriber.transcribe(wav)
        self.assertIsInstance(res, str)
        self.assertTrue(len(res) > 5)

    def test_legacy_alias_compatibility(self):
        self.assertIs(self.AudioTranscriber, type(self.stt_legacy))


class TestStreamProviders(unittest.TestCase):
    """Testa os provedores individuais de streaming (OpenCode, OmniRoute, Ollama)."""

    def test_opencode_stream_provider(self):
        from server.chat.providers.opencode_stream import stream_opencode

        mock_ndjson = [
            json.dumps({"type": "reasoning", "part": {"text": "Pensando..."}}),
            json.dumps({"type": "text", "part": {"text": "Resposta final."}}),
            json.dumps({"type": "step_finish", "part": {"tokens": {"total": 42}, "cost": 0.0}}),
        ]

        with patch("shutil.which", return_value="/fake/opencode"):
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.stdout = io.StringIO("\n".join(mock_ndjson) + "\n")
                mock_proc.stderr = io.StringIO("")
                mock_proc.returncode = 0
                mock_proc.wait.return_value = 0
                mock_popen.return_value = mock_proc

                events = list(stream_opencode("s1", "mensagem teste", "opencode/mock"))
                types = [e["type"] for e in events]
                self.assertIn("thinking", types)
                self.assertIn("content", types)
                self.assertIn("step_finish", types)

    def test_omniroute_stream_provider(self):
        from server.chat.providers.omniroute_stream import stream_omniroute

        sse_lines = [
            b'data: {"choices": [{"delta": {"reasoning_content": "Pensando no Omni..."}}]}\n',
            b'data: {"choices": [{"delta": {"content": "Resposta do OmniRoute."}}]}\n',
            b'data: [DONE]\n'
        ]

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = sse_lines
            mock_urlopen.return_value = mock_resp

            events = list(stream_omniroute(
                omniroute_url="http://fake-omni:20128/v1",
                session_id="s-omni",
                message="Pergunta",
                model_id="omniroute/gpt-4o",
                history=[]
            ))
            types = [e["type"] for e in events]
            self.assertIn("thinking", types)
            self.assertIn("content", types)

    def test_ollama_stream_provider(self):
        from server.chat.providers.ollama_stream import stream_ollama

        ollama_lines = [
            b'{"message": {"thinking": "Pensando Ollama..."}}\n',
            b'{"message": {"content": "Resposta Ollama."}}\n'
        ]

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = ollama_lines
            mock_urlopen.return_value = mock_resp

            events = list(stream_ollama(
                ollama_url="http://fake-ollama:11434",
                session_id="s-ollama",
                message="Pergunta",
                model_id="qwen2.5-coder:7b",
                history=[]
            ))
            types = [e["type"] for e in events]
            self.assertIn("thinking", types)
            self.assertIn("content", types)


class TestZeusChatEngineFacade(unittest.TestCase):
    """Testa a fachada ZeusChatEngine integrando os módulos."""

    def test_facade_stream_chat_sse(self):
        from server.chat.zeus_engine import ZeusChatEngine

        engine = ZeusChatEngine()
        # Testa streaming com fallback local
        sse_events = list(engine.stream_chat_sse(
            session_id="facade-session",
            message="Liste os arquivos e execute testes",
            backend="fallback"
        ))

        self.assertTrue(len(sse_events) > 0)
        has_thinking = any('"thinking"' in ev for ev in sse_events)
        has_content = any('"content"' in ev for ev in sse_events)
        has_done = any('"done"' in ev for ev in sse_events)

        self.assertTrue(has_thinking, "SSE deve conter evento thinking")
        self.assertTrue(has_content, "SSE deve conter evento content")
        self.assertTrue(has_done, "SSE deve conter evento done")


if __name__ == "__main__":
    unittest.main()
