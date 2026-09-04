#!/usr/bin/env python3
"""
Test suite for the runner of steps 2-4.

The per-step work is tested by tests_multiple_choice.py, tests_expand_rest.py
and tests_normalize.py; what is tested here is the loop around them:

- the retry on an unparseable model answer, and the count of what it cost
- the thinking settings, from the arguments to the log line
- the workers: several vitae in flight at once, all of them recorded, and
  what happens to the batch when the endpoint gives up on one of them
- the checkpoint: what it records, that a resumed run skips it, and that it
  knows which model wrote it
- the assembly of the output CSV, including the vitae with nothing to do
- the report counts
"""


import json
import os
import re
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import polars as pl
import pytest
from openai import APIError

import run_step

from helper_functions import thinking_kwargs

from run_step import (
    Run,
    Step,
    append_checkpoint,
    ask,
    checkpoint_head,
    assemble,
    describe_reasoning,
    process_vita,
    read_checkpoint,
    read_checkpoint_head,
    render_report,
    start_checkpoint,
    run_batch,
)

# one row per vita: a header and no regest, as text_to_vita_df writes it. The
# schema is spelled out because an all-null column would otherwise be typed Null
# and the counting in the report expects strings, as the real CSVs have them.
SOURCE = pl.DataFrame(
    {
        "volume": [2, 2, 3],
        "nr_RG": [370, 371, 12],
        "nr_suffix": [0, 0, 0],
        "header_no_tags": ["eccl. mai.", "s. Aug.", "op. Halberstad."],
        "regest_no_tags": [None, None, None],
        "id_RG_all": ["102000370-0", "102000371-0", "103000012-0"],
    },
    schema={"volume": pl.Int64, "nr_RG": pl.Int64, "nr_suffix": pl.Int64,
            "header_no_tags": pl.String, "regest_no_tags": pl.String,
            "id_RG_all": pl.String},
)

STEP = Step(2, "twice", "a prompt", lambda run: None)


def make_run(process, workers: int = 1) -> Run:
    run = Run(step=STEP, model="a-model", name="a-run", source=SOURCE, workers=workers,
              ids=SOURCE.select("volume", "nr_RG").unique().sort(by="*"))
    run.process = process
    return run


class TestAsk:
    def test_the_first_parseable_answer_is_taken(self):
        calls = []

        def call(client, model, system, user, settings=None, label=""):
            calls.append(settings)
            return {"choices": [{"message": {"content": "{}"}}]}

        import run_step
        run_step.call_chat_ai = call
        result = ask(None, "m", "system", "user", lambda content: ({1: "a"}, None, []), 5,
                     thinking_kwargs("gemma-4-31b-it", thinking=False))
        assert result[0] == {1: "a"}
        assert len(calls) == 1  # no retry once it parses
        assert calls == [thinking_kwargs("gemma-4-31b-it", thinking=False)]  # passed on

    def test_an_unparseable_answer_is_retried_and_then_given_up_on(self):
        calls = []

        def call(client, model, system, user, settings=None, label=""):
            calls.append(user)
            return {"choices": [{"message": {"content": "sorry"}}]}

        import run_step
        run_step.call_chat_ai = call
        choices, _, errors, effort = ask(None, "m", "system", "user",
                                        lambda content: (None, None, [{"message": "no JSON"}]), 3)
        assert choices is None  # the caller leaves the text alone
        assert len(calls) == 3
        assert errors == [{"message": "no JSON"}]
        assert effort == {"tries": 3, "server_retries": 0, "readable": False}


