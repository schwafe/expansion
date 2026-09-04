#!/usr/bin/env python3
"""
Where the output of a run lives, and what produced it.

Steps 2-4 are worth running with different models and different thinking
settings, and the interesting comparisons mix them -- one model for the choices,
another for the grammar. So the output of a step is not one file but one per
run: `data/runs/<run>/step<n>.csv`, next to a manifest that names, for every
step up to that one, the model, its settings, the prompt and the file it read.

A run is named after the model and the settings of the step that started it, so
the common case -- the whole workflow with one model -- needs no name at all. A
step whose input comes from another run inherits that run's manifest entries, so
every manifest describes a complete chain from step 1 onwards, whoever produced
the earlier links:

    data/runs/gemma-4-31b-it/
        manifest.json
        step2.csv  step2.json  step2_report.md
        step3.csv  step3.json  step3_report.md
    data/runs/qwen3.8-27b-nothink/
        manifest.json                    # steps 2-3 inherited from gemma-4-31b-it
        step4.csv  step4.json  step4_report.md

Step 1 is rule-based and the same for every run, so it stays at `data/step1.csv`
and is only recorded as the first link of every chain.

A run that has a step of its own and then takes a later one from elsewhere holds
two chains rather than one, and its step numbers no longer say what was built on
what. Every entry records the file it read, so `lineage` follows that backwards
instead -- use it, not `chain`, wherever what produced a step is the question.
"""

import json
from pathlib import Path

DATA_DIR = Path("data")
RUNS_DIR = DATA_DIR / "runs"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
STEP1 = DATA_DIR / "step1.csv"  # the rule-based expansion, model-free

FIRST_MODEL_STEP = 2
MANIFEST = "manifest.json"


def slug(model: str, thinking: bool | None = None,
         reasoning_effort: str | None = None) -> str:
    """
    The default name of a run: the model, and what was asked of its thinking.

    A level implies thinking, so the two never both show up in the name.
    """
    if reasoning_effort is not None:
        return f"{model}-{reasoning_effort}"
    if thinking is None:
        return model
    return f"{model}-think" if thinking else f"{model}-nothink"


def run_dir(run: str) -> Path:
    return RUNS_DIR / run


def output_path(run: str, step: int) -> Path:
    return run_dir(run) / f"step{step}.csv"


def dump_path(run: str, step: int) -> Path:
    return run_dir(run) / f"step{step}.json"


def report_path(run: str, step: int) -> Path:
    return run_dir(run) / f"step{step}_report.md"


def checkpoint_path(run: str, step: int) -> Path:
    return CHECKPOINT_DIR / run / f"step{step}.jsonl"


def manifest_path(run: str) -> Path:
    return run_dir(run) / MANIFEST


def read_manifest(run: str) -> dict:
    """What a run has produced so far; empty for a run that does not exist yet."""
    path = manifest_path(run)
    if not path.exists():
        return {"run": run, "steps": {}}
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def write_manifest(run: str, manifest: dict) -> None:
    path = manifest_path(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)
        file.write("\n")


def existing_runs() -> list[str]:
    """Every run that has a manifest, in alphabetical order."""
    if not RUNS_DIR.exists():
        return []
    return sorted(path.name for path in RUNS_DIR.iterdir()
                  if (path / MANIFEST).exists())


def runs_with(step: int) -> list[str]:
    """The runs whose chain reaches a given step -- the candidates for `--from`."""
    return [run for run in existing_runs() if str(step) in read_manifest(run)["steps"]]


def step1_entry() -> dict:
    """The first link of every chain: rule-based, so no model and no run."""
    return {"run": None, "model": None, "output": str(STEP1)}


