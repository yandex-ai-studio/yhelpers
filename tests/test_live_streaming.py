from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pytest
from IPython.display import HTML

pytestmark = pytest.mark.live


def live_credentials() -> tuple[str, str]:
    if os.getenv("YHELPERS_RUN_LIVE") != "1":
        pytest.skip("set YHELPERS_RUN_LIVE=1 to run live tests")
    folder_id = os.getenv("folder_id")
    api_key = os.getenv("api_key")
    if not folder_id or not api_key:
        pytest.skip("folder_id and api_key are required")
    return folder_id, api_key


@dataclass
class LiveAPI:
    client: Any
    folder_id: str
    api_key: str
    model: str


@pytest.fixture(scope="module")
def live_api():
    from openai import OpenAI

    folder_id, api_key = live_credentials()
    client = OpenAI(
        base_url="https://ai.api.cloud.yandex.net/v1",
        api_key=api_key,
        project=folder_id,
    )
    yield LiveAPI(
        client=client,
        folder_id=folder_id,
        api_key=api_key,
        model=f"gpt://{folder_id}/qwen3-235b-a22b-fp8",
    )
    client.close()


@pytest.fixture(scope="module")
def live_vector_store(live_api: LiveAPI):
    document = BytesIO(
        b"Project Orion's launch code is AURORA-729. "
        b"The mission owner is the Notebook Reliability Team."
    )
    uploaded = None
    vector_store = None
    try:
        uploaded = live_api.client.files.create(
            file=("project_orion.txt", document),
            purpose="assistants",
        )
        vector_store = live_api.client.vector_stores.create(
            name="yhelpers-live-streaming-test"
        )
        live_api.client.vector_stores.files.create_and_poll(
            vector_store_id=vector_store.id,
            file_id=uploaded.id,
        )
        yield vector_store.id
    finally:
        if vector_store is not None:
            with contextlib.suppress(Exception):
                live_api.client.vector_stores.delete(vector_store_id=vector_store.id)
        if uploaded is not None:
            with contextlib.suppress(Exception):
                live_api.client.files.delete(file_id=uploaded.id)


@pytest.fixture(scope="module")
def live_container(live_api: LiveAPI):
    container = live_api.client.containers.create(
        name="yhelpers-live-streaming-test",
        expires_after={"anchor": "last_active_at", "minutes": 20},
    )
    try:
        yield container.id
    finally:
        with contextlib.suppress(Exception):
            live_api.client.containers.delete(container_id=container.id)


class RecordingStream:
    def __init__(self, stream):
        self.stream = stream
        self.event_types: list[str] = []

    def __iter__(self):
        for event in self.stream:
            self.event_types.append(event.type)
            yield event


def output_types(response) -> set[str]:
    return {str(getattr(item, "type", "")) for item in response.output}


def raw_item_types(result) -> set[str]:
    return {
        str(getattr(getattr(item, "raw_item", None), "type", ""))
        for item in result.new_items
    }


def assert_compact_default(display_capture) -> None:
    cards = [
        call.value.data
        for call in display_capture.calls
        if isinstance(call.value, HTML) and not call.display_id
    ]
    assert cards
    assert all("<pre" not in card for card in cards)
    assert all("&quot;response&quot;" not in card for card in cards)


def test_live_responses_stream(live_api: LiveAPI):
    from yhelpers.responses.streaming import jstream

    stream = live_api.client.responses.create(
        model=live_api.model,
        input="Reply with one short Markdown heading and one sentence.",
        stream=True,
    )
    response = jstream(stream, events=[])
    assert response.status == "completed"
    assert response.output_text


def test_live_responses_web_search(live_api: LiveAPI, display_capture):
    from yhelpers.responses.streaming import jstream

    stream = RecordingStream(
        live_api.client.responses.create(
            model=live_api.model,
            instructions=(
                "You must use web search exactly once, then answer in two short "
                "sentences and cite the source URL."
            ),
            input="What title is shown on the current Python 3 documentation home page?",
            tools=[{"type": "web_search", "search_context_size": "low"}],
            stream=True,
        )
    )
    response = jstream(stream)
    assert response.status == "completed"
    assert "web_search_call" in output_types(response)
    assert "response.web_search_call.searching" in stream.event_types
    assert_compact_default(display_capture)


