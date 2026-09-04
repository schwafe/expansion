#!/usr/bin/env python3
"""
Test suite for the helpers the whole workflow shares.

Mostly the two shapes a vita is kept in: `data/*.csv` has one row per regest
(plus one for the header), which is how the RG itself is laid out; the model
steps and the evaluation want the vita as one text. The two conversions have to
be exact inverses of each other, since the workflow goes back and forth between
them at every step. The rest is the per-model shape of the thinking settings,
and which failures of the endpoint are worth another try.
"""

import re
import threading
import time
from types import SimpleNamespace

import polars as pl
import pytest
from openai import APIError, APITimeoutError

import helper_functions
from helper_functions import (
    VITA_SCHEMA,
    call_chat_ai,
    check_the_model,
    wait_for_a_slot,
    text_to_vita_df,
    thinking_kwargs,
    vita_df_to_text,
    vita_dfs_to_vita_texts,
    vita_texts_to_vita_dfs,
)


def texts(*rows) -> pl.DataFrame:
    """One row per vita: (volume, nr_RG, text)."""
    return pl.DataFrame(
        {
            "volume": [row[0] for row in rows],
            "nr_RG": [row[1] for row in rows],
            "text": [row[2] for row in rows],
        },
        schema={"volume": pl.Int64, "nr_RG": pl.Int64, "text": pl.String},
    )


VITA = texts((2, 370, "Brunswic eccl. mai.\nde indulg. 1392\nde conc. 1393"))


class TestVitaTextsToVitaDfs:
    def test_the_first_line_is_the_header_and_the_rest_are_regests(self):
        vita = vita_texts_to_vita_dfs(VITA)
        assert vita.get_column("header_no_tags").to_list() == [
            "Brunswic eccl. mai.", None, None
        ]
        assert vita.get_column("regest_no_tags").to_list() == [
            None, "de indulg. 1392", "de conc. 1393"
        ]

    def test_the_numbering_is_rebuilt_from_the_position(self):
        vita = vita_texts_to_vita_dfs(VITA)
        assert vita.get_column("nr_suffix").to_list() == [0, 1, 2]
        assert vita.get_column("id_RG_all").to_list() == [
            "10200370-0", "10200370-1", "10200370-2"
        ]

    def test_several_vitae_keep_the_order_of_the_input(self):
        vita = vita_texts_to_vita_dfs(texts(
            (2, 370, "first\nregest"), (5, 885, "second\nregest"),
        ))
        assert vita.get_column("nr_RG").to_list() == [370, 370, 885, 885]

    def test_a_vita_of_a_header_alone_stacks_with_the_others(self):
        """Its regest column is nothing but nulls -- the schema keeps it String."""
        vita = vita_texts_to_vita_dfs(texts(
            (2, 370, "a header and nothing else"), (5, 885, "a header\na regest"),
        ))
        assert vita.height == 3
        assert vita.schema == VITA_SCHEMA

    def test_the_text_column_can_be_named_otherwise(self):
        renamed = VITA.rename({"text": "normalized"})
        assert vita_texts_to_vita_dfs(renamed, "normalized").height == 3


class TestRoundTrip:
    def test_texts_survive_the_way_out_and_back(self):
        assert vita_dfs_to_vita_texts(vita_texts_to_vita_dfs(VITA)).equals(VITA)

    def test_regest_rows_survive_the_way_out_and_back(self):
        vita = vita_texts_to_vita_dfs(VITA)
        back = vita_texts_to_vita_dfs(vita_dfs_to_vita_texts(vita))
        assert back.equals(vita)

    def test_one_vita_at_a_time_agrees_with_the_whole_table(self):
        vita = vita_texts_to_vita_dfs(VITA)
        assert vita_df_to_text(vita) == VITA.get_column("text").item()
        assert text_to_vita_df(VITA.get_column("text").item(), 2, 370).equals(vita)


