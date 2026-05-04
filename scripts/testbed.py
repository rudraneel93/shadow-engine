"""Self-contained testbed with deliberate bugs for definitive proof.

Each function has a known bug variant that breaks its tests.
The LLM must fix the bug to restore passing tests.
"""

# ── Math Functions ──────────────────────────────────

def safe_divide(a: float, b: float) -> float:
    """Divide a by b. Returns 0 if b is 0."""
    if b == 0:
        return 0.0
    return a / b

def fibonacci(n: int) -> list[int]:
    """Return first n Fibonacci numbers."""
    if n <= 0:
        return []
    if n == 1:
        return [0]
    result = [0, 1]
    for _ in range(2, n):
        result.append(result[-1] + result[-2])
    return result

def is_palindrome(s: str) -> bool:
    """Check if string is palindrome (case-insensitive, ignore non-alnum)."""
    cleaned = ''.join(c.lower() for c in s if c.isalnum())
    return cleaned == cleaned[::-1]

def binary_search(arr: list[int], target: int) -> int:
    """Binary search in sorted array. Return index or -1."""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

def flatten(nested) -> list:
    """Flatten arbitrarily nested lists."""
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result

def merge_intervals(intervals: list) -> list:
    """Merge overlapping intervals [(1,3),(2,6)] → [(1,6)]."""
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged

def count_words(text: str) -> dict[str, int]:
    """Count word frequency in text."""
    words = text.lower().split()
    freq = {}
    for w in words:
        w = w.strip('.,!?;:')
        freq[w] = freq.get(w, 0) + 1
    return freq

def find_anagrams(word: str, word_list: list[str]) -> list[str]:
    """Find anagrams of word in word_list (case-insensitive)."""
    sorted_word = ''.join(sorted(word.lower()))
    return [w for w in word_list if ''.join(sorted(w.lower())) == sorted_word]

def topological_sort(graph: dict) -> list[str]:
    """Topological sort of DAG using Kahn's algorithm."""
    in_degree = {node: 0 for node in graph}
    for node in graph:
        for neighbor in graph[node]:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1
    
    queue = [node for node in graph if in_degree[node] == 0]
    result = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    return result

def regex_match(pattern: str, text: str) -> bool:
    """Simple regex matcher supporting *, ., and literals."""
    if not pattern:
        return not text
    if len(pattern) > 1 and pattern[1] == '*':
        return (regex_match(pattern[2:], text) or
                (bool(text) and pattern[0] in ('.', text[0]) and regex_match(pattern, text[1:])))
    if text and pattern[0] in ('.', text[0]):
        return regex_match(pattern[1:], text[1:])
    return False