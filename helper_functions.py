import re
import pandas as pd
import polars as pl
from IPython.display import HTML


# NOTE: copied from https://ai.plainenglish.io/displaying-dataframes-side-by-side-in-jupyter-notebook-871e1a6fc692 and then adjusted slightly
def side_by_side(*dfs):
    # This is the div element that we will use to display at the end
    # display:flex makes the div's children stack sideways
    html = '<div style="display:flex">'

    # Iterating through DataFrames
    for df in dfs:
        # convert to pandas if it's a polars dataframe
        df = df.to_pandas() if isinstance(df, pl.DataFrame) else df

        # If None is passed, add extra spacing
        if df is None:
            html += '<div style="margin-right: 8em"></div>'
            continue

        # Putting each table in a div and setting a small margin
        html += '<div style="margin-right: 2em">'

        # The actual table HTML string
        html += df.to_html()

        # Closing the div
        html += "</div>"

    # Closing the root div
    html += "</div>"

    # returning the html with the side-by-side tables
    return HTML(html)


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


def vita_df_to_text(vita:pl.DataFrame):
    header = vita.get_column("header_no_tags").drop_nulls().item() # implicit assertion that there is just one header
    regests = vita.sort(by=["volume", "nr_RG", "nr_suffix"]).get_column("regest_no_tags").drop_nulls().implode().item().to_list()
    return f"{header}\n{'\n'.join(regests)}"

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