class TestThinkingKwargs:
    """The thinking settings in the shape each family of models expects."""

    def test_asking_for_nothing_changes_nothing(self):
        assert thinking_kwargs("gemma-4-31b-it") == {}

    def test_the_families_that_take_a_template_variable_get_their_own_name_for_it(self):
        assert thinking_kwargs("gemma-4-31b-it", thinking=False) == {
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}
        }
        assert thinking_kwargs("deepseek-v4-flash-0731", thinking=False) == {
            "extra_body": {"chat_template_kwargs": {"thinking": False}}
        }

    def test_the_longer_prefix_wins(self):
        """qwen3.8 knows levels, the rest of qwen3 does not."""
        assert thinking_kwargs("qwen3.8-27b", reasoning_effort="low")["reasoning_effort"] == "low"
        assert "reasoning_effort" not in thinking_kwargs("qwen3.6-35b-a3b", thinking=True)

    def test_a_level_is_a_parameter_for_some_and_a_template_variable_for_others(self):
        assert thinking_kwargs("openai-gpt-oss-120b", reasoning_effort="high") == {
            "reasoning_effort": "high"
        }
        assert thinking_kwargs("deepseek-v4-flash-0731", reasoning_effort="max") == {
            "extra_body": {"chat_template_kwargs": {"reasoning_effort": "max", "thinking": True}}
        }

    def test_a_level_turns_the_thinking_on_by_itself(self):
        template = thinking_kwargs("qwen3.8-27b", reasoning_effort="low")["extra_body"]
        assert template["chat_template_kwargs"] == {"enable_thinking": True}

    def test_a_family_without_a_switch_says_it_with_a_level(self):
        assert thinking_kwargs("mistral-medium-3.5-128b", thinking=False) == {
            "reasoning_effort": "none"
        }
        assert thinking_kwargs("mistral-medium-3.5-128b", thinking=True) == {
            "reasoning_effort": "high"
        }

    def test_a_level_the_family_does_not_know_is_refused(self):
        with pytest.raises(ValueError, match="low/medium/xhigh"):
            thinking_kwargs("qwen3.8-27b", reasoning_effort="max")

    def test_a_family_with_no_levels_at_all_says_so(self):
        with pytest.raises(ValueError, match="no levels at all"):
            thinking_kwargs("glm-4.7", reasoning_effort="high")

    def test_a_model_that_cannot_stop_thinking_says_so(self):
        with pytest.raises(ValueError, match="cannot be told not to think"):
            thinking_kwargs("openai-gpt-oss-120b", thinking=False)

    def test_a_level_that_contradicts_the_switch_is_refused(self):
        with pytest.raises(ValueError, match="contradict"):
            thinking_kwargs("mistral-medium-3.5-128b", thinking=False, reasoning_effort="high")

    def test_a_model_with_levels_is_not_only_told_to_think(self):
        # "thinking on" leaves the level to the endpoint, and the report would
        # then say the run thought, but not how much
        with pytest.raises(ValueError, match="name the level"):
            thinking_kwargs("qwen3.8-27b", thinking=True)
        with pytest.raises(ValueError, match="low/high/max"):
            thinking_kwargs("deepseek-v4-flash-0731", thinking=True)
        with pytest.raises(ValueError, match="low/medium/high"):
            thinking_kwargs("openai-gpt-oss-120b", thinking=True)

    def test_a_family_with_one_level_to_think_at_needs_no_naming(self):
        """mistral thinks at `high` or not at all, so `--thinking` says it."""
        assert thinking_kwargs("mistral-medium-3.5-128b", thinking=True) == {
            "reasoning_effort": "high"
        }

    def test_a_model_without_levels_is_told_to_think_and_that_is_all_there_is(self):
        assert thinking_kwargs("gemma-4-31b-it", thinking=True) == {
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}
        }

    def test_a_level_alone_still_says_everything(self):
        assert thinking_kwargs("qwen3.8-27b", thinking=True, reasoning_effort="low") == {
            "reasoning_effort": "low",
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
        }

    def test_switching_the_thinking_off_needs_no_level(self):
        assert thinking_kwargs("qwen3.8-27b", thinking=False) == {
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}
        }

    def test_a_model_that_does_not_think_is_asked_for_nothing(self):
        assert thinking_kwargs("apertus-70b-instruct-2509", thinking=False) == {}
        assert thinking_kwargs("meta-llama-3.1-8b-instruct", thinking=False) == {}
        assert thinking_kwargs("devstral-2-123b-instruct-2512", thinking=False) == {}

    def test_a_model_that_does_not_think_cannot_be_told_to(self):
        # apertus takes both settings and answers the same either way; the
        # Mistral tokenizer of devstral answers 400 -- neither is a thought
        with pytest.raises(ValueError, match="does not think at all"):
            thinking_kwargs("apertus-70b-instruct-2509", thinking=True)
        with pytest.raises(ValueError, match="does not think at all"):
            thinking_kwargs("devstral-2-123b-instruct-2512", reasoning_effort="high")

    def test_an_unknown_model_is_not_guessed_at(self):
        with pytest.raises(ValueError, match="no thinking style known"):
            thinking_kwargs("olmo-3-32b-instruct", thinking=False)

    def test_an_unknown_model_without_a_setting_is_left_alone(self):
        assert thinking_kwargs("olmo-3-32b-instruct") == {}


