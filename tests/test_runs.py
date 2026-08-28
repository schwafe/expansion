#!/usr/bin/env python3
"""
Test suite for the layout of the runs.

The point of `runs.py` is that a step's output can never be confused with the
same step run by another model, and that whatever produced the input of a step
stays readable afterwards. So what is tested is the naming, the resolution of a
step's input -- including every way it can fail -- and the manifest that keeps
the chain together when a run builds on another one.
"""

import json

import pytest

import runs


@pytest.fixture(autouse=True)
def in_a_temporary_data_dir(tmp_path, monkeypatch):
    """Every test gets its own data/, so nothing here touches the real one."""
    monkeypatch.setattr(runs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(runs, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(runs, "STEP1", tmp_path / "step1.csv")
    (tmp_path / "step1.csv").write_text("volume,nr_RG\n", encoding="utf-8")
    return tmp_path


def produce(run: str, step: int, model: str = "a-model", parent: str | None = None) -> None:
    """A step's worth of bookkeeping, without the model calls."""
    source, inherited = runs.resolve_input(run, step, parent)
    runs.record(run, step, inherited, model=model, thinking=None, reasoning_effort=None,
                prompt_sha1="abc", input=str(source),
                output=str(runs.output_path(run, step)), vitae=156)


class TestSlug:
    def test_a_plain_model_is_its_own_name(self):
        assert runs.slug("gemma-4-31b-it") == "gemma-4-31b-it"

    def test_the_switch_is_part_of_the_name(self):
        assert runs.slug("gemma-4-31b-it", thinking=False) == "gemma-4-31b-it-nothink"
        assert runs.slug("gemma-4-31b-it", thinking=True) == "gemma-4-31b-it-think"

    def test_a_level_replaces_the_switch_it_implies(self):
        assert runs.slug("qwen3.8-27b", thinking=True, reasoning_effort="low") == "qwen3.8-27b-low"

    def test_two_settings_of_one_model_cannot_collide(self):
        names = {runs.slug("m"), runs.slug("m", thinking=False), runs.slug("m", thinking=True),
                 runs.slug("m", reasoning_effort="low"), runs.slug("m", reasoning_effort="high")}
        assert len(names) == 5


class TestResolveInput:
    def test_step_two_reads_the_rule_based_expansion(self):
        source, inherited = runs.resolve_input("whatever", 2)
        assert source == runs.STEP1
        assert inherited["1"]["model"] is None  # step 1 has no model to speak of

    def test_step_two_takes_no_parent(self):
        with pytest.raises(ValueError, match="--from does not apply"):
            runs.resolve_input("a-run", 2, parent="another-run")

    def test_a_later_step_reads_the_step_before_it(self):
        produce("a-run", 2)
        source, _ = runs.resolve_input("a-run", 3)
        assert source == runs.output_path("a-run", 2)

    def test_a_parent_provides_what_this_run_has_not_got(self):
        produce("gemma", 2)
        produce("gemma", 3)
        source, inherited = runs.resolve_input("qwen-nothink", 4, parent="gemma")
        assert source == runs.output_path("gemma", 3)
        assert set(inherited) == {"1", "2", "3"}  # the whole chain comes along

    def test_a_missing_input_names_the_runs_that_have_one(self):
        produce("gemma", 2)
        with pytest.raises(LookupError, match="these have one: gemma"):
            runs.resolve_input("qwen-nothink", 3)

    def test_a_missing_input_says_so_when_nothing_has_one(self):
        with pytest.raises(LookupError, match="run step 2 first"):
            runs.resolve_input("qwen-nothink", 3)

    def test_a_missing_step_one_is_reported_rather_than_read(self, in_a_temporary_data_dir):
        runs.STEP1.unlink()
        with pytest.raises(LookupError, match="expand_simple"):
            runs.resolve_input("a-run", 2)


class TestManifest:
    def test_a_run_records_the_chain_it_produced(self):
        produce("gemma", 2)
        produce("gemma", 3)
        assert [number for number, _ in runs.chain("gemma")] == [1, 2, 3]
        assert runs.chain("gemma")[2][1]["input"] == str(runs.output_path("gemma", 2))

    def test_an_inherited_step_keeps_the_run_that_produced_it(self):
        produce("gemma", 2)
        produce("gemma", 3)
        produce("qwen-nothink", 4, model="qwen3.8-27b", parent="gemma")
        steps = dict(runs.chain("qwen-nothink"))
        assert steps[3]["run"] == "gemma"  # not this run, though its manifest lists it
        assert steps[4]["run"] == "qwen-nothink"
        assert steps[4]["model"] == "qwen3.8-27b"

    def test_a_rerun_replaces_only_its_own_step(self):
        produce("gemma", 2)
        produce("gemma", 3)
        produce("gemma", 2, model="another-model")
        steps = dict(runs.chain("gemma"))
        assert steps[2]["model"] == "another-model"
        assert steps[3]["model"] == "a-model"  # untouched

    def test_the_manifest_is_readable_json_on_disk(self):
        produce("gemma", 2)
        written = json.loads(runs.manifest_path("gemma").read_text(encoding="utf-8"))
        assert written["run"] == "gemma"
        assert written["steps"]["2"]["vitae"] == 156

    def test_a_run_that_does_not_exist_yet_is_empty_rather_than_an_error(self):
        assert runs.read_manifest("nothing-here")["steps"] == {}

    def test_the_prompt_of_the_last_time_can_be_looked_up(self):
        produce("gemma", 2)
        assert runs.previous_prompt("gemma", 2) == "abc"
        assert runs.previous_prompt("gemma", 4) is None


class TestTheRun:
    """Which run a reader means, when it does not say."""

    def test_the_only_run_needs_no_naming(self):
        produce("gemma", 2)
        assert runs.the_run(None) == "gemma"

    def test_several_runs_have_to_be_told_apart(self):
        produce("gemma", 2)
        produce("qwen-nothink", 2)
        with pytest.raises(LookupError, match="which one"):
            runs.the_run(None)

    def test_a_named_run_that_does_not_exist_lists_the_ones_that_do(self):
        produce("gemma", 2)
        with pytest.raises(LookupError, match="there is: gemma"):
            runs.the_run("typo")

    def test_no_run_at_all_says_what_to_do(self):
        with pytest.raises(LookupError, match="run_step.py 2"):
            runs.the_run(None)


class TestPaths:
    def test_every_run_has_its_own_checkpoint(self):
        assert runs.checkpoint_path("gemma", 2) != runs.checkpoint_path("qwen-nothink", 2)

    def test_the_files_of_a_step_sit_together(self):
        assert runs.output_path("gemma", 2).parent == runs.run_dir("gemma")
        assert runs.dump_path("gemma", 2).parent == runs.run_dir("gemma")
        assert runs.report_path("gemma", 2).parent == runs.run_dir("gemma")

    def test_only_runs_with_a_manifest_are_listed(self, in_a_temporary_data_dir):
        produce("gemma", 2)
        (in_a_temporary_data_dir / "runs" / "half-a-run").mkdir()
        assert runs.existing_runs() == ["gemma"]
        assert runs.runs_with(2) == ["gemma"]
        assert runs.runs_with(3) == []
