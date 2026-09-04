import random
import re
import threading
import time
from dataclasses import dataclass

import polars as pl

from openai import (APIConnectionError, APIError, BadRequestError,
                    InternalServerError, OpenAI, RateLimitError)

ONE_MINUTE = 60
CALLS_PER_MINUTE = 15  # what the endpoint allows the key

# How far a retry may fall either side of its wait. Without it the requests
# that were refused together wait the same time and arrive together again, in
# waves, and the endpoint refuses them for the same reason as the first time.
JITTER = 0.25


def construct_query(abbreviation):
    if abbreviation.endswith("."):
        abbreviation = abbreviation[:-1]
    escaped = re.escape(abbreviation)
    escaped = escaped.replace(r"\.", r"\.?")
    if escaped.endswith("\\)"):
        result = rf"\b{escaped}"
    else:
        result = rf"\b{escaped}\b"
    return result


def find_overlapping_matches(text: str, pattern: str) -> list[str]:
    """Find all overlapping matches using lookahead."""
    if text is None:
        return []
    # Wrap pattern in a lookahead to allow overlapping matches
    lookahead_pattern = f"(?=({pattern}))"
    return [m.group(1) for m in re.finditer(lookahead_pattern, text)]


def find_abbreviations(texts: pl.DataFrame) -> pl.Series:

    #r'\b(' + re.escape(row["Abkürzung"]).replace(r"\ ", r"[\ \t]*") + ')'
    left_over = texts.with_columns(
        pl.col("header_no_tags").str.extract_all(r"\b(\w+\.)").alias("1h"),
        pl.col("regest_no_tags").str.extract_all(r"\b(\w+\.)").alias("1r"),
        pl.col("header_no_tags")
        .map_elements(
            lambda x: find_overlapping_matches(x, r"\b(\w+\.\ ?\w+\.)"),
            return_dtype=pl.List(pl.String),
        )
        .alias("2h"),
        pl.col("regest_no_tags")
        .map_elements(
            lambda x: find_overlapping_matches(x, r"\b(\w+\.\ ?\w+\.)"),
            return_dtype=pl.List(pl.String),
        )
        .alias("2r"),
        pl.col("header_no_tags")
        .map_elements(
            lambda x: find_overlapping_matches(x, r"\b(\w+\.\ ?\w+\.\ ?\w+\.)"),
            return_dtype=pl.List(pl.String),
        )
        .alias("3h"),
        pl.col("regest_no_tags")
        .map_elements(
            lambda x: find_overlapping_matches(x, r"\b(\w+\.\ ?\w+\.\ ?\w+\.)"),
            return_dtype=pl.List(pl.String),
        )
        .alias("3r"),
        pl.col("header_no_tags")
        .map_elements(
            lambda x: find_overlapping_matches(x, r"\b(\w+\.\ ?\w+\.\ ?\w+\.\ ?\w+\.)"),
            return_dtype=pl.List(pl.String),
        )
        .alias("4h"),
        pl.col("regest_no_tags")
        .map_elements(
            lambda x: find_overlapping_matches(x, r"\b(\w+\.\ ?\w+\.\ ?\w+\.\ ?\w+\.)"),
            return_dtype=pl.List(pl.String),
        )
        .alias("4r"),
        pl.col("header_no_tags")
        .map_elements(
            lambda x: find_overlapping_matches(
                x, r"\b(\w+\.\ ?\w+\.\ ?\w+\.\ ?\w+\.\ ?\w+\.)"
            ),
            return_dtype=pl.List(pl.String),
        )
        .alias("5h"),
        pl.col("regest_no_tags")
        .map_elements(
            lambda x: find_overlapping_matches(
                x, r"\b(\w+\.\ ?\w+\.\ ?\w+\.\ ?\w+\.\ ?\w+\.)"
            ),
            return_dtype=pl.List(pl.String),
        )
        .alias("5r"),
    )
    abbreviations = pl.concat(
        (
            left_over.get_column("1h").explode().drop_nulls(),
            left_over.get_column("1r").explode().drop_nulls(),
            left_over.get_column("2h").explode().drop_nulls(),
            left_over.get_column("2r").explode().drop_nulls(),
            left_over.get_column("3h").explode().drop_nulls(),
            left_over.get_column("3r").explode().drop_nulls(),
            left_over.get_column("4h").explode().drop_nulls(),
            left_over.get_column("4r").explode().drop_nulls(),
            left_over.get_column("5h").explode().drop_nulls(),
            left_over.get_column("5r").explode().drop_nulls(),
        )
    )

    return abbreviations.rename("Abkürzung").unique()