class TestWhatAnAnswerCost:
    """What `ask` reports about itself, so a slow step can be diagnosed."""

    def answers(self, contents: list[str], retries: int = 0) -> dict:
        """Ask with a model that gives these answers in turn."""
        replies = iter(contents)
        self.labels = []

        def call(client, model, system, user, settings=None, label=""):
            self.labels.append(label)
            return {"choices": [{"message": {"content": next(replies)}}],
                    "retries": retries}

        run_step.call_chat_ai = call
        parse = lambda content: (({1: "a"}, None, []) if content == "ok"
                                 else (None, None, [{"message": "no JSON"}]))
        return ask(None, "m", "system", "user", parse, 5, label="2/370")[3]

    def test_an_answer_at_the_first_try_costs_one(self):
        assert self.answers(["ok"])["tries"] == 1

    def test_every_unreadable_answer_is_counted(self):
        effort = self.answers(["sorry", "sorry", "ok"])
        assert effort["tries"] == 3
        assert effort["readable"] is True

    def test_the_server_errors_waited_out_are_counted_too(self):
        # a slow endpoint and a model that cannot keep to the format are both
        # slow, and only these two numbers tell them apart
        effort = self.answers(["sorry", "ok"], retries=2)
        assert (effort["tries"], effort["server_retries"]) == (2, 4)

    def test_the_vita_is_named_to_whatever_does_the_waiting(self):
        # with ten vitae in flight, one retried five times and five retried
        # once print the same five lines unless they say which vita they are
        self.answers(["sorry", "ok"])
        assert self.labels == ["2/370", "2/370"]

    def test_a_vita_is_timed(self):
        run = make_run(lambda volume, nr: {"text": "t", "record": {"errors": []}})
        entry = process_vita(run, (2, 370))
        assert entry["record"]["effort"]["seconds"] >= 0

    def test_a_vita_with_nothing_to_do_is_not_timed(self):
        assert process_vita(make_run(lambda volume, nr: None), (2, 370))["record"] is None


class TestDescribeReasoning:
    """What the log line and the report say about the model's thinking."""

    def described(self, **arguments) -> str:
        return describe_reasoning(Run(step=STEP, model="gemma-4-31b-it", **arguments))

    def test_nothing_asked_for_leaves_the_model_to_itself(self):
        assert self.described() == "thinking left at the model's default"

    def test_thinking_can_be_turned_off(self):
        assert self.described(thinking=False) == "thinking off"

    def test_an_effort_is_named(self):
        assert self.described(reasoning_effort="max") == "thinking on, effort max"


class TestCheckpoint:
    def test_what_is_written_is_read_back(self, tmp_path):
        path = tmp_path / "step2.jsonl"
        append_checkpoint(path, [{"volume": 2, "nr_RG": 370, "text": "a", "record": None}])
        append_checkpoint(path, [{"volume": 3, "nr_RG": 12, "text": None, "record": {"x": 1}}])
        done = read_checkpoint(path)
        assert set(done) == {(2, 370), (3, 12)}
        assert done[(3, 12)]["record"] == {"x": 1}

    def test_a_missing_checkpoint_is_an_empty_run(self, tmp_path):
        assert read_checkpoint(tmp_path / "nothing.jsonl") == {}

    def test_the_batch_writes_every_vita(self, tmp_path):
        path = tmp_path / "step2.jsonl"
        run = make_run(lambda volume, nr: {"text": f"{volume}/{nr}", "record": {"errors": []}})
        run_batch(run, {}, path, every=2, limit=None)
        assert len(read_checkpoint(path)) == 3  # the last batch is flushed too

    def test_a_resumed_run_skips_what_is_done(self, tmp_path):
        path = tmp_path / "step2.jsonl"
        seen = []

        def process(volume, nr):
            seen.append((volume, nr))
            return {"text": "new", "record": {"errors": []}}

        done = {(2, 370): {"volume": 2, "nr_RG": 370, "text": "old", "record": None}}
        run_batch(make_run(process), done, path, every=10, limit=None)
        assert seen == [(2, 371), (3, 12)]

    def test_the_limit_stops_the_batch_early(self, tmp_path):
        seen = []

        def process(volume, nr):
            seen.append((volume, nr))
            return {"text": "new", "record": {"errors": []}}

        run_batch(make_run(process), {}, tmp_path / "step2.jsonl", every=10, limit=1)
        assert seen == [(2, 370)]