def test_live_responses_code_interpreter(
    live_api: LiveAPI,
    live_container: str,
    display_capture,
):
    from yhelpers.responses.streaming import jstream

    stream = RecordingStream(
        live_api.client.responses.create(
            model=live_api.model,
            instructions=(
                "You must use Code Interpreter and show the exact Python code used."
            ),
            input=(
                "Use Python to calculate the sum of the squares from 1 through 100. "
                "Return the number and one sentence explaining the formula."
            ),
            include=["code_interpreter_call.outputs"],
            tools=[
                {
                    "type": "code_interpreter",
                    "container": live_container,
                }
            ],
            stream=True,
        )
    )
    response = jstream(stream)
    assert response.status == "completed"
    assert "code_interpreter_call" in output_types(response)
    assert any("code_interpreter_call_code" in name for name in stream.event_types)
    assert_compact_default(display_capture)


def test_live_responses_file_search(
    live_api: LiveAPI,
    live_vector_store: str,
    display_capture,
):
    from yhelpers.responses.streaming import jstream

    stream = RecordingStream(
        live_api.client.responses.create(
            model=live_api.model,
            instructions=(
                "You must use file search. Answer only from the indexed document."
            ),
            input="What is Project Orion's launch code and who owns the mission?",
            include=["file_search_call.results"],
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [live_vector_store],
                    "max_num_results": 3,
                }
            ],
            stream=True,
        )
    )
    response = jstream(stream)
    assert response.status == "completed"
    assert "file_search_call" in output_types(response)
    assert "response.file_search_call.searching" in stream.event_types
    assert "AURORA-729" in response.output_text
    assert_compact_default(display_capture)


@pytest.mark.asyncio
async def test_live_agents_stream(live_api: LiveAPI):
    from agents import Agent, Runner, function_tool, set_tracing_disabled
    from agents.models.openai_responses import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from yhelpers.agents.streaming import jstream

    set_tracing_disabled(True)
    client = AsyncOpenAI(
        base_url="https://ai.api.cloud.yandex.net/v1",
        api_key=live_api.api_key,
        project=live_api.folder_id,
    )

    @function_tool
    def word_count(text: str) -> str:
        """Count words in text."""
        return str(len(text.split()))

    agent = Agent(
        name="Counter",
        model=OpenAIResponsesModel(model=live_api.model, openai_client=client),
        instructions="Always call word_count before answering briefly.",
        tools=[word_count],
    )
    result = Runner.run_streamed(agent, "Count: AI Studio streams nicely")
    try:
        result = await jstream(result, events=[])
        assert result.is_complete
        assert result.final_output
        assert "function_call" in raw_item_types(result)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_live_agents_all_hosted_tools(
    live_api: LiveAPI,
    live_vector_store: str,
    live_container: str,
    display_capture,
):
    from agents import (
        Agent,
        CodeInterpreterTool,
        FileSearchTool,
        Runner,
        WebSearchTool,
        set_tracing_disabled,
    )
    from agents.models.openai_responses import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from yhelpers.agents.streaming import jstream

    set_tracing_disabled(True)
    client = AsyncOpenAI(
        base_url="https://ai.api.cloud.yandex.net/v1",
        api_key=live_api.api_key,
        project=live_api.folder_id,
    )
    agent = Agent(
        name="Hosted tools verifier",
        model=OpenAIResponsesModel(model=live_api.model, openai_client=client),
        instructions=(
            "You are testing hosted tools. You must use all three tools exactly once: "
            "file search for the local Project Orion facts, web search for the current "
            "Python documentation page title, and Code Interpreter to calculate the "
            "sum of squares from 1 through 20. Finish with three concise bullets."
        ),
        tools=[
            WebSearchTool(search_context_size="low"),
            FileSearchTool(
                vector_store_ids=[live_vector_store],
                max_num_results=3,
                include_search_results=True,
            ),
            CodeInterpreterTool(
                tool_config={
                    "type": "code_interpreter",
                    "container": live_container,
                }
            ),
        ],
    )
    result = Runner.run_streamed(
        agent,
        (
            "Find Project Orion's launch code and owner in the indexed file; find "
            "the current Python 3 docs home-page title on the web; then use Python "
            "to sum the squares from 1 through 20."
        ),
        max_turns=8,
    )
    try:
        result = await jstream(result)
        assert result.is_complete
        assert result.final_output
        assert {
            "web_search_call",
            "file_search_call",
            "code_interpreter_call",
        }.issubset(raw_item_types(result))
        assert "AURORA-729" in str(result.final_output)
        assert_compact_default(display_capture)
    finally:
        await client.close()
