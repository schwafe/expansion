import re
import time
import polars as pl

from openai import InternalServerError, OpenAI
from ratelimit import limits, sleep_and_retry

ONE_MINUTE = 60


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
        "id_RG_all": [f"1{volume:02d}{nr:05d}-{i}" for i in range(len(pieces))]})
    return vita

@sleep_and_retry
@limits(calls=15, period=ONE_MINUTE)
def _call_chat_ai_once(client: OpenAI, model: str, system_prompt: str, user_prompt: str):
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
    )
    return chat_completion.model_dump()

def call_chat_ai(client: OpenAI, model: str, system_prompt: str, user_prompt: str, max_retries: int = 5, retry_wait: float = 5):
    for retry in range(max_retries + 1):
        try:
            return _call_chat_ai_once(client, model, system_prompt, user_prompt)
        except InternalServerError as e:
            if retry == max_retries:
                raise
            print(f"server error ({e.status_code}), retrying in {retry_wait}s ({retry + 1}/{max_retries})")
            time.sleep(retry_wait)