def an_endpoint(*models, fails: Exception | None = None):
    """A client that lists these models, or fails to list anything."""
    def listing():
        if fails is not None:
            raise fails
        return SimpleNamespace(data=[SimpleNamespace(id=model) for model in models])

    return SimpleNamespace(base_url="https://endpoint/v1",
                           models=SimpleNamespace(list=listing))


class TestTheModelIsThere:
    """
    A mistyped model name, caught before the vitae pay for it.

    Without this every vita asks for the unknown name and is answered with a
    404, which reads like an endpoint that is down rather than like a typo.
    """

    def test_a_model_the_endpoint_has_is_run(self):
        check_the_model(an_endpoint("gemma-4-31b-it", "qwen3.8-27b"), "gemma-4-31b-it")

    def test_a_model_the_endpoint_does_not_have_stops_the_run(self):
        with pytest.raises(ValueError, match="no model 'gpt-oss-120b123123'"):
            check_the_model(an_endpoint("openai-gpt-oss-120b"), "gpt-oss-120b123123")

    def test_the_refusal_says_what_there_is_instead(self):
        # the name that was meant is usually in the list
        with pytest.raises(ValueError) as refused:
            check_the_model(an_endpoint("openai-gpt-oss-120b", "gemma-4-31b-it"), "gpt-oss")
        assert "openai-gpt-oss-120b" in str(refused.value)
        assert "gemma-4-31b-it" in str(refused.value)

    def test_an_endpoint_that_cannot_be_reached_does_not_stop_the_run(self, capsys):
        # the vitae are asked for over the next hour; this says nothing about them
        check_the_model(an_endpoint(fails=APITimeoutError(request=None)), "gemma-4-31b-it")
        assert "could not ask" in capsys.readouterr().out

    def test_an_endpoint_that_refuses_to_list_says_so_and_stops(self):
        refusal = APIError("no listing for you", request=None, body=None)
        with pytest.raises(ValueError, match="refused to list its models"):
            check_the_model(an_endpoint(fails=refusal), "gemma-4-31b-it")