class TestWorkers:
    """Several vitae in flight at once, and every one of them recorded."""

    def test_every_vita_is_processed_and_checkpointed(self, tmp_path):
        path = tmp_path / "step2.jsonl"
        run = make_run(lambda volume, nr: {"text": f"{volume}/{nr}",
                                           "record": {"errors": []}}, workers=3)
        done = run_batch(run, {}, path, every=10, limit=None)
        assert set(done) == {(2, 370), (2, 371), (3, 12)}
        assert set(read_checkpoint(path)) == set(done)

    def test_the_vitae_really_do_overlap(self, tmp_path):
        # every vita waits for the other two, which can only be reached if all
        # three are in flight together -- a sequential loop deadlocks and the
        # barrier breaks instead of the test hanging
        together = threading.Barrier(3, timeout=10)

        def process(volume, nr):
            together.wait()
            return {"text": "t", "record": {"errors": []}}

        run = make_run(process, workers=3)
        done = run_batch(run, {}, tmp_path / "step2.jsonl", every=10, limit=None)
        assert len(done) == 3

    def test_a_worker_that_raises_keeps_what_is_already_paid_for(self, tmp_path):
        path = tmp_path / "step2.jsonl"

        def process(volume, nr):
            if (volume, nr) == (3, 12):
                raise RuntimeError("a bug in here, not a bad answer")
            return {"text": "t", "record": {"errors": []}}

        with pytest.raises(RuntimeError):  # our own fault: not for the batch to absorb
            run_batch(make_run(process), {}, path, every=10, limit=None)
        assert set(read_checkpoint(path)) == {(2, 370), (2, 371)}


