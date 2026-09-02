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

import polars as pl
import pytest
from openai import APITimeoutError

import helper_functions
from helper_functions import (
    VITA_SCHEMA,
    call_chat_ai,
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

    def test_an_unknown_model_is_not_guessed_at(self):
        with pytest.raises(ValueError, match="no thinking style known"):
            thinking_kwargs("apertus-70b-instruct-2509", thinking=False)

    def test_an_unknown_model_without_a_setting_is_left_alone(self):
        assert thinking_kwargs("apertus-70b-instruct-2509") == {}


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
        assert self.waits == [5, 10]

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
        assert "server error (APITimeoutError), retrying in 5s (1/3)" in capsys.readouterr().out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
