"""
This module provides tools for performing similarity searches on collections of strings or objects implementing the SimilaritySearchable protocol. It uses the Levenshtein distance to calculate the similarity between search terms and elements in a collection. The module supports customized scoring based on insertion, deletion, and substitution costs, and can handle both exact and partial string matches.

Key components:
- `SimilaritySearchable`: A protocol that requires methods for obtaining the full value and search terms of an object.
- `levenshtein_distance`: Function to compute the edit distance between two strings with customizable operation costs.
- `score_string_similarity`: Calculates a similarity score between a given search term and elements in a collection.
- `MatchedString`: A data class for storing match results with a similarity score.
- `get_top_n_results`: Retrieves the top N similar items to a given search term from a collection.

Usage Example:
    # Define a searchable class
    from dataclasses import dataclass
    from typing import Iterable

    @dataclass
    class MySearchable:
        full_text: str
        terms: list

        def get_full_value(self) -> str:
            return self.full_text

        def get_search_terms(self) -> Iterable[str]:
            return self.terms

    # Create a collection of searchable items
    items = [MySearchable("Example text", ["example", "text"]), "simple text"]

    # Search for the term 'examp'
    results = get_top_n_results(items, "examp", max_results=2)

Limitations:
- Performance: The module is designed for collections of a few thousand items. Its performance with larger datasets has not been extensively tested.
- Memory Usage: The Levenshtein distance calculation can be memory-intensive for very long strings or very large collections.
- Scalability: While suitable for moderate-sized collections, the implementation may require optimization for handling large-scale datasets efficiently.
"""

from dataclasses import dataclass
from functools import partial
from typing import Iterable, List, Protocol, Union, runtime_checkable


@runtime_checkable
class SimilaritySearchable(Protocol):
    def get_full_value(self) -> str: ...

    def get_search_terms(self) -> Iterable[str]: ...


def levenshtein_distance(s1, s2, cost_insert=1, cost_delete=1, cost_substitute=1):
    # Create a table to store results of subproblems
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    # Fill the table for base cases
    for i in range(m + 1):
        dp[i][0] = i * cost_delete  # Cost of deletions to make s1 empty
    for j in range(n + 1):
        dp[0][j] = j * cost_insert  # Cost of insertions to make s1 into s2

    # Compute the distance based on the recursion described
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                cost = 0
            else:
                cost = cost_substitute

            dp[i][j] = min(
                dp[i - 1][j] + cost_delete,
                dp[i][j - 1] + cost_insert,
                dp[i - 1][j - 1] + cost,
            )

    return dp[m][n]


def score_string_similarity(
    source: SimilaritySearchable | str, search_term: str, weights=(1, 1, 1), score_cutoff=100
) -> int:
    """Calculates and returns the Levenshtein distance between a source string and a search term.

    Weights are supplied as tuple of scores to apply for the operations respectively:
        (addition_cost, deletion_cost, change_cost)

    By default every type of change costs 1.

    Experimentation has found that values of (1, 10, 10) with a cutoff of 35 makes a pretty pleasant
    set of values to use for general purpose search where the user is typing what they are looking for
    in a shorthand way (where changes / deletions are much less likely than additions).

    This makes it possible to just type a few letters of the word / phrase you are searching for, in the correct
    order, and get a low score even when a decent number of letters needed to be added. Any deletions or changes
    however will dramatically worsen the score.

    Default weights and score_cutoff found to work via manual tweaks to perform well for "partial
    string matching" where a user can search by inputing any of the letters in the source string,
    in the proper order. Deletions / substitutions of letters are heavily penalized.

    When the distance is above the cutoff, -1 is returned.
    """
    match source:
        case str():
            score = levenshtein_distance(
                search_term, source, cost_insert=weights[0], cost_delete=weights[1], cost_substitute=weights[2]
            )
            # score = distance(search_term, source, weights=weights, score_cutoff=score_cutoff)
        case SimilaritySearchable():
            # test each the terms the Searchable item provides and rank them best to worst (lowest to highest)
            term_scores = sorted(
                [
                    (
                        levenshtein_distance(
                            search_term,
                            source_term,
                            cost_insert=weights[0],
                            cost_delete=weights[1],
                            cost_substitute=weights[2],
                        ),
                        source_term,
                    )
                    for source_term in source.get_search_terms()
                ]
            )
            score = term_scores[0][0]
        case _:
            raise TypeError(f"source must be a str or implement the {SimilaritySearchable.__name__} protocol")

    return -1 if score > score_cutoff else score


@dataclass(frozen=True, order=True)
class MatchedString:
    score: int
    value: str  # the full string value
    match_term: str  # the specific term that was matched against (possibly a sub-value of "value"

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, MatchedString):
            return (self.score, self.value) == (other.score, other.value)
        else:
            raise ValueError(type(other))

    def __str__(self):
        return self.value


def get_top_n_results(
    searchable_items: List[Union[str, SimilaritySearchable]],
    search_term: str,
    max_results: int = 5,
    weights=(1, 10, 10),  # by default, heavily penalize changes/deletions
    max_distance=35,
) -> List[MatchedString]:
    """Finds and returns the items most similar to the search term from a list of searchable items."""

    matches = []
    similarity_calculator = partial(
        score_string_similarity, search_term=search_term, weights=weights, score_cutoff=max_distance
    )

    for item in searchable_items:
        if isinstance(item, str):
            similarity_score = similarity_calculator(item)
            if similarity_score > -1:
                matches.append(MatchedString(score=similarity_score, value=item, match_term=item))
        else:
            # if the item is not a string, it must implement the "SimilaritySearchable" protocol
            term_scores = sorted([(similarity_calculator(term), term) for term in item.get_search_terms()])
            try:
                winning_score, winning_term = next(x for x in term_scores if x[0] > -1)
                matches.append(MatchedString(score=winning_score, value=item.get_full_value(), match_term=winning_term))
            except StopIteration:
                continue

    return sorted(matches)[:max_results]  # noqa
