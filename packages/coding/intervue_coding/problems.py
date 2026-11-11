"""Coding problem catalogue. Expected outputs never enter the sandbox: the sandbox returns actual
return values and grading happens in the API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class TestCase(BaseModel):
    name: str
    args: list[Any]
    expected: Any
    hidden: bool = False


class CodingProblem(BaseModel):
    id: str
    title: str
    difficulty: int
    tags: list[str]
    statement: str
    constraints: list[str]
    examples: list[dict[str, str]]
    function_name: str
    params: list[str]
    starter: dict[str, str]  # language -> starter code
    tests: list[TestCase]
    compare: Literal["exact", "unordered"] = "exact"
    roles: list[str] = []


def _starters(fn: str, params: list[str], py_sig: str, ts_sig: str, ret_ts: str) -> dict[str, str]:
    js_params = ", ".join(params)
    return {
        "python": f"def {fn}({py_sig}):\n    # Write your solution here\n    pass\n",
        "javascript": f"export function {fn}({js_params}) {{\n  // Write your solution here\n}}\n",
        "typescript": f"export function {fn}({ts_sig}): {ret_ts} {{\n  // Write your solution here\n}}\n",
    }


PROBLEMS: list[CodingProblem] = [
    CodingProblem(
        id="latest-record-per-key",
        title="Latest record per customer",
        difficulty=2,
        tags=["data", "hashing"],
        roles=["aws_data_engineer", "python_developer", "data_analyst"],
        statement=(
            "You receive change records from a CDC feed. Each record is a dict/object with keys "
            "`customer_id` (string), `updated_at` (ISO-8601 string) and `status` (string). "
            "Return the latest record for each customer, sorted by `customer_id` ascending. "
            "If two records for the same customer share the same `updated_at`, keep the one that appears last in the input."
        ),
        constraints=["0 <= len(records) <= 100,000", "ISO-8601 timestamps compare correctly as strings", "Aim for O(n log n) or better"],
        examples=[
            {
                "input": 'records = [{"customer_id": "c2", "updated_at": "2024-01-02T00:00:00", "status": "active"}, {"customer_id": "c1", "updated_at": "2024-01-01T00:00:00", "status": "new"}, {"customer_id": "c2", "updated_at": "2024-01-01T00:00:00", "status": "new"}]',
                "output": '[{"customer_id": "c1", ...,"status": "new"}, {"customer_id": "c2", ..., "status": "active"}]',
            }
        ],
        function_name="latest_records",
        params=["records"],
        starter=_starters(
            "latest_records",
            ["records"],
            "records: list[dict]",
            "records: Array<{customer_id: string; updated_at: string; status: string}>",
            "Array<{customer_id: string; updated_at: string; status: string}>",
        ),
        tests=[
            TestCase(
                name="basic",
                args=[
                    [
                        {"customer_id": "c2", "updated_at": "2024-01-02T00:00:00", "status": "active"},
                        {"customer_id": "c1", "updated_at": "2024-01-01T00:00:00", "status": "new"},
                        {"customer_id": "c2", "updated_at": "2024-01-01T00:00:00", "status": "new"},
                    ]
                ],
                expected=[
                    {"customer_id": "c1", "updated_at": "2024-01-01T00:00:00", "status": "new"},
                    {"customer_id": "c2", "updated_at": "2024-01-02T00:00:00", "status": "active"},
                ],
            ),
            TestCase(name="empty input", args=[[]], expected=[]),
            TestCase(
                name="tie keeps last",
                args=[
                    [
                        {"customer_id": "a", "updated_at": "2024-05-01T10:00:00", "status": "x"},
                        {"customer_id": "a", "updated_at": "2024-05-01T10:00:00", "status": "y"},
                    ]
                ],
                expected=[{"customer_id": "a", "updated_at": "2024-05-01T10:00:00", "status": "y"}],
                hidden=True,
            ),
            TestCase(
                name="out of order",
                args=[
                    [
                        {"customer_id": "b", "updated_at": "2024-03-01T00:00:00", "status": "late"},
                        {"customer_id": "b", "updated_at": "2024-01-01T00:00:00", "status": "early"},
                        {"customer_id": "a", "updated_at": "2023-12-31T23:59:59", "status": "only"},
                    ]
                ],
                expected=[
                    {"customer_id": "a", "updated_at": "2023-12-31T23:59:59", "status": "only"},
                    {"customer_id": "b", "updated_at": "2024-03-01T00:00:00", "status": "late"},
                ],
                hidden=True,
            ),
        ],
    ),
    CodingProblem(
        id="sessionize-events",
        title="Sessionize clickstream events",
        difficulty=2,
        tags=["data", "sorting"],
        roles=["aws_data_engineer", "data_analyst", "python_developer"],
        statement=(
            "Given a list of `[user_id, timestamp_seconds]` pairs (unsorted), count the number of sessions per user. "
            "A new session starts when the gap between consecutive events for the same user is greater than `gap` seconds. "
            "Return a dict/object mapping user_id to session count."
        ),
        constraints=["0 <= len(events) <= 100,000", "timestamps are non-negative integers", "gap > 0"],
        examples=[{"input": 'events = [["u1", 0], ["u1", 100], ["u1", 5000], ["u2", 10]], gap = 1800', "output": '{"u1": 2, "u2": 1}'}],
        function_name="count_sessions",
        params=["events", "gap"],
        starter=_starters(
            "count_sessions", ["events", "gap"], "events: list[list], gap: int", "events: Array<[string, number]>, gap: number", "Record<string, number>"
        ),
        tests=[
            TestCase(name="example", args=[[["u1", 0], ["u1", 100], ["u1", 5000], ["u2", 10]], 1800], expected={"u1": 2, "u2": 1}),
            TestCase(name="unsorted input", args=[[["u1", 5000], ["u1", 0], ["u1", 100]], 1800], expected={"u1": 2}),
            TestCase(name="gap boundary is same session", args=[[["a", 0], ["a", 1800]], 1800], expected={"a": 1}, hidden=True),
            TestCase(name="no events", args=[[], 60], expected={}, hidden=True),
        ],
    ),
    CodingProblem(
        id="top-k-frequent",
        title="Top K frequent words",
        difficulty=1,
        tags=["hashing", "sorting"],
        statement=(
            "Given a list of words and an integer k, return the k most frequent words. Sort by frequency descending; break ties alphabetically ascending."
        ),
        constraints=["1 <= k <= number of unique words", "words are lowercase"],
        examples=[{"input": 'words = ["spark", "sql", "spark", "aws", "sql", "spark"], k = 2', "output": '["spark", "sql"]'}],
        function_name="top_k",
        params=["words", "k"],
        starter=_starters("top_k", ["words", "k"], "words: list[str], k: int", "words: string[], k: number", "string[]"),
        tests=[
            TestCase(name="example", args=[["spark", "sql", "spark", "aws", "sql", "spark"], 2], expected=["spark", "sql"]),
            TestCase(name="alphabetical tie-break", args=[["b", "a", "c", "b", "a", "c"], 2], expected=["a", "b"]),
            TestCase(name="single", args=[["x"], 1], expected=["x"], hidden=True),
            TestCase(name="all ties", args=[["d", "c", "b", "a"], 3], expected=["a", "b", "c"], hidden=True),
        ],
    ),
    CodingProblem(
        id="merge-intervals",
        title="Merge overlapping intervals",
        difficulty=2,
        tags=["sorting", "intervals"],
        statement="Given a list of `[start, end]` intervals, merge all overlapping intervals and return them sorted by start. Touching intervals (end == next start) should merge.",
        constraints=["0 <= len(intervals) <= 10,000", "start <= end"],
        examples=[{"input": "intervals = [[1,3],[2,6],[8,10],[15,18]]", "output": "[[1,6],[8,10],[15,18]]"}],
        function_name="merge_intervals",
        params=["intervals"],
        starter=_starters("merge_intervals", ["intervals"], "intervals: list[list[int]]", "intervals: number[][]", "number[][]"),
        tests=[
            TestCase(name="example", args=[[[1, 3], [2, 6], [8, 10], [15, 18]]], expected=[[1, 6], [8, 10], [15, 18]]),
            TestCase(name="touching", args=[[[1, 4], [4, 5]]], expected=[[1, 5]]),
            TestCase(name="unsorted", args=[[[5, 7], [1, 2], [2, 3]]], expected=[[1, 3], [5, 7]], hidden=True),
            TestCase(name="empty", args=[[]], expected=[], hidden=True),
            TestCase(name="nested", args=[[[1, 10], [2, 3], [4, 5]]], expected=[[1, 10]], hidden=True),
        ],
    ),
    CodingProblem(
        id="validate-records",
        title="Data quality validator",
        difficulty=1,
        tags=["data", "validation"],
        roles=["aws_data_engineer", "data_analyst"],
        statement=(
            "Given a list of order records (dicts/objects with `order_id`, `amount`, `country`), return a dict/object with counts of: "
            "`missing_id` (order_id is null/empty), `negative_amount` (amount < 0), `duplicate_id` (order_id seen before in the list, counted per extra occurrence), "
            "and `valid` (records with none of those problems — a duplicate's first occurrence is still valid)."
        ),
        constraints=["amount is a number", "country may be any string"],
        examples=[
            {
                "input": 'records = [{"order_id": "1", "amount": 10, "country": "IN"}, {"order_id": "1", "amount": 5, "country": "IN"}, {"order_id": "", "amount": -1, "country": "US"}]',
                "output": '{"missing_id": 1, "negative_amount": 1, "duplicate_id": 1, "valid": 1}',
            }
        ],
        function_name="validate_records",
        params=["records"],
        starter=_starters(
            "validate_records",
            ["records"],
            "records: list[dict]",
            "records: Array<{order_id: string | null; amount: number; country: string}>",
            "Record<string, number>",
        ),
        tests=[
            TestCase(
                name="example",
                args=[
                    [
                        {"order_id": "1", "amount": 10, "country": "IN"},
                        {"order_id": "1", "amount": 5, "country": "IN"},
                        {"order_id": "", "amount": -1, "country": "US"},
                    ]
                ],
                expected={"missing_id": 1, "negative_amount": 1, "duplicate_id": 1, "valid": 1},
            ),
            TestCase(
                name="all valid",
                args=[[{"order_id": "a", "amount": 0, "country": "IN"}, {"order_id": "b", "amount": 3, "country": "IN"}]],
                expected={"missing_id": 0, "negative_amount": 0, "duplicate_id": 0, "valid": 2},
            ),
            TestCase(
                name="null id",
                args=[[{"order_id": None, "amount": 1, "country": "IN"}]],
                expected={"missing_id": 1, "negative_amount": 0, "duplicate_id": 0, "valid": 0},
                hidden=True,
            ),
        ],
    ),
    CodingProblem(
        id="two-sum",
        title="Two sum",
        difficulty=1,
        tags=["hashing", "arrays"],
        statement="Return the indices `[i, j]` (i < j) of the two numbers in `nums` that add up to `target`. Exactly one solution exists.",
        constraints=["2 <= len(nums) <= 100,000", "Aim for O(n) time"],
        examples=[{"input": "nums = [2, 7, 11, 15], target = 9", "output": "[0, 1]"}],
        function_name="two_sum",
        params=["nums", "target"],
        starter=_starters("two_sum", ["nums", "target"], "nums: list[int], target: int", "nums: number[], target: number", "number[]"),
        tests=[
            TestCase(name="example", args=[[2, 7, 11, 15], 9], expected=[0, 1]),
            TestCase(name="negatives", args=[[-3, 4, 3, 90], 0], expected=[0, 2]),
            TestCase(name="duplicates", args=[[3, 3], 6], expected=[0, 1], hidden=True),
        ],
    ),
]


def get_problem(problem_id: str) -> CodingProblem | None:
    return next((p for p in PROBLEMS if p.id == problem_id), None)


def pick_problem(role: str, difficulty: int, exclude: set[str]) -> CodingProblem:
    candidates = [p for p in PROBLEMS if p.id not in exclude and (not p.roles or role in p.roles)]
    if not candidates:
        candidates = [p for p in PROBLEMS if p.id not in exclude] or PROBLEMS
    return min(candidates, key=lambda p: (abs(p.difficulty - difficulty), 0 if role in p.roles else 1, p.id))


def public_view(p: CodingProblem) -> dict[str, Any]:
    """Problem as shown to the candidate: hidden tests and all expected outputs of hidden tests removed."""
    return {
        "id": p.id,
        "title": p.title,
        "difficulty": p.difficulty,
        "statement": p.statement,
        "constraints": p.constraints,
        "examples": p.examples,
        "function_name": p.function_name,
        "starter": p.starter,
        "visible_tests": [{"name": t.name, "args": t.args, "expected": t.expected} for t in p.tests if not t.hidden],
        "hidden_test_count": sum(1 for t in p.tests if t.hidden),
    }
