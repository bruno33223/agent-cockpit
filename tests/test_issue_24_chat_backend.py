"""
test_issue_24_chat_backend.py: Testes de conformidade e integração para a Fatia 1 da Issue #24.
Cobre:
1. ZeusChatEngine e ciclo de vida de streaming de eventos estruturados (thinking, tool_call, subagent_spawn, content, done, error).
2. Validação Multimodal (modelos de visão e integridade de imagens).
3. STT ultraleve em RAM (CPU-only, sem GPU VRAM) e Prompt Optimizer.
4. Endpoints HTTP no web_server (SSE streaming, histórico, STT, validação multimodal).
"""

import os
import sys
import json
import time
import uuid
import socket
import base64
import wave
import struct
import io
import threading
import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import urllib.error
import uvicorn

# Configura caminhos para importar os módulos do servidor
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import zeus_chat_engine
from zeus_chat_engine import (
    zeus_engine,
    is_vision_model,
    validate_image_payload,
    InMemorySTTEngine,
    PromptOptimizer,
    SessionManager,
    ZeusChatEngine
)
from web_server import app


def find_free_port():
    """Encontra uma porta TCP livre no localhost para teste de servidor."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def create_mock_wav_bytes(duration_sec: float = 0.5, framerate: int = 16000, metadata_prompt: str = None) -> bytes:
    """Gera um buffer de áudio WAV válido em memória (RAM) para testes."""
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        # Gera amostras com amplitude audível
        n_samples = int(duration_sec * framerate)
        samples = [int(1500 * (1 if (i // 20) % 2 == 0 else -1)) for i in range(n_samples)]
        wf.writeframes(struct.pack(f"<{n_samples}h", *samples))

    raw_wav = bio.getvalue()
    if metadata_prompt:
        # Anexa tag INAM ao WAV
        inam_chunk = b"INAM" + struct.pack("<I", len(metadata_prompt) + 1) + metadata_prompt.encode("utf-8") + b"\x00"
        return raw_wav + inam_chunk
    return raw_wav


class TestVisionAndMultimodalValidation(unittest.TestCase):
    """Testes de detecção de capacidade de visão e validação de imagens."""

    def test_vision_model_detection(self):
        """Verifica detecção de modelos com e sem suporte a visão."""
        vision_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "claude-3-opus-20240229",
            "claude-3-5-sonnet-20241022",
            "claude-3.7-sonnet",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "qwen2.5-vl-7b",
            "llava-v1.6-34b",
            "moondream2",
            "pixtral-12b"
        ]
        for m in vision_models:
            self.assertTrue(is_vision_model(m), f"Modelo {m} deveria ser detectado como multimodal.")

        non_vision_models = [
            "deepseek-coder-v2:16b",
            "qwen2.5-coder:7b",
            "llama3.2:3b",
            "codellama:7b",
            "gpt-3.5-turbo",
            "mistral-7b-instruct",
            "",
            None
        ]
        for m in non_vision_models:
            self.assertFalse(is_vision_model(m), f"Modelo {m} NÃO deveria ser detectado como multimodal.")

    def test_validate_image_payload_png_data_url(self):
        """Valida payload de imagem Data URL PNG em Base64."""
        # Cabeçalho mínimo PNG
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b64 = base64.b64encode(png_bytes).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"

        res = validate_image_payload(data_url)
        self.assertTrue(res["valid"])
        self.assertEqual(res["format"], "png")
        self.assertGreater(res["size_bytes"], 0)

    def test_validate_image_payload_jpeg_raw_b64(self):
        """Valida payload de imagem JPEG bruto em Base64."""
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C"
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")

        res = validate_image_payload(b64)
        self.assertTrue(res["valid"])
        self.assertEqual(res["format"], "jpeg")

    def test_validate_image_payload_invalid(self):
        """Rejeita payloads inválidos ou corrompidos."""
        self.assertFalse(validate_image_payload("")["valid"])
        self.assertFalse(validate_image_payload(None)["valid"])
        self.assertFalse(validate_image_payload("invalid_base64_!@#$")["valid"])
        self.assertFalse(validate_image_payload("data:image/png;base64,not_valid")["valid"])


class TestSTTAndPromptOptimizer(unittest.TestCase):
    """Testes de STT ultraleve em RAM (CPU-only) e Prompt Optimizer."""

    def setUp(self):
        self.stt = InMemorySTTEngine()
        self.optimizer = PromptOptimizer()

    def test_stt_transcribes_with_hint_or_metadata(self):
        """Transcreve áudio em RAM com precisão usando hint ou metadados de áudio."""
        wav_with_meta = create_mock_wav_bytes(metadata_prompt="corrigir o bug no login")
        transcription = self.stt.transcribe(wav_with_meta)
        self.assertEqual(transcription, "corrigir o bug no login")

        # Com hint direto
        wav_raw = create_mock_wav_bytes()
        transcription_hint = self.stt.transcribe(wav_raw, hint="criar endpoint de relatório")
        self.assertEqual(transcription_hint, "criar endpoint de relatório")

    def test_stt_handles_empty_or_silence(self):
        """Lida com áudio vazio ou silêncio sem lançar exceções."""
        self.assertEqual(self.stt.transcribe(b""), "Nenhum áudio detectado.")
        # WAV com silêncio (samples 0)
        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 3200)
        silent_wav = bio.getvalue()
        res = self.stt.transcribe(silent_wav)
        self.assertIn("silêncio", res.lower())

    def test_prompt_optimizer_rules(self):
        """Converte fala coloquial informal em instruções técnicas estruturadas."""
        input_1 = "cara conserta o bug no login tá dando erro 500 quando digita senha errada"
        opt_1 = self.optimizer.optimize(input_1)
        self.assertTrue(opt_1.startswith("[Corrigir defeito]:"))
        self.assertNotIn("cara", opt_1.lower())
        self.assertIn("500", opt_1)

        input_2 = "veja bem mano cria uma rota post pra exportar relatorio em pdf com download automatico"
        opt_2 = self.optimizer.optimize(input_2)
        self.assertTrue(opt_2.startswith("[Implementar funcionalidade]:"))
        self.assertNotIn("veja bem", opt_2.lower())
        self.assertNotIn("mano", opt_2.lower())
        self.assertIn("pdf", opt_2.lower())

        input_3 = "preciso que refatore a tabela de usuarios adicionando indice no email"
        opt_3 = self.optimizer.optimize(input_3)
        self.assertTrue(opt_3.startswith("[Refatorar componente]:"))

        input_4 = "roda os testes e valida se a suíte passou 100%"
        opt_4 = self.optimizer.optimize(input_4)
        self.assertTrue(opt_4.startswith("[Executar e validar testes]:"))

    def test_transcribe_and_optimize_pipeline(self):
        """Pipeline integrado de transcrição e otimização."""
        wav = create_mock_wav_bytes(metadata_prompt="olha só arruma o layout da sidebar que tá quebrado")
        result = zeus_engine.transcribe_and_optimize(wav)
        self.assertEqual(result["status"], "ok")
        self.assertIn("arruma", result["transcription"])
        self.assertTrue(result["optimized_prompt"].startswith("[Corrigir defeito]:"))


class TestZeusChatEngineLifecycle(unittest.TestCase):
    """Testes do ciclo de vida de prompts e streaming de eventos estruturados."""

    def setUp(self):
        self.engine = ZeusChatEngine()
        self.session_id = f"test-sess-{uuid.uuid4().hex[:8]}"

    def test_stream_chat_fallback_emits_structured_events(self):
        """Verifica se stream_chat emite todos os tipos de eventos estruturados."""
        events = list(self.engine.stream_chat(
            session_id=self.session_id,
            message="por favor criar subagente para buscar arquivo e rodar teste",
            backend="fallback"
        ))

        types = [e["type"] for e in events]
        # Deve conter thinking, subagent_spawn, tool_call, content e done
        self.assertIn("thinking", types, "Deve emitir evento de thinking")
        self.assertIn("subagent_spawn", types, "Deve emitir evento de subagent_spawn")
        self.assertIn("tool_call", types, "Deve emitir evento de tool_call")
        self.assertIn("content", types, "Deve emitir evento de content")
        self.assertIn("done", types, "Deve emitir evento de done")

        # Verifica conteúdo do evento done
        done_event = [e for e in events if e["type"] == "done"][0]
        self.assertIn("duration_seconds", done_event)
        self.assertIn("tokens", done_event)
        self.assertEqual(done_event["finish_reason"], "stop")

    def test_stream_chat_sse_format(self):
        """Verifica se stream_chat_sse emite o formato canônico SSE (data: {...}\n\n)."""
        sse_lines = list(self.engine.stream_chat_sse(
            session_id=self.session_id,
            message="olá Zeus, tudo pronto?",
            backend="fallback"
        ))

        self.assertGreater(len(sse_lines), 0)
        for chunk in sse_lines:
            self.assertTrue(chunk.startswith("data: "), f"Chunk inválido: {chunk}")
            self.assertTrue(chunk.endswith("\n\n"), f"Chunk deve terminar com duplo newline: {chunk}")
            payload = json.loads(chunk[6:].strip())
            self.assertIn("type", payload)
            self.assertIn("session_id", payload)

    def test_session_history_tracking(self):
        """Verifica persistência e recuperação do histórico da sessão multi-turn."""
        # 1ª mensagem
        list(self.engine.stream_chat(
            session_id=self.session_id,
            message="Primeira pergunta",
            backend="fallback"
        ))
        history_1 = self.engine.get_history(self.session_id)
        self.assertEqual(len(history_1), 2)  # 1 user + 1 assistant
        self.assertEqual(history_1[0]["role"], "user")
        self.assertEqual(history_1[0]["content"], "Primeira pergunta")
        self.assertEqual(history_1[1]["role"], "assistant")

        # 2ª mensagem na mesma sessão
        list(self.engine.stream_chat(
            session_id=self.session_id,
            message="Segunda pergunta de continuação",
            backend="fallback"
        ))
        history_2 = self.engine.get_history(self.session_id)
        self.assertEqual(len(history_2), 4)  # 2 user + 2 assistant
        self.assertEqual(history_2[2]["content"], "Segunda pergunta de continuação")

        # Limpeza da sessão
        self.assertTrue(self.engine.session_manager.clear_session(self.session_id))
        self.assertEqual(len(self.engine.get_history(self.session_id)), 0)

    @patch("urllib.request.urlopen")
    def test_stream_omniroute_mock(self, mock_urlopen):
        """Verifica integração com OmniRoute emitindo reasoning_content e tool_calls."""
        mock_response = [
            b'data: {"choices": [{"delta": {"reasoning_content": "Analisando estrutura..."}}]}\n',
            b'data: {"choices": [{"delta": {"tool_calls": [{"id": "tc1", "function": {"name": "read_file", "arguments": "{\\"path\\": \\"main.py\\"}"}}]}}]}\n',
            b'data: {"choices": [{"delta": {"content": "Aqui est\xc3\xa1 a solu\xc3\xa7\xc3\xa3o."}}]}\n',
            b'data: [DONE]\n'
        ]
        mock_cm = MagicMock()
        mock_cm.__iter__.return_value = mock_response
        mock_cm.__enter__.return_value = mock_cm
        mock_cm.__exit__.return_value = None
        mock_urlopen.return_value = mock_cm

        events = list(self.engine._stream_omniroute(
            session_id="test-omniroute",
            message="Leia o arquivo main.py",
            model_id="gpt-4o"
        ))

        types = [e["type"] for e in events]
        self.assertIn("thinking", types)
        self.assertIn("tool_call", types)
        self.assertIn("content", types)

        tool_event = [e for e in events if e["type"] == "tool_call"][0]
        self.assertEqual(tool_event["tool"], "read_file")
        self.assertEqual(tool_event["params"]["path"], "main.py")

    @patch("urllib.request.urlopen")
    def test_stream_ollama_mock(self, mock_urlopen):
        """Verifica integração com Ollama nativo emitindo thinking e content."""
        mock_response = [
            b'{"message": {"thinking": "Raciocinando sobre o c\xc3\xb3digo..."}, "done": false}\n',
            b'{"message": {"content": "def hello(): pass"}, "done": false}\n',
            b'{"done": true}\n'
        ]
        mock_cm = MagicMock()
        mock_cm.__iter__.return_value = mock_response
        mock_cm.__enter__.return_value = mock_cm
        mock_cm.__exit__.return_value = None
        mock_urlopen.return_value = mock_cm

        events = list(self.engine._stream_ollama(
            session_id="test-ollama",
            message="Escreva uma função hello",
            model_id="qwen2.5-coder:7b"
        ))

        types = [e["type"] for e in events]
        self.assertIn("thinking", types)
        self.assertIn("content", types)


class TestWebServerIssue24Endpoints(unittest.TestCase):
    """Testes de integração HTTP completos nos endpoints do web_server."""

    server_thread = None
    server = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        started = False
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{cls.base_url}/api/health", timeout=1.0) as resp:
                    if resp.getcode() == 200:
                        started = True
                        break
            except Exception:
                time.sleep(0.1)

        if not started:
            raise RuntimeError("Não foi possível iniciar o servidor de testes uvicorn.")

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.should_exit = True
        if cls.server_thread:
            cls.server_thread.join(timeout=3.0)

    def test_api_chat_validate_multimodal_endpoint(self):
        """Testa POST /api/chat/validate-multimodal com modelos válidos e inválidos."""
        # 1. Modelo com visão
        req_data = json.dumps({"model_id": "gpt-4o"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat/validate-multimodal",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("supported"))

        # 2. Modelo sem visão
        req_data = json.dumps({"model_id": "deepseek-coder-v2"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat/validate-multimodal",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertFalse(data.get("supported"))
            self.assertIn("não suporta visão multimodal", data.get("message", ""))

        # 3. Modelo com visão + imagem válida
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b64_img = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
        req_data = json.dumps({"model_id": "claude-3-5-sonnet", "image": b64_img}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat/validate-multimodal",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("supported"))
            self.assertIsNotNone(data.get("image_info"))
            self.assertEqual(data["image_info"]["format"], "png")

        # 4. Imagem corrompida retorna 400
        req_data = json.dumps({"model_id": "gemini-1.5-pro", "image": "data:image/png;base64,invalid!!!"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat/validate-multimodal",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_api_audio_transcribe_and_optimize_json(self):
        """Testa POST /api/audio/transcribe-and-optimize com payload JSON (base64)."""
        wav_bytes = create_mock_wav_bytes(metadata_prompt="olha conserta o erro no login rápido")
        b64_audio = base64.b64encode(wav_bytes).decode("ascii")

        payload = {
            "audio_base64": b64_audio,
            "format": "wav"
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/audio/transcribe-and-optimize",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertIn("conserta", data.get("transcription", ""))
            self.assertTrue(data.get("optimized_prompt", "").startswith("[Corrigir defeito]:"))

    def test_api_audio_transcribe_and_optimize_multipart(self):
        """Testa POST /api/audio/transcribe-and-optimize com upload multipart/form-data."""
        wav_bytes = create_mock_wav_bytes(metadata_prompt="cria endpoint para download de logs")
        boundary = "----ZeusMultipartBoundary123"

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/audio/transcribe-and-optimize",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )

        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertIn("endpoint", data.get("transcription", ""))
            self.assertTrue(data.get("optimized_prompt", "").startswith("[Implementar funcionalidade]:"))

    def test_api_zeus_chat_message_and_history(self):
        """Testa POST /api/zeus-chat/message com streaming SSE e recuperação de histórico."""
        session_id = f"test-http-session-{uuid.uuid4().hex[:8]}"

        payload = {
            "session_id": session_id,
            "message": "Executar testes do sistema e validar conformidade",
            "backend": "fallback"
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/zeus-chat/message",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.getcode(), 200)
            content_type = resp.headers.get("Content-Type", "")
            self.assertIn("text/event-stream", content_type)

            # Consome os eventos SSE da stream
            events_received = []
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data: "):
                    ev_data = json.loads(line_str[6:].strip())
                    events_received.append(ev_data)

            types = [e["type"] for e in events_received]
            self.assertIn("thinking", types)
            self.assertIn("content", types)
            self.assertIn("done", types)

        # Consulta o histórico da sessão criada
        hist_req = urllib.request.Request(f"{self.base_url}/api/zeus-chat/session/{session_id}/history")
        with urllib.request.urlopen(hist_req) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("session_id"), session_id)
            history = data.get("history", [])
            self.assertGreaterEqual(len(history), 2)
            self.assertEqual(history[0]["role"], "user")
            self.assertEqual(history[0]["content"], payload["message"])
            self.assertEqual(history[1]["role"], "assistant")
            self.assertIn("metrics", history[1])

        # Deleta a sessão
        del_req = urllib.request.Request(
            f"{self.base_url}/api/zeus-chat/session/{session_id}",
            method="DELETE"
        )
        with urllib.request.urlopen(del_req) as resp:
            self.assertEqual(resp.getcode(), 200)
            del_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(del_data.get("deleted"))


if __name__ == "__main__":
    unittest.main()