class TestTakingTurns:
    """
    The rate limit kept by spacing the calls rather than counting them.

    Counting lets the threads through in a bunch and then holds all of them at
    the edge of the window and releases them together, which is the wave the
    endpoint refuses.
    """

    @pytest.fixture(autouse=True)
    def an_idle_process(self, monkeypatch):
        """No slot is taken yet, and none stays taken after the test."""
        monkeypatch.setattr(helper_functions, "_next_slot", 0.0)

    def take_a_slot(self, spacing: float) -> float:
        started = time.monotonic()
        wait_for_a_slot(spacing)
        return time.monotonic() - started

    def test_the_first_call_of_a_quiet_process_goes_out_at_once(self):
        assert self.take_a_slot(0.05) < 0.05

    def test_the_call_after_it_waits_for_its_turn(self):
        self.take_a_slot(0.05)
        assert self.take_a_slot(0.05) >= 0.04

    def test_no_two_threads_ever_get_the_same_turn(self):
        # they ask in the same instant, which is what the endpoint refuses
        taken = []
        together = threading.Barrier(4, timeout=10)

        def ask():
            together.wait()
            wait_for_a_slot(0.05)
            taken.append(time.monotonic())

        threads = [threading.Thread(target=ask) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        taken.sort()
        assert all(later - earlier >= 0.04 for earlier, later in zip(taken, taken[1:]))

    def test_a_quiet_minute_does_not_save_up_turns(self):
        # otherwise the wait would be followed by a burst of everything it saved
        helper_functions._next_slot = time.monotonic() - 60
        assert self.take_a_slot(0.05) < 0.05


class TestWaitingOutTheEndpoint:
    """
    Which failures are worth another answer.

    With several vitae in flight the endpoint queues them, so a request that
    never comes back says the queue was long, not that this vita cannot be
    answered -- and giving up on it would throw away a whole vita's work.
    """

    def answer(self, monkeypatch, failures: list, max_retries: int = 3, label: str = ""):
        """Call through `call_chat_ai` with an endpoint that fails like this."""
        remaining, calls, waits = list(failures), [], []

        def once(client, model, system_prompt, user_prompt, settings=None):
            calls.append(1)
            if remaining:
                raise remaining.pop(0)
            return {"choices": [{"message": {"content": "ok"}}]}

        monkeypatch.setattr(helper_functions, "_call_chat_ai_once", once)
        monkeypatch.setattr(helper_functions.time, "sleep", waits.append)
        try:
            response = call_chat_ai(None, "m", "system", "user", max_retries=max_retries,
                                    retry_wait=5, label=label)
        finally:
            self.calls, self.waits = len(calls), waits
        return response

    def test_a_read_timeout_is_waited_out(self, monkeypatch):
        response = self.answer(monkeypatch, [APITimeoutError(request=None)])
        assert response["retries"] == 1  # and the report can say it happened
        assert self.calls == 2

    def test_the_wait_grows_with_every_failure(self, monkeypatch):
        # all of these mean the endpoint has more work than it can take, so
        # asking again at the same pace is the one thing not to do
        self.answer(monkeypatch, [APITimeoutError(request=None),
                                  APITimeoutError(request=None)])
        first, second = self.waits
        assert 5 * 0.75 <= first <= 5 * 1.25
        assert 10 * 0.75 <= second <= 10 * 1.25
        assert second > first  # the jitter is never wide enough to undo the growth

    def test_two_requests_refused_together_do_not_come_back_together(self, monkeypatch):
        # they were refused in the same instant, so an exact wait would have
        # them arrive in the same instant too, and be refused again
        waits = set()
        for _ in range(10):
            self.answer(monkeypatch, [APITimeoutError(request=None)])
            waits.add(self.waits[0])
        assert len(waits) > 1

    def test_an_endpoint_that_never_comes_back_is_reported(self, monkeypatch):
        with pytest.raises(APITimeoutError):
            self.answer(monkeypatch, [APITimeoutError(request=None)] * 9, max_retries=2)
        assert self.calls == 3  # the first try and its two retries

    def test_an_answer_at_the_first_try_says_it_waited_for_nothing(self, monkeypatch):
        assert self.answer(monkeypatch, [])["retries"] == 0

    def test_the_waiting_says_what_it_is_waiting_for(self, monkeypatch, capsys):
        self.answer(monkeypatch, [APITimeoutError(request=None)], label="2/370")
        assert "2/370: server error (APITimeoutError)" in capsys.readouterr().out

    def test_without_a_caller_to_name_the_line_still_reads(self, monkeypatch, capsys):
        self.answer(monkeypatch, [APITimeoutError(request=None)])
        assert re.search(r"server error \(APITimeoutError\), retrying in \d\.\ds \(1/3\)",
                         capsys.readouterr().out)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
