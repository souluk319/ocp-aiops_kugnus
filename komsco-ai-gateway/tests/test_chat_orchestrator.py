import ast
import asyncio
from pathlib import Path

from komsco_ai_gateway import chat_models
from komsco_ai_gateway import chat_orchestrator
from komsco_ai_gateway import main as gateway_main


def test_main_reexports_chat_request_by_identity() -> None:
    assert gateway_main.ChatRequest is chat_models.ChatRequest


def test_chat_orchestrator_module_does_not_import_main() -> None:
    source = Path(chat_orchestrator.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "komsco_ai_gateway.main" not in imported_modules
    assert "main" not in imported_from


def test_chat_orchestrator_dependencies_capture_fresh_main_bindings(monkeypatch) -> None:
    first = lambda _request: "first"
    second = lambda _request: "second"

    monkeypatch.setattr(gateway_main, "general_concept_answer", first)
    first_dependencies = gateway_main._chat_orchestrator_dependencies()
    binding = chat_orchestrator.ChatRuntimeBinding.GENERAL_CONCEPT_ANSWER

    monkeypatch.setattr(gateway_main, "general_concept_answer", second)
    second_dependencies = gateway_main._chat_orchestrator_dependencies()

    assert first_dependencies.runtime.resolve(binding) is first
    assert second_dependencies.runtime.resolve(binding) is second


def test_chat_runtime_binding_contract_resolves_every_declared_main_symbol() -> None:
    runtime = gateway_main._chat_orchestrator_dependencies().runtime

    for binding in chat_orchestrator.ChatRuntimeBinding:
        assert runtime.resolve(binding) is getattr(gateway_main, binding.value)


def test_chat_orchestrator_has_no_function_rebinding_compatibility_hack() -> None:
    source = Path(chat_orchestrator.__file__).read_text(encoding="utf-8")

    assert "FunctionType" not in source
    assert "dict(globals())" not in source


def test_chat_latest_state_port_updates_main_globals() -> None:
    state = gateway_main._MainChatLatestStatePort()
    runtime_tool_plan = {"task_type": "inspect"}
    rca_context = {"phase": "post_answer"}

    state.set_runtime_tool_plan(runtime_tool_plan)
    state.set_rca_context(rca_context)

    assert gateway_main.LAST_RUNTIME_TOOL_PLAN is runtime_tool_plan
    assert gateway_main.LAST_RCA_CONTEXT is rca_context


def test_chat_stream_keeps_streaming_response_headers(monkeypatch) -> None:
    captured: list[object] = []

    class FakeOrchestrator:
        def __init__(self, dependencies) -> None:
            captured.append(dependencies)

        async def stream(self, request, authorization):
            captured.extend((request, authorization))
            yield "data: [DONE]\n\n"

    monkeypatch.setattr(gateway_main, "ChatOrchestrator", FakeOrchestrator)
    request = gateway_main.ChatRequest(message="hello")

    async def request_and_consume():
        response = await gateway_main.chat_stream(request, "Bearer token")
        chunks = [chunk async for chunk in response.body_iterator]
        return response, chunks

    response, chunks = asyncio.run(request_and_consume())

    assert captured[1:] == [request, "Bearer token"]
    assert chunks == ["data: [DONE]\n\n"]
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