class TestWhenTheEndpointGivesUp:
    """
    A vita the endpoint never answered for is not a result and not a reason to
    lose the rest of the batch: it is simply not done, so a resume asks again.
    """

    def failing(self, keys: set):
        def process(volume, nr):
            if (volume, nr) in keys:
                raise APIError("Request timed out.", None, body=None)
            return {"text": "t", "record": {"errors": []}}
        return process

    def test_the_others_are_finished_and_the_failure_is_left_out(self, tmp_path, capsys):
        path = tmp_path / "step2.jsonl"
        done = run_batch(make_run(self.failing({(2, 371)})), {}, path, every=10, limit=None)
        assert set(done) == {(2, 370), (3, 12)}
        assert set(read_checkpoint(path)) == {(2, 370), (3, 12)}
        assert "2/371" in capsys.readouterr().out  # and it says which one

    def test_a_failure_is_not_recorded_as_an_empty_answer(self, tmp_path):
        # a vita recorded with no text would be written to the output as it
        # stands and never asked about again -- the one outcome to avoid
        run_batch(make_run(self.failing({(2, 371)})), {}, tmp_path / "step2.jsonl",
                  every=1, limit=None)
        assert (2, 371) not in read_checkpoint(tmp_path / "step2.jsonl")

    def test_a_run_of_failures_stops_the_batch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_step, "MAX_FAILURES", 1)
        seen = []

        def process(volume, nr):
            seen.append((volume, nr))
            raise APIError("Request timed out.", None, body=None)

        run_batch(make_run(process), {}, tmp_path / "step2.jsonl", every=10, limit=None)
        assert len(seen) < 3  # what was never submitted is never asked for

    def test_the_vitae_kept_after_an_interruption_go_on_counting(self, tmp_path, capsys):
        # they are finished, not abandoned, so they carry the same [n/total] as
        # every other line rather than arriving as a bare list of numbers
        def process(volume, nr):
            if (volume, nr) == (2, 370):
                raise KeyboardInterrupt
            time.sleep(0.2)
            return {"text": "t", "record": {"errors": []}}

        with pytest.raises(SystemExit):
            run_batch(make_run(process, workers=2), {}, tmp_path / "step2.jsonl",
                      every=10, limit=None)
        printed = capsys.readouterr().out
        assert "vitae are answered or in flight" in printed
        after = printed.split("vitae are answered or in flight")[1]
        kept = [line for line in after.splitlines() if line.startswith("  ")]
        assert kept  # the wait was not for nothing
        assert all(re.match(r"  \[\d+/3\] \d+/\d+", line) for line in kept), kept

    def test_being_asked_twice_leaves_without_waiting(self, tmp_path, monkeypatch):
        # the answers that are out are paid for, but a wait of a quarter of an
        # hour is not what someone shutting their machine down asked for
        path = tmp_path / "step2.jsonl"
        stopped = []

        def stop(message):
            stopped.append(message)
            raise SystemExit(message)  # the real one does not come back either

        class AskedAgain(ThreadPoolExecutor):
            """Ctrl+C a second time, while the vitae in flight are waited for."""

            def shutdown(self, *args, **kwargs):
                os.kill(os.getpid(), signal.SIGINT)
                return super().shutdown(*args, **kwargs)

        monkeypatch.setattr(run_step, "stop_now", stop)
        monkeypatch.setattr(run_step, "ThreadPoolExecutor", AskedAgain)

        def process(volume, nr):
            if (volume, nr) == (3, 12):
                os.kill(os.getpid(), signal.SIGINT)  # the first one, from a worker
                time.sleep(0.5)
            return {"text": "t", "record": {"errors": []}}

        with pytest.raises(SystemExit):
            run_batch(make_run(process), {}, path, every=10, limit=None)
        assert stopped and "--resume" in stopped[0]
        assert (2, 370) in read_checkpoint(path)  # what was answered is still written

    def test_a_line_cut_short_by_the_leaving_is_left_out(self, tmp_path, capsys):
        # leaving at once can take the process mid-line, and one half-written
        # vita must not make the hundred before it unreadable
        path = tmp_path / "step2.jsonl"
        path.write_text('{"run": "a-run"}\n'
                        '{"volume": 2, "nr_RG": 370, "text": "t", "record": null}\n'
                        '{"volume": 2, "nr_RG": 371, "te', encoding="utf-8")
        assert set(read_checkpoint(path)) == {(2, 370)}
        assert "cut short" in capsys.readouterr().out

    def test_a_broken_line_anywhere_else_is_not_swallowed(self, tmp_path):
        path = tmp_path / "step2.jsonl"
        path.write_text('{"run": "a-run"}\n'
                        '{"volume": 2, "nr_R\n'
                        '{"volume": 2, "nr_RG": 371, "text": "t", "record": null}\n',
                        encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            read_checkpoint(path)

    def test_the_handler_is_given_back_when_the_batch_is_over(self, tmp_path):
        # the batch borrows Ctrl+C; a notebook or a test after it must not find
        # itself unable to interrupt anything
        before = signal.getsignal(signal.SIGINT)
        run_batch(make_run(lambda volume, nr: None), {}, tmp_path / "step2.jsonl",
                  every=10, limit=None)
        assert signal.getsignal(signal.SIGINT) is before

    def test_the_first_interruption_says_how_to_stop_at_once(self, tmp_path, capsys):
        def process(volume, nr):
            if (volume, nr) == (2, 370):
                raise KeyboardInterrupt
            time.sleep(0.2)
            return {"text": "t", "record": {"errors": []}}

        with pytest.raises(SystemExit):
            run_batch(make_run(process, workers=2), {}, tmp_path / "step2.jsonl",
                      every=10, limit=None)
        assert "Ctrl+C again" in capsys.readouterr().out

    def test_an_interruption_still_keeps_what_is_answered(self, tmp_path):
        path = tmp_path / "step2.jsonl"

        def process(volume, nr):
            if (volume, nr) == (3, 12):
                raise KeyboardInterrupt
            return {"text": "t", "record": {"errors": []}}

        with pytest.raises(SystemExit):
            run_batch(make_run(process), {}, path, every=10, limit=None)
        assert set(read_checkpoint(path)) == {(2, 370), (2, 371)}


class TestAssemble:
    def test_a_vita_with_nothing_to_do_passes_through_unchanged(self):
        run = make_run(lambda volume, nr: None)
        done = {key: {"volume": key[0], "nr_RG": key[1], "text": None, "record": None}
                for key in run.keys()}
        expanded, results = assemble(run, done)
        assert results == []
        assert expanded.sort(["volume", "nr_RG"]).equals(SOURCE.sort(["volume", "nr_RG"]))

    def test_a_processed_vita_is_rebuilt_from_its_text(self):
        run = make_run(lambda volume, nr: None)
        done = {(2, 370): {"volume": 2, "nr_RG": 370, "text": "ecclesia maior",
                           "record": {"volume": 2, "nr_RG": 370}},
                (2, 371): {"volume": 2, "nr_RG": 371, "text": None, "record": None},
                (3, 12): {"volume": 3, "nr_RG": 12, "text": None, "record": None}}
        expanded, results = assemble(run, done)
        row = expanded.filter((pl.col("volume") == 2) & (pl.col("nr_RG") == 370))
        assert row.get_column("header_no_tags").item() == "ecclesia maior"
        assert results == [{"volume": 2, "nr_RG": 370}]


class TestCheckpointHead:
    """The first line of a checkpoint says whose it is."""

    def test_it_names_the_run_and_what_it_was_run_with(self):
        head = checkpoint_head(make_run(lambda volume, nr: None))
        assert head["run"] == "a-run" and head["model"] == "a-model" and head["step"] == 2

    def test_it_is_written_once_and_read_back(self, tmp_path):
        path = tmp_path / "step2.jsonl"
        head = checkpoint_head(make_run(lambda volume, nr: None))
        start_checkpoint(path, head)
        start_checkpoint(path, {"run": "someone-else"})  # an existing one is left alone
        assert read_checkpoint_head(path) == head

    def test_the_vitae_are_read_past_it(self, tmp_path):
        path = tmp_path / "step2.jsonl"
        start_checkpoint(path, checkpoint_head(make_run(lambda volume, nr: None)))
        append_checkpoint(path, [{"volume": 2, "nr_RG": 370, "text": "a", "record": None}])
        assert set(read_checkpoint(path)) == {(2, 370)}

    def test_a_checkpoint_from_before_the_head_is_read_as_it_is(self, tmp_path):
        path = tmp_path / "step2.jsonl"
        append_checkpoint(path, [{"volume": 2, "nr_RG": 370, "text": "a", "record": None}])
        assert read_checkpoint_head(path) is None
        assert set(read_checkpoint(path)) == {(2, 370)}


class TestReport:
    @pytest.fixture
    def run(self):
        return make_run(lambda volume, nr: None)

    def test_the_tiers_and_errors_are_counted(self, run):
        results = [{
            "details": [{"tier": "suggestion"}, {"tier": "free"}, {"tier": "suggestion"}],
            "errors": [{"message": "Rejected expansion: [[3]] 'x'"}],
        }]
        report = render_report(run, SOURCE, results)
        assert "| suggestion | 2 |" in report
        assert "| free | 1 |" in report
        assert "| Rejected expansion | 1 |" in report

    def test_the_choices_of_step_2_are_counted(self, run):
        results = [{"choices": [{"choice": "dominus"}, {"choice": None}], "errors": []}]
        report = render_report(run, SOURCE, results)
        assert "| chosen | 1 |" in report
        assert "| left standing | 1 |" in report

    def test_the_changes_of_step_4_are_listed(self, run):
        results = [{"details": [
            {"tier": "changed", "word": "annus", "form": "annis"},
            {"tier": "changed", "word": "annus", "form": "annis"},
            {"tier": "kept", "word": "ecclesia", "form": "ecclesia"},
        ], "errors": []}]
        report = render_report(run, SOURCE, results)
        assert "| `annus -> annis` | 2 |" in report

    def test_the_model_is_named(self, run):
        assert "`a-model`" in render_report(run, SOURCE, [])

    def test_the_tries_per_vita_are_averaged(self, run):
        results = [{"errors": [], "effort": {"tries": 1, "server_retries": 0,
                                             "readable": True, "seconds": 10.0}},
                   {"errors": [], "effort": {"tries": 3, "server_retries": 0,
                                             "readable": True, "seconds": 30.0}}]
        report = render_report(run, SOURCE, results)
        assert "| answers | 4, 2.00 per vita |" in report
        assert "| vitae that took more than one | 1, at worst 3 answers |" in report
        assert "| seconds per answer | 10.0 |" in report

    def test_the_pace_is_stated_against_the_rate_limit(self, run):
        results = [{"errors": [], "effort": {"tries": 1, "server_retries": 0,
                                             "readable": True, "seconds": 60.0}}]
        assert "about 1.0 at 1 vita(e) at a time" in render_report(run, SOURCE, results)

    def test_the_server_errors_are_only_mentioned_where_there_were_any(self, run):
        quiet = [{"errors": [], "effort": {"tries": 1, "server_retries": 0,
                                           "readable": True, "seconds": 1.0}}]
        assert "server errors waited out" not in render_report(run, SOURCE, quiet)
        noisy = [{"errors": [], "effort": {"tries": 1, "server_retries": 4,
                                           "readable": True, "seconds": 1.0}}]
        assert "| server errors waited out | 4 |" in render_report(run, SOURCE, noisy)

    def test_a_run_from_before_the_counting_has_no_effort_section(self, run):
        assert "## Effort" not in render_report(run, SOURCE, [{"errors": []}])

    def test_more_workers_are_more_answers_a_minute(self, run):
        results = [{"errors": [], "effort": {"tries": 1, "server_retries": 0,
                                             "readable": True, "seconds": 60.0}}]
        run.workers = 5
        assert "about 5.0 at 5 vita(e) at a time" in render_report(run, SOURCE, results)
