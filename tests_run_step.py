#!/usr/bin/env python3
"""
Test suite for the runner of steps 2-4.

The per-step work is tested by tests_multiple_choice.py, tests_expand_rest.py
and tests_normalize.py; what is tested here is the loop around them:

- the retry on an unparseable model answer
- the checkpoint: what it records, and that a resumed run skips it
- the assembly of the output CSV, including the vitae with nothing to do
- the report counts
"""


import polars as pl
import pytest

from run_step import (
    Run,
    Step,
    append_checkpoint,
    ask,
    assemble,
    read_checkpoint,
    render_report,
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

STEP = Step(2, "twice", None, None, None, "a prompt", lambda run: None)


def make_run(process) -> Run:
    run = Run(step=STEP, model="a-model", source=SOURCE,
              ids=SOURCE.select("volume", "nr_RG").unique().sort(by="*"))
    run.process = process
    return run


class TestAsk:
    def test_the_first_parseable_answer_is_taken(self):
        calls = []

        def call(client, model, system, user):
            calls.append(user)
            return {"choices": [{"message": {"content": "{}"}}]}

        import run_step
        run_step.call_chat_ai = call
        result = ask(None, "m", "system", "user", lambda content: ({1: "a"}, None, []), 5)
        assert result[0] == {1: "a"}
        assert len(calls) == 1  # no retry once it parses

    def test_an_unparseable_answer_is_retried_and_then_given_up_on(self):
        calls = []

        def call(client, model, system, user):
            calls.append(user)
            return {"choices": [{"message": {"content": "sorry"}}]}

        import run_step
        run_step.call_chat_ai = call
        choices, _, errors = ask(None, "m", "system", "user",
                                 lambda content: (None, None, [{"message": "no JSON"}]), 3)
        assert choices is None  # the caller leaves the text alone
        assert len(calls) == 3
        assert errors == [{"message": "no JSON"}]


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