def determine_candidates(vita: pl.DataFrame, glossary: pl.DataFrame):
    """
    The expansion candidates of step 2 for one vita.

    Two kinds of glossary entry contribute, and they are exactly the ones step 1
    could not expand by rule: every complex entry, and those simple entries
    whose volume knows more than one reading.
    """
    volume = vita.get_column("volume").unique().item() # implicit assertion that there is just one vita and consequently one volume in the dataframe
    simple = glossary.filter(~pl.col("komplex"))
    simple = simple.filter(pl.col(f"^RG{volume}$").is_not_null())
    simple = simple.filter(pl.col("Abkürzung").is_duplicated())
    complex = glossary.filter(pl.col("komplex"))

    abbreviations = find_abbreviations(vita)
    multiword_abbreviations_with_spaces = abbreviations.filter(abbreviations.str.find(r"\.\w").is_not_null()).str.replace_all(r"\.(\w)", r". $1")
    abbreviations = pl.concat((abbreviations, multiword_abbreviations_with_spaces))

    simple_candidates = pl.DataFrame(abbreviations).join(simple, on="Abkürzung", how="inner").select("Abkürzung", "Auflösung").group_by("Abkürzung").agg(pl.col("Auflösung"))
    complex_candidates = pl.DataFrame(abbreviations).join(complex, on="Abkürzung", how="inner").select("Abkürzung", "Auflösung").group_by("Abkürzung").agg(pl.col("Auflösung"))
    
    candidates = pl.concat((simple_candidates, complex_candidates)).sort(by="Abkürzung")
    return {row["Abkürzung"]: row["Auflösung"] for row in candidates.iter_rows(named=True)}


def vita_df_to_text(vita:pl.DataFrame) -> str:
    header = vita.get_column("header_no_tags").drop_nulls().item() # implicit assertion that there is just one header
    regests = vita.sort(by=["volume", "nr_RG", "nr_suffix"]).get_column("regest_no_tags").drop_nulls().implode().item().to_list()
    return f"{header}\n{'\n'.join(regests)}"

def vita_dfs_to_vita_texts(df:pl.DataFrame) -> pl.DataFrame:
    texts = df.group_by(["volume", "nr_RG"]).map_groups(lambda group: pl.concat((group.select(["volume", "nr_RG"]).unique(), pl.DataFrame({"text": vita_df_to_text(group)})), how="horizontal", strict=True))
    return df.group_by(["volume", "nr_RG"]).first().select(["volume", "nr_RG"]).join(texts, on=["volume", "nr_RG"])

# the schema of the per-regest tables, spelled out because a vita of a header
# and nothing else leaves the regest column with nothing but nulls, which polars
# would type as Null and then refuse to stack on a column of strings
VITA_SCHEMA = {
    "volume": pl.Int64,
    "nr_RG": pl.Int64,
    "nr_suffix": pl.Int64,
    "header_no_tags": pl.String,
    "regest_no_tags": pl.String,
    "id_RG_all": pl.String,
}

def text_to_vita_df(text: str, volume: int, nr: int):
    pieces = text.split('\n')

    header = [None for _ in pieces]
    regests = pieces

    header[0] = pieces[0]
    regests[0] = None

    vita = pl.DataFrame(
        {"volume" : [volume for _ in pieces],
        "nr_RG": [nr for _ in pieces],
        "nr_suffix": range(len(pieces)),
        "header_no_tags": header,
        "regest_no_tags": regests,
        "id_RG_all": [f"1{volume:02d}{nr:05d}-{i}" for i in range(len(pieces))]},
        schema=VITA_SCHEMA)
    return vita