def resolve_input(run: str, step: int, parent: str | None = None) -> tuple[Path, dict]:
    """
    The file a step reads, and the manifest entries that come with it.

    Step 2 always reads the rule-based expansion. Every later step reads the
    output of the step before it -- from this run, or from the run named by
    `parent`, whose earlier entries are then inherited so that this run's
    manifest still describes the whole chain.
    """
    if step == FIRST_MODEL_STEP:
        if parent is not None:
            raise ValueError(f"step {step} always reads {STEP1}, so --from does not apply")
        if not STEP1.exists():
            raise LookupError(f"{STEP1} is missing -- run `python expand_simple.py --write` first")
        return STEP1, {"1": step1_entry()}

    source = parent if parent is not None else run
    steps = read_manifest(source)["steps"]
    if str(step - 1) not in steps:
        available = runs_with(step - 1)
        raise LookupError(
            f"run {source!r} has no step {step - 1} to build on. Pass --from <run>; "
            + (f"these have one: {', '.join(available)}" if available
               else f"no run has one yet, so run step {step - 1} first")
        )
    inherited = {number: entry for number, entry in steps.items() if int(number) < step}
    return Path(steps[str(step - 1)]["output"]), inherited


def record(run: str, step: int, inherited: dict, **entry) -> dict:
    """Write what this step did into the run's manifest, keeping the chain."""
    manifest = read_manifest(run)
    manifest["run"] = run
    manifest["steps"] = {**inherited, **manifest["steps"], **{str(step): {"run": run, **entry}}}
    manifest["steps"] = dict(sorted(manifest["steps"].items(), key=lambda item: int(item[0])))
    write_manifest(run, manifest)
    return manifest


def the_run(name: str | None) -> str:
    """
    Which run a reader means: the one it named, or the only one there is.

    Guessing between several would silently score or publish the wrong model's
    output, so with more than one run the caller has to say.
    """
    if name is not None:
        if not manifest_path(name).exists():
            known = ", ".join(existing_runs()) or "none yet"
            raise LookupError(f"no run {name!r} in {RUNS_DIR} (there is: {known})")
        return name
    available = existing_runs()
    if len(available) == 1:
        return available[0]
    if not available:
        raise LookupError(f"no run in {RUNS_DIR} yet -- "
                          "run `python run_step.py 2 --no-thinking` first")
    raise LookupError("several runs, so which one? " + ", ".join(available))


def chain(run: str) -> list[tuple[int, dict]]:
    """Every step a run's manifest lists, in order, each with what produced it."""
    steps = read_manifest(run)["steps"]
    return [(int(number), steps[number]) for number in sorted(steps, key=int)]


def produced(path: str | Path) -> tuple[int, dict] | None:
    """The step and the manifest entry that wrote a file, whichever run that was."""
    path = Path(path)
    if path == STEP1:
        return 1, step1_entry()
    if path.parent.parent != RUNS_DIR:
        return None
    for number, entry in read_manifest(path.parent.name)["steps"].items():
        if entry.get("output") and Path(entry["output"]) == path:
            return int(number), entry
    return None


def lineage(run: str, step: int | None = None) -> list[tuple[int, dict]]:
    """
    What actually produced a step: its own entry, and every file behind it.

    Not the same as `chain`. A manifest lists everything a run has produced, and
    after a `--from` that need not be one chain: a run can have a step 2 of its
    own and a step 3 that read another run's, and then the step number a step
    carries no longer says what it was built on. So the chain of a step is
    followed backwards through the file each step recorded reading, which is
    what it was really given. `step` defaults to the last one the run reached.
    """
    steps = read_manifest(run)["steps"]
    if step is None:
        step = max((int(number) for number in steps), default=0)
    if str(step) not in steps:
        return []
    number, entry = step, steps[str(step)]
    found, seen = [(number, entry)], {entry.get("output")}
    while entry.get("input") and entry["input"] not in seen:
        seen.add(entry["input"])
        behind = produced(entry["input"])
        if behind is None:  # written by a run whose manifest is gone
            break
        number, entry = behind
        found.append((number, entry))
    return sorted(found, key=lambda item: item[0])


def previous_prompt(run: str, step: int) -> str | None:
    """The prompt this run last used for a step, to notice that it has changed."""
    return read_manifest(run)["steps"].get(str(step), {}).get("prompt_sha1")
