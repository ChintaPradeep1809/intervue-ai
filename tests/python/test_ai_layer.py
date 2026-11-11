"""AI schema / provider abstraction tests."""

import pytest
from pydantic import BaseModel

from intervue_ai import AIClient, AIProvider, AIProviderError, AIRequest, AIResult, MockAIProvider, TokenUsage, load_pricing
from intervue_ai.schema import to_strict_json_schema
from intervue_engine.schemas import FollowUpDecision, ResumeAnalysis
from intervue_eval import AnswerScore


def _walk(node, fn):
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            _walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            _walk(v, fn)


@pytest.mark.parametrize("model", [AnswerScore, ResumeAnalysis, FollowUpDecision])
def test_strict_schema_is_closed_and_fully_required(model):
    schema = to_strict_json_schema(model)
    assert "$defs" not in str(schema) and "$ref" not in str(schema)

    def check(n):
        if n.get("type") == "object" and "properties" in n:
            assert n["additionalProperties"] is False
            assert set(n["required"]) == set(n["properties"])
        for banned in ("minimum", "maximum", "title", "default"):
            assert banned not in n

    _walk(schema, check)


class Out(BaseModel):
    value: int


class FailingProvider(AIProvider):
    name = "failing"
    model = "x"

    def __init__(self):
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        raise AIProviderError("boom")


class GoodProvider(AIProvider):
    name = "good"
    model = "y"

    async def generate(self, request):
        return AIResult(output=request.schema(value=7), provider=self.name, model=self.model, usage=TokenUsage(10, 5), latency_ms=1)


async def test_client_retries_then_falls_back_to_next_provider():
    bad = FailingProvider()
    client = AIClient([bad, GoodProvider()], attempts_per_provider=2)
    seen = []

    async def on_usage(req, res):
        seen.append(res.provider)

    client.on_usage = on_usage
    res = await client.run(AIRequest(task="anything", schema=Out, system="", prompt=""))
    assert res.output.value == 7 and res.fallback_used and bad.calls == 2 and seen == ["good"]


async def test_client_uses_deterministic_fallback_when_llms_fail():
    client = AIClient([FailingProvider()], attempts_per_provider=1)
    ctx = {
        "answer": "I would use a window function with row_number partition by customer",
        "expected_concepts": [{"name": "window", "keywords": ["window function"]}],
    }
    res = await client.run(AIRequest(task="score_answer", schema=AnswerScore, system="", prompt="", context=ctx))
    assert res.provider == "mock" and res.fallback_used and res.output.covered_concepts == ["window"]


async def test_mock_provider_refuses_unknown_task():
    with pytest.raises(AIProviderError):
        await MockAIProvider().generate(AIRequest(task="unknown", schema=Out, system="", prompt=""))


def test_pricing_config_math(tmp_path):
    p = tmp_path / "p.json"
    p.write_text('{"llm": {"anthropic:*": {"input_per_mtok": 4, "output_per_mtok": 20, "cache_read_per_mtok": 0.2}}, "tts_per_1k_chars": {"elevenlabs": 0.18}}')
    cfg = load_pricing(p)
    i, o = cfg.llm_cost("anthropic", "claude-opus-5-5", 1_000_000, 100_000, cache_read_tokens=500_000)
    assert round(i, 4) == round(0.5 * 4 + 0.5 * 0.2, 4) and round(o, 4) == 2.0
    assert cfg.llm_cost("mock", "rule", 1000, 1000) == (0.0, 0.0)
    assert round(cfg.voice_cost("elevenlabs", 0, 2000), 4) == 0.36


class NoCreditsProvider(AIProvider):
    name = "nocredits"
    model = "x"

    def __init__(self):
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        raise AIProviderError("no credits", retryable=False, cooldown_seconds=60)


async def test_circuit_breaker_skips_exhausted_provider():
    bad = NoCreditsProvider()
    client = AIClient([bad, GoodProvider()], attempts_per_provider=3)
    seen_errors = []
    client.on_error = lambda task, provider, msg: seen_errors.append((task, msg))
    for _ in range(3):
        res = await client.run(AIRequest(task="t", schema=Out, system="", prompt=""))
        assert res.output.value == 7
    assert bad.calls == 1, "a provider out of credits is called once, then skipped during its cooldown"
    assert seen_errors == [("t", "no credits")]


def _completion(message: dict, finish: str = "stop") -> object:
    from openai.types.chat import ChatCompletion

    return ChatCompletion.model_validate(
        {
            "id": "c1",
            "object": "chat.completion",
            "created": 0,
            "model": "gemini-test",
            "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", **message}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )


async def test_chat_completions_provider_runs_tool_loop_and_validates_schema():
    from intervue_ai import ToolSpec, build_provider

    provider = build_provider("gemini", "test-key", "gemini-test")
    assert str(provider._client.base_url).startswith("https://generativelanguage.googleapis.com/")
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "lookup", "arguments": '{"q": "x"}'},
        "extra_content": {"google": {"thought_signature": "sig"}},
    }
    responses = [
        _completion({"content": None, "tool_calls": [tool_call]}, "tool_calls"),
        _completion({"content": '```json\n{"value": 7}\n```'}),
    ]
    sent = []

    async def create(**kwargs):
        sent.append(kwargs)
        return responses[len(sent) - 1]

    provider._client.chat.completions.create = create

    async def lookup(args):
        return f"looked up {args['q']}"

    req = AIRequest(task="t", schema=Out, system="s", prompt="p", tools=[ToolSpec("lookup", "d", {"type": "object"}, lookup)])
    res = await provider.generate(req)
    assert res.output.value == 7 and res.tool_calls == ["lookup"]
    assert res.usage.input_tokens == 20 and res.usage.output_tokens == 10
    assert sent[0]["response_format"]["json_schema"]["strict"] is True
    replayed = sent[1]["messages"]
    assert replayed[2]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "sig"}}, "thought signature replayed"
    assert replayed[3] == {"role": "tool", "tool_call_id": "call_1", "content": "looked up x"}


async def test_chat_completions_provider_rate_limit_steps_aside():
    import httpx
    import openai

    from intervue_ai import build_provider

    provider = build_provider("openai_compat", "k", "m", base_url="http://localhost:9/v1")

    async def create(**kwargs):
        resp = httpx.Response(429, request=httpx.Request("POST", "http://localhost:9/v1/chat/completions"))
        raise openai.RateLimitError("Quota exceeded for requests per day", response=resp, body=None)

    provider._client.chat.completions.create = create
    with pytest.raises(AIProviderError) as err:
        await provider.generate(AIRequest(task="t", schema=Out, system="s", prompt="p"))
    assert err.value.cooldown_seconds == 3600 and not err.value.retryable


def test_edge_voice_provider_config():
    from intervue_voice import EdgeVoiceProvider, build_voice_provider

    vp = build_voice_provider("edge", None, "en-IN-PrabhatNeural")
    assert isinstance(vp, EdgeVoiceProvider)
    cfg = vp.session_config()
    assert (cfg.tts, cfg.stt, cfg.language, cfg.voice_hint) == ("server", "browser", "en-IN", "en-IN-PrabhatNeural")
    # an ElevenLabs voice id is not an Edge voice: use the default Indian English voice
    assert build_voice_provider("edge", None, "XrExE9yKIg1WjnnlVkGX").voice == "en-IN-NeerjaNeural"
