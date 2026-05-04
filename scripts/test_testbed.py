"""Tests for testbed.py functions — 30 tests covering all 10 functions."""

import pytest
from testbed import (
    safe_divide, fibonacci, is_palindrome, binary_search,
    flatten, merge_intervals, count_words, find_anagrams,
    topological_sort, regex_match,
)


class TestSafeDivide:
    def test_normal(self): assert safe_divide(10, 2) == 5.0
    def test_zero_division(self): assert safe_divide(5, 0) == 0.0
    def test_negative(self): assert safe_divide(-6, 3) == -2.0


class TestFibonacci:
    def test_n5(self): assert fibonacci(5) == [0, 1, 1, 2, 3]
    def test_n0(self): assert fibonacci(0) == []
    def test_n1(self): assert fibonacci(1) == [0]


class TestIsPalindrome:
    def test_simple(self): assert is_palindrome("racecar") is True
    def test_not_palindrome(self): assert is_palindrome("hello") is False
    def test_case_insensitive(self): assert is_palindrome("RaceCar") is True


class TestBinarySearch:
    def test_found(self): assert binary_search([1, 2, 3, 4, 5], 3) == 2
    def test_not_found(self): assert binary_search([1, 2, 3], 5) == -1
    def test_empty(self): assert binary_search([], 1) == -1


class TestFlatten:
    def test_already_flat(self): assert flatten([1, 2, 3]) == [1, 2, 3]
    def test_nested(self): assert flatten([1, [2, [3]]]) == [1, 2, 3]
    def test_empty(self): assert flatten([]) == []


class TestMergeIntervals:
    def test_basic(self): assert merge_intervals([(1, 3), (2, 6)]) == [(1, 6)]
    def test_no_overlap(self): assert merge_intervals([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]
    def test_empty(self): assert merge_intervals([]) == []


class TestCountWords:
    def test_simple(self): assert count_words("hello world hello") == {"hello": 2, "world": 1}
    def test_punctuation(self): assert count_words("hi! hi?") == {"hi": 2}
    def test_empty(self): assert count_words("") == {}


class TestFindAnagrams:
    def test_found(self): assert find_anagrams("listen", ["enlist", "hello", "silent"]) == ["enlist", "silent"]
    def test_none(self): assert find_anagrams("xyz", ["abc", "def"]) == []
    def test_case(self): assert find_anagrams("Tea", ["eat", "ate"]) == ["eat", "ate"]


class TestTopologicalSort:
    def test_dag(self):
        assert topological_sort({"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}) == ["A", "B", "C", "D"]
    def test_single(self): assert topological_sort({"X": []}) == ["X"]


class TestRegexMatch:
    def test_exact(self): assert regex_match("abc", "abc") is True
    def test_dot(self): assert regex_match("a.c", "abc") is True
    def test_star(self): assert regex_match("a*b", "aaab") is True
    def test_no_match(self): assert regex_match("abc", "xyz") is False