def vita_texts_to_vita_dfs(df:pl.DataFrame, column:str="text") -> pl.DataFrame:
    """
    The other direction of vita_dfs_to_vita_texts: one row per vita (volume,
    nr_RG and the text) back to one row per regest, the vitae in the order they
    come in. The first line of a text is the header, every further one a regest.

    `nr_suffix` and `id_RG_all` are rebuilt from the position of the line, so a
    text that has been through this and back carries the same values as one
    straight out of the RG -- but only as long as no line was added or dropped
    in between, since nothing else records what the numbering used to be.
    """
    return pl.concat(
        text_to_vita_df(row[column], row["volume"], row["nr_RG"])
        for row in df.iter_rows(named=True)
    )

def available_models(client: OpenAI) -> list[str]:
    """The names the endpoint answers to, as it lists them."""
    return sorted(model.id for model in client.models.list().data)


def check_the_model(client: OpenAI, model: str) -> None:
    """
    Refuse a name the endpoint does not have, before the run starts.

    A mistyped model is not refused once but once per vita: every one of them
    is answered with a 404 and left for `--resume`, so the run looks like an
    endpoint having a bad day rather than like a typo. Asking which models
    there are costs one request, and the answer is short enough to print --
    the name that was meant is usually in it.
    """
    try:
        available = available_models(client)
    except APIConnectionError as error:
        # not an answer about the model: the endpoint may well be there again
        # by the time the vitae are asked for, so this does not stop the run
        print(f"note: could not ask {client.base_url} which models it has "
              f"({type(error).__name__}); running with {model} as given")
        return
    except APIError as error:
        raise ValueError(f"{client.base_url} refused to list its models: {error}") from error
    if model not in available:
        raise ValueError(f"{client.base_url} has no model {model!r}. It has:\n  "
                         + "\n  ".join(available))


@dataclass(frozen=True)
class ThinkingStyle:
    """
    How one family of models is told whether and how much to think.

    There is no shared way of asking. For most families the switch is a variable
    of the chat template (`enable_thinking`, `thinking` for DeepSeek); the effort
    is a top-level request parameter for some families and another template
    variable for others, and each knows its own levels. Asking the way another
    family expects is not an error and not reported: a template that does not use
    the variable renders as if nothing had been passed, and the model answers as
    it would have anyway. Hence this table -- measured against the model cards,
    not guessed from a shared shape.
    """

    reasons: bool = True             # False: this family does not think at all
    switch: str | None = None        # the template variable that takes a boolean
    efforts: tuple[str, ...] = ()    # the levels this family knows, least first
    effort_parameter: bool = False   # the level is a top-level parameter, not a template variable
    on: str | None = None            # the level that means "think", where there is no switch
    off: str | None = None           # the level that means "do not think"


# keyed by the beginning of the model name, longest match wins
STYLES: dict[str, ThinkingStyle] = {
    # thinking is a template variable, the model card documents no levels
    "gemma-4": ThinkingStyle(switch="enable_thinking"),
    "glm-4": ThinkingStyle(switch="enable_thinking"),
    "qwen3": ThinkingStyle(switch="enable_thinking"),
    # ... and for these two the level as well
    "qwen3.8": ThinkingStyle(switch="enable_thinking", efforts=("low", "medium", "xhigh"),
                             effort_parameter=True),
    "deepseek-v4": ThinkingStyle(switch="thinking", efforts=("low", "high", "max")),
    # no switch: the level alone says whether to think, and it is a parameter
    "mistral-medium-3.5": ThinkingStyle(efforts=("none", "high"), effort_parameter=True,
                                        on="high", off="none"),
    "openai-gpt-oss": ThinkingStyle(efforts=("low", "medium", "high"), effort_parameter=True),
    # and these do not think at all, so there is nothing to ask of them; they
    # are in the table because a model that is missing from it cannot be run
    "apertus": ThinkingStyle(reasons=False),
    "meta-llama-3.1": ThinkingStyle(reasons=False),
    "devstral": ThinkingStyle(reasons=False),
}


