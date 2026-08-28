#!/usr/bin/env python3
"""
Test suite for the helpers the whole workflow shares.

Mostly the two shapes a vita is kept in: `data/*.csv` has one row per regest
(plus one for the header), which is how the RG itself is laid out; the model
steps and the evaluation want the vita as one text. The two conversions have to
be exact inverses of each other, since the workflow goes back and forth between
them at every step. The rest is the body that switches a model's thinking.
"""

import polars as pl
import pytest

from helper_functions import (
    VITA_SCHEMA,
    text_to_vita_df,
    thinking_body,
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


class TestThinkingBody:
    """The `extra_body` that tells a reasoning model how much to think."""

    def test_asking_for_nothing_changes_nothing(self):
        assert thinking_body() is None

    def test_thinking_can_be_turned_off(self):
        assert thinking_body(thinking=False) == {"chat_template_kwargs": {"thinking": False}}

    def test_an_effort_turns_thinking_on_by_itself(self):
        assert thinking_body(reasoning_effort="max") == {
            "chat_template_kwargs": {"thinking": True, "reasoning_effort": "max"}
        }

    def test_an_effort_the_provider_does_not_know_is_refused(self):
        with pytest.raises(ValueError):
            thinking_body(reasoning_effort="very high")
