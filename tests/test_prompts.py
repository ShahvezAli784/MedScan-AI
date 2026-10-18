import json
from types import SimpleNamespace

import pytest

import config
from src.ai import coach, prompts


def record(conn_medicines):
    return next(m for m in conn_medicines if m["brand_name"] == "Panadol")


def test_explanation_prompt_is_grounded(medicines):
    msgs = prompts.build_explanation_messages(record(medicines), "Roman Urdu")
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert "ONLY from the DATABASE RECORD" in system and "Never give dosing" in system
    assert "Roman Urdu" in system and config.DISCLAIMER in system
    assert "Brand name: Panadol" in user and "Active ingredient: Paracetamol" in user


def test_language_instructions():
    assert "Urdu (Arabic) script" in prompts.language_instruction("Urdu")
    assert prompts.language_instruction("Klingon") == config.LANGUAGES["English"]


def test_assistant_prompt_mentions_tools_and_context():
    p = prompts.build_assistant_system_prompt("English", '{"x": 1}')
    assert "get_cabinet" in p and "check_duplicates" in p and '{"x": 1}' in p


def test_missing_values_marked(medicines):
    assert "Uses: not in database" in prompts.format_record({"brand_name": "X"})


@pytest.mark.parametrize("q", [
    "What is the dose of Panadol?", "How many tablets can I take?", "Can I take Brufen with Panadol?",
    "Is it safe to combine these?", "Please diagnose my headache", "Panadol ki kitni khurak?",
    "Should I take this for my fever, how often?", "mix with ibuprofen?"])
def test_guardrail_blocks(q):
    refusal = prompts.screen_user_question(q)
    assert refusal and config.DISCLAIMER in refusal


@pytest.mark.parametrize("q", ["What is in my cabinet?", "What is expiring soon?", "Do I have duplicates?",
                               "What is Panadol used for?"])
def test_guardrail_allows(q):
    assert prompts.screen_user_question(q) is None


def test_refusal_in_other_languages():
    assert "فارماسسٹ" in prompts.screen_user_question("dose?", "Urdu")
    assert "pharmacist" in prompts.screen_user_question("dose?", "Roman Urdu")


# ---- coach behaviour with a fake Groq client (no network) -------------------------------
class FakeClient:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def reply(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


def tool_call(name, args="{}"):
    return SimpleNamespace(id="call_1", function=SimpleNamespace(name=name, arguments=args))


def test_no_key_disables_ai(monkeypatch, conn):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not coach.ai_enabled()
    res = coach.ask_assistant(conn, 1, [], "What is expiring soon?")
    assert not res.ok and "GROQ_API_KEY" in res.text
    assert not coach.explain_medicine({"brand_name": "X"}, "English").ok


def test_guardrail_runs_before_llm(conn):
    client = FakeClient([])
    res = coach.ask_assistant(conn, 1, [], "What dose should I take?", client=client)
    assert res.ok and client.calls == []


def test_tool_calling_loop_ignores_model_user_id(conn):
    demo_id = 1
    client = FakeClient([reply(tool_calls=[tool_call("get_cabinet", '{"user_id": 999}')]), reply("You have 5 medicines.")])
    res = coach.ask_assistant(conn, demo_id, [], "What is in my cabinet?", client=client)
    assert res.ok and res.tools_used == ["get_cabinet"] and not res.used_fallback
    tool_msg = [m for m in client.calls[1]["messages"] if m["role"] == "tool"][0]
    assert "Panadol" in tool_msg["content"]  # demo user's data, not user 999's


def test_check_duplicates_tool(conn):
    out = json.loads(coach.run_tool(coach.make_tool_registry(conn, 1), "check_duplicates", "{}"))
    assert {g["shared_ingredient"] for g in out["groups"]} == {"paracetamol", "ibuprofen"}
    assert out["note"] == config.DUPLICATE_WARNING
    assert "error" in json.loads(coach.run_tool(coach.make_tool_registry(conn, 1), "nope", "{}"))


def test_falls_back_to_plain_prompt_when_tools_fail(conn):
    client = FakeClient([RuntimeError("tool_use_failed"), reply("Plain answer.")])
    res = coach.ask_assistant(conn, 1, [], "Do I have duplicate ingredients?", client=client)
    assert res.ok and res.used_fallback and res.text == "Plain answer."
    assert "tools" not in client.calls[1] and "CABINET DATA" in client.calls[1]["messages"][0]["content"]


def test_rate_limit_message(conn):
    class RateLimitError(Exception):
        pass
    res = coach.ask_assistant(conn, 1, [], "What is in my cabinet?", client=FakeClient([RateLimitError("429")]))
    assert not res.ok and "rate-limited" in res.text


def test_explain_medicine_with_fake_client(medicines):
    client = FakeClient([reply("Panadol is paracetamol.")])
    res = coach.explain_medicine(record(medicines), "English", client=client)
    assert res.ok and "paracetamol" in res.text.lower()
    assert client.calls[0]["model"] == config.GROQ_MODEL