class ThinkingUnsupported(RuntimeError):
    """
    The model refused the thinking settings outright.

    A model whose tokenizer has no chat template at all (the Mistral ones)
    answers 400 rather than ignoring a template variable it does not know, so
    this is what a wrong entry in `STYLES` looks like when it is loud. The
    quiet version cannot be caught here at all -- see `ThinkingStyle`.
    """


def thinking_style(model: str) -> ThinkingStyle:
    """The entry of `STYLES` for a model, by the longest matching name."""
    matching = [prefix for prefix in STYLES if model.startswith(prefix)]
    if not matching:
        raise ValueError(
            f"no thinking style known for {model}: add one to helper_functions.STYLES, "
            "from the model card. Without it the settings would be sent the way some "
            "other model wants them and silently do nothing."
        )
    return STYLES[max(matching, key=len)]


def known_efforts() -> str:
    """The levels per family, for a help text that cannot go stale."""
    return "; ".join(f"{prefix}: {'/'.join(style.efforts)}"
                     for prefix, style in STYLES.items() if style.efforts)


def thinking_kwargs(model: str, thinking: bool | None = None,
                    reasoning_effort: str | None = None) -> dict:
    """
    What to add to `chat.completions.create` so this model thinks as asked.

    Asking for neither adds nothing and leaves the model at its own default --
    for the reasoning models that is thinking, which on a whole vita can take
    minutes. Asking for a level implies asking to think. Everything the model
    cannot do is raised here rather than sent and ignored.
    """
    if thinking is None and reasoning_effort is None:
        return {}
    style = thinking_style(model)
    if not style.reasons:
        if thinking or reasoning_effort is not None:
            raise ValueError(f"{model} does not think at all, so it cannot be told to: "
                             "run it with --no-thinking, which is what it does anyway")
        return {}  # nothing to send: it does not think, and it was not asked to
    template: dict[str, object] = {}
    parameters: dict[str, object] = {}

    if reasoning_effort is not None:
        if reasoning_effort not in style.efforts:
            knows = "/".join(style.efforts) if style.efforts else "no levels at all"
            raise ValueError(f"{model} does not take the effort {reasoning_effort!r}; "
                             f"it knows {knows}")
        if style.effort_parameter:
            parameters["reasoning_effort"] = reasoning_effort
        else:
            template["reasoning_effort"] = reasoning_effort

    wants = thinking if thinking is not None else True
    levels = [level for level in style.efforts if level != style.off]
    if wants and reasoning_effort is None and len(levels) > 1:
        # a model that is told to think and nothing else thinks at the level the
        # endpoint gives it, which is nowhere in the request, nowhere in the
        # answer and nowhere in the endpoint's documentation
        raise ValueError(f"{model} thinks at one of {'/'.join(levels)}, and which one it is "
                         "when it is not told is the endpoint's to decide and says so "
                         "nowhere; name the level with --reasoning-effort")
    if style.switch is not None:
        template[style.switch] = wants
    elif thinking is not None:
        if reasoning_effort is not None:
            if wants != (reasoning_effort != style.off):
                raise ValueError(f"{model} says how much to think through the level alone, so "
                                 f"{reasoning_effort!r} and thinking={thinking} contradict")
        else:
            level = style.on if wants else style.off
            if level is None:
                raise ValueError(
                    f"{model} cannot be told {'to think' if wants else 'not to think'}; "
                    f"it knows the levels {'/'.join(style.efforts)}"
                )
            parameters["reasoning_effort"] = level

    if template:
        parameters["extra_body"] = {"chat_template_kwargs": template}
    return parameters


