"""Tests for pluggable benchmarks with mock adapters and preloaded items."""

from __future__ import annotations

from typing import Any

import pytest

from tool_eval_bench.adapters.base import (
    BackendAdapter,
    ChatCompletionResult,
)
from tool_eval_bench.plugins.gsm8k.dataset import GSM8KItem
from tool_eval_bench.plugins.gsm8k.plugin import GSM8KPlugin
from tool_eval_bench.plugins.ifeval.dataset import IFEvalItem
from tool_eval_bench.plugins.ifeval.plugin import IFEvalPlugin
from tool_eval_bench.plugins.mmlu.dataset import MMLUItem
from tool_eval_bench.plugins.mmlu.plugin import MMLUPlugin


class MockAdapter(BackendAdapter):
    """Simple mock adapter that returns pre-packaged model responses."""

    def __init__(self, response_content: str) -> None:
        self.response_content = response_content
        self.calls: list[dict] = []

    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict] | list[Any],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout_seconds: float = 60.0,
        api_key: str | None = None,
        base_url: str = "",
        extra_params: dict | None = None,
        stream: bool = False,
        response_format: dict | None = None,
        parallel_tool_calls: bool | None = True,
    ) -> ChatCompletionResult:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
                "api_key": api_key,
                "base_url": base_url,
                "extra_params": extra_params,
                "stream": stream,
                "response_format": response_format,
                "parallel_tool_calls": parallel_tool_calls,
            }
        )
        return ChatCompletionResult(
            content=self.response_content,
            tool_calls=[],
            raw_response={"choices": [{"message": {"content": self.response_content}}]},
            elapsed_ms=15.0,
        )


@pytest.mark.asyncio
async def test_gsm8k_plugin_run() -> None:
    """GSM8K evaluation: sequential and parallel loops."""
    items = [
        GSM8KItem(
            index=0,
            question="What is 2+2?",
            raw_answer="#### 4",
            ground_truth=4.0,
        ),
        GSM8KItem(
            index=1,
            question="What is 3+3?",
            raw_answer="#### 6",
            ground_truth=6.0,
        ),
    ]

    # Test sequential run (concurrency=1)
    adapter_seq = MockAdapter("The answer is 4. #### 4")
    plugin = GSM8KPlugin()
    result_seq = await plugin.run(
        adapter_seq,
        model="test-model",
        base_url="http://localhost:8000",
        _preloaded_items=items,
        concurrency=1,
    )
    assert result_seq.plugin_name == "gsm8k"
    # 1 out of 2 correct (both adapter calls return 4)
    assert result_seq.score == 50.0
    assert len(adapter_seq.calls) == 2

    # Test parallel run (concurrency=2)
    adapter_par = MockAdapter("The answer is 6. #### 6")
    result_par = await plugin.run(
        adapter_par,
        model="test-model",
        base_url="http://localhost:8000",
        _preloaded_items=items,
        concurrency=2,
    )
    assert result_par.plugin_name == "gsm8k"
    # 1 out of 2 correct (both adapter calls return 6)
    assert result_par.score == 50.0
    assert len(adapter_par.calls) == 2


@pytest.mark.asyncio
async def test_mmlu_plugin_run() -> None:
    """MMLU evaluation: sequential and parallel loops."""
    choices = ["A", "B", "C", "D"]
    items = [
        MMLUItem(
            index=0,
            question="Q1",
            subject="abstract_algebra",
            choices=choices,
            answer=0,
        ),
        MMLUItem(
            index=1,
            question="Q2",
            subject="abstract_algebra",
            choices=choices,
            answer=1,
        ),
    ]

    # Test sequential run
    adapter_seq = MockAdapter("A")
    plugin = MMLUPlugin()
    result_seq = await plugin.run(
        adapter_seq,
        model="test-model",
        base_url="http://localhost:8000",
        _preloaded_items={"test": items, "dev": []},
        concurrency=1,
        n_shots=0,
    )
    assert result_seq.plugin_name == "mmlu"
    assert result_seq.score == 50.0  # index 0 matches A
    assert len(adapter_seq.calls) == 2

    # Test parallel run
    adapter_par = MockAdapter("B")
    result_par = await plugin.run(
        adapter_par,
        model="test-model",
        base_url="http://localhost:8000",
        _preloaded_items={"test": items, "dev": []},
        concurrency=2,
        n_shots=0,
    )
    assert result_par.plugin_name == "mmlu"
    assert result_par.score == 50.0
    assert len(adapter_par.calls) == 2


@pytest.mark.asyncio
async def test_ifeval_plugin_run() -> None:
    """IFEval evaluation: sequential and parallel loops."""
    items = [
        IFEvalItem(
            key=0,
            prompt="P1",
            instruction_id_list=["punctuation:no_comma"],
            kwargs=[{"comma_number": 0}],
        ),
        IFEvalItem(
            key=1,
            prompt="P2",
            instruction_id_list=["punctuation:no_comma"],
            kwargs=[{"comma_number": 0}],
        ),
    ]

    # Test sequential run
    adapter_seq = MockAdapter("Response without any commas.")
    plugin = IFEvalPlugin()
    result_seq = await plugin.run(
        adapter_seq,
        model="test-model",
        base_url="http://localhost:8000",
        _preloaded_items=items,
        concurrency=1,
    )
    assert result_seq.plugin_name == "ifeval"
    assert result_seq.score == 100.0  # both follow instructions
    assert len(adapter_seq.calls) == 2

    # Test parallel run
    adapter_par = MockAdapter("Response, with, commas.")
    result_par = await plugin.run(
        adapter_par,
        model="test-model",
        base_url="http://localhost:8000",
        _preloaded_items=items,
        concurrency=2,
    )
    assert result_par.plugin_name == "ifeval"
    assert result_par.score == 0.0  # both fail instructions
    assert len(adapter_par.calls) == 2
