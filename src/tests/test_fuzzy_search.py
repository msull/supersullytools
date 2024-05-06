from dataclasses import dataclass
from typing import Iterable

from supersullytools.utils import fuzzy_search


class TestScoreStringSimilarity:
    def test_find_most_similar(self):
        # source string is first, term is second. The score is related to adjustments for the term to match the source
        assert fuzzy_search.score_string_similarity("Cat", "Cat", weights=(1, 1, 1)) == 0

        # one addition
        assert fuzzy_search.score_string_similarity("Cat", "at", weights=(1, 2, 3)) == 1
        # one deletion
        assert fuzzy_search.score_string_similarity("Cat", "Cate", weights=(1, 2, 3)) == 2
        # one change
        assert fuzzy_search.score_string_similarity("Cat", "C1t", weights=(1, 2, 3)) == 3

        # two additions
        assert fuzzy_search.score_string_similarity("Cat", "a", weights=(1, 9, 9)) == 2
        # two deletions
        assert fuzzy_search.score_string_similarity("Cat", "Crate", weights=(9, 2, 9)) == 4
        # two changes
        assert fuzzy_search.score_string_similarity("Cat", "C1a", weights=(9, 9, 3)) == 6

        # two changes, but a delete/add are cheaper
        assert fuzzy_search.score_string_similarity("Cat", "C1a", weights=(1, 1, 3)) == 2

        # 3 changes
        assert fuzzy_search.score_string_similarity("Cat", "ZOO", weights=(100, 100, 3)) == 9
        # 3 changes, but cheaper to delete and add everything
        assert fuzzy_search.score_string_similarity("Cat", "ZOO", weights=(1, 1, 3)) == 6

    def test_supports_similarity_protocol(self):
        @dataclass
        class MyTest:
            value: str = "Ziya Brinhilde"

            def get_full_value(self) -> str:
                return self.value

            def get_search_terms(self) -> Iterable[str]:
                val = self.value.lower()
                first, last = val.split(" ")
                return [first, last, first + last]

        test_obj = MyTest()
        assert fuzzy_search.score_string_similarity(test_obj, "ziya", (1, 10, 10)) == 0
        assert fuzzy_search.score_string_similarity(test_obj, "brinhilde", (1, 10, 10)) == 0

        # our search terms specifically .lower() the values, so searching with uppercase is a "change" score
        assert fuzzy_search.score_string_similarity(test_obj, "Ziya", (1, 10, 10)) == 10
        assert fuzzy_search.score_string_similarity(test_obj, "zeeba", (1, 10, 10)) == 30
        assert fuzzy_search.score_string_similarity(test_obj, "hilde", (1, 10, 10)) == 4
        assert fuzzy_search.score_string_similarity(test_obj, "zyaBrhile", (1, 10, 10)) == 14


class TestGetTopNResults:
    def test_basic(self):
        search_these = ["Cat", "Dog", "Banana", "Bandana"]

        results = fuzzy_search.get_top_n_results(search_these, "anana")
        print(results)
        assert results[:2] == ["Banana", "Bandana"]

    def test_supports_similarity_protocol(self):
        @dataclass
        class MyTest:
            value: str = "Ziya Brinhilde"

            def get_full_value(self) -> str:
                return self.value

            def get_search_terms(self) -> Iterable[str]:
                val = self.value.lower()
                first, last = val.split(" ")
                return [first, last, first + last]

        results = fuzzy_search.get_top_n_results([MyTest()], "ziya")
        assert results == [fuzzy_search.MatchedString(score=0, value="Ziya Brinhilde", match_term="ziya")]

        results = fuzzy_search.get_top_n_results([MyTest()], "Ziya")
        assert results == [fuzzy_search.MatchedString(score=10, value="Ziya Brinhilde", match_term="ziya")]

        results = fuzzy_search.get_top_n_results([MyTest(), "Zeeba"], "zeyaa")
        assert results == [
            fuzzy_search.MatchedString(score=20, value="Ziya Brinhilde", match_term="ziya"),
            fuzzy_search.MatchedString(score=30, value="Zeeba", match_term="Zeeba"),
        ]
        results = fuzzy_search.get_top_n_results([MyTest(), "Zeeba"], "hilde")
        assert results == [fuzzy_search.MatchedString(score=4, value="Ziya Brinhilde", match_term="brinhilde")]