# A tenth of a second more than the arithmetic asks for: at exactly four
# seconds the first and the sixteenth call are a minute apart, and an endpoint
# counting a rolling minute counts both -- one call more than it allows, every
# minute, for as long as the run lasts.
SPACING = ONE_MINUTE / CALLS_PER_MINUTE + 0.1
_slots = threading.Lock()
_next_slot = 0.0


def wait_for_a_slot(spacing: float) -> None:
    """
    Hold the call back until it is this process's turn to make one.

    The limit is kept by spacing the calls rather than by counting them, which
    is the same fifteen a minute and never a burst. Counting them lets the
    threads through in a bunch, and then holds all of them at the edge of the
    window and releases them together -- so the endpoint, which refuses calls
    that arrive at the same instant, sees exactly the wave the workers were
    started apart to avoid. Whoever asks takes the next free slot and everyone
    else moves up, so the spreading is the same at the beginning of a run, at
    every window edge, and for the retries after a refusal.

    An idle process does not save up slots: a call that comes after a quiet
    minute goes out at once rather than being followed by fourteen at will.

    Every call goes through here, the retries of a refused one included -- a
    call that came straight back would arrive on top of whatever the endpoint
    is already refusing.
    """
    global _next_slot
    with _slots:  # only for the arithmetic: the waiting happens outside it
        now = time.monotonic()
        mine = max(now, _next_slot)
        _next_slot = mine + spacing
    if mine > now:
        time.sleep(mine - now)


def _call_chat_ai_once(client: OpenAI, model: str, system_prompt: str, user_prompt: str,
                       settings: dict | None = None):
    wait_for_a_slot(SPACING)
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        temperature=0,
        **(settings or {}),
    )
    return chat_completion.model_dump()

def call_chat_ai(client: OpenAI, model: str, system_prompt: str, user_prompt: str, settings: dict | None = None, max_retries: int = 5, retry_wait: float = 5, label: str = ""):
    """
    One answer from the model, waiting out the errors that are worth waiting out.

    The response carries `retries`: how many server errors had to be waited out
    before it arrived. A step that is slow because the endpoint is overloaded
    then looks different in the report from one that is slow because the model
    is, which is not something the wall clock alone can tell.

    `label` names what this call is for -- with several vitae in flight the
    waiting is otherwise anonymous, and one vita being retried five times looks
    exactly like five vitae being retried once.

    This is meant to be the only retrying there is: a client that retries on its
    own does it without a slot and without a word, so the waits below are not
    the ones actually kept and a run can sit for half an hour with nothing
    printed. `run_step.connect` builds the client with `max_retries=0` for that
    reason.
    """
    for retry in range(max_retries + 1):
        try:
            response = _call_chat_ai_once(client, model, system_prompt, user_prompt, settings)
            response["retries"] = retry
            return response
        except BadRequestError as e:
            if not settings:
                raise
            raise ThinkingUnsupported(
                f"{model} rejected the thinking settings {settings}: {e.message} "
                "-- run it without --thinking/--reasoning-effort."
            ) from e
        except (InternalServerError, RateLimitError, APIConnectionError) as e:
            # A 500 is worth waiting out; so is a 429, since the endpoint counts
            # its own rate limit and the decorator above only approximates it;
            # and so is a request that never came back -- with several vitae in
            # flight the endpoint queues them, and a read timeout
            # (APITimeoutError, an APIConnectionError) says the queue was long,
            # not that this vita is unanswerable. The wait grows, because all of
            # these mean the endpoint has more work than it can take, and it is
            # jittered, so that what was refused together does not come back
            # together.
            if retry == max_retries:
                raise
            waiting = retry_wait * (retry + 1) * random.uniform(1 - JITTER, 1 + JITTER)
            reason = getattr(e, "status_code", None) or type(e).__name__
            print(f"  {label + ': ' if label else ''}server error ({reason}), "
                  f"retrying in {waiting:.1f}s ({retry + 1}/{max_retries})")
            time.sleep(waiting)