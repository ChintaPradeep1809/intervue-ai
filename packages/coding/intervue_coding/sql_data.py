"""Deterministic retail dataset and SQL interview problems."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel

RETAIL_DDL = """
CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT,
  country TEXT NOT NULL,
  signup_date TEXT NOT NULL
);
CREATE TABLE products (
  product_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  price REAL NOT NULL
);
CREATE TABLE orders (
  order_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
  order_date TEXT NOT NULL,
  status TEXT NOT NULL
);
CREATE TABLE order_items (
  order_id INTEGER NOT NULL REFERENCES orders(order_id),
  product_id INTEGER NOT NULL REFERENCES products(product_id),
  quantity INTEGER NOT NULL,
  unit_price REAL NOT NULL
);
"""

_FIRST = [
    "Aarav",
    "Diya",
    "Ishaan",
    "Meera",
    "Rohan",
    "Sara",
    "Kabir",
    "Ananya",
    "Vikram",
    "Priya",
    "Liam",
    "Emma",
    "Noah",
    "Olivia",
    "Arjun",
    "Zara",
    "Dev",
    "Nisha",
    "Omar",
    "Leah",
]
_LAST = ["Sharma", "Reddy", "Iyer", "Khan", "Patel", "Smith", "Garcia", "Chen", "Nair", "Das"]
_COUNTRIES = ["IN", "IN", "IN", "US", "US", "UK", "SG", "DE"]
_PRODUCTS = [
    ("Wireless Mouse", "Electronics", 24.99),
    ("Mechanical Keyboard", "Electronics", 89.0),
    ("USB-C Hub", "Electronics", 39.5),
    ("Noise-cancelling Headphones", "Electronics", 199.0),
    ("Standing Desk", "Furniture", 349.0),
    ("Ergonomic Chair", "Furniture", 279.0),
    ("Desk Lamp", "Furniture", 45.0),
    ("Notebook Pack", "Stationery", 12.0),
    ("Gel Pens", "Stationery", 6.5),
    ("Data Engineering Book", "Books", 49.0),
    ("SQL Pocket Guide", "Books", 19.0),
    ("Monitor Arm", "Furniture", 79.0),
]


def _build_rows() -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(20240601)
    customers = []
    for i in range(1, 31):
        name = f"{_FIRST[(i * 7) % len(_FIRST)]} {_LAST[(i * 3) % len(_LAST)]}"
        customers.append(
            {
                "customer_id": i,
                "name": name,
                "email": f"{name.split()[0].lower()}{i}@example.com",
                "country": _COUNTRIES[i % len(_COUNTRIES)],
                "signup_date": (date(2023, 1, 1) + timedelta(days=rng.randint(0, 300))).isoformat(),
            }
        )
    products = [{"product_id": i + 1, "name": n, "category": c, "price": p} for i, (n, c, p) in enumerate(_PRODUCTS)]
    orders, items = [], []
    oid = 1000
    for _ in range(140):
        oid += 1
        cust = rng.choice(range(1, 27))  # customers 27-30 never order
        d = date(2024, 1, 1) + timedelta(days=rng.randint(0, 180))
        status = rng.choices(["completed", "completed", "completed", "cancelled", "returned"], k=1)[0]
        orders.append({"order_id": oid, "customer_id": cust, "order_date": d.isoformat(), "status": status})
        for pid in rng.sample(range(1, len(products) + 1), rng.randint(1, 3)):
            items.append({"order_id": oid, "product_id": pid, "quantity": rng.randint(1, 4), "unit_price": products[pid - 1]["price"]})
    return {"customers": customers, "products": products, "orders": orders, "order_items": items}


@dataclass(frozen=True)
class Dataset:
    name: str
    ddl: str
    rows: dict[str, list[dict[str, Any]]]
    description: str


DATASETS: dict[str, Dataset] = {
    "retail": Dataset(
        name="retail",
        ddl=RETAIL_DDL,
        rows=_build_rows(),
        description="An e-commerce store: customers place orders containing order_items for products. "
        "Revenue for an order = SUM(quantity * unit_price) of its items. Only orders with status = 'completed' count as revenue.",
    )
}


class SqlProblem(BaseModel):
    id: str
    title: str
    difficulty: int
    dataset: str
    statement: str
    reference_sql: str
    order_matters: bool
    expected_features: list[str]
    hints_for_review: list[str] = []


SQL_PROBLEMS: list[SqlProblem] = [
    SqlProblem(
        id="sql-top-customers",
        title="Top customers by revenue",
        difficulty=1,
        dataset="retail",
        statement="Return the top 5 customers by total revenue from completed orders. Columns: customer_id, name, revenue (rounded to 2 decimals). Order by revenue descending, then customer_id ascending.",
        reference_sql="""SELECT c.customer_id, c.name, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM customers c JOIN orders o ON o.customer_id = c.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY c.customer_id, c.name
ORDER BY revenue DESC, c.customer_id ASC
LIMIT 5""",
        order_matters=True,
        expected_features=["join", "group by", "order by", "limit"],
    ),
    SqlProblem(
        id="sql-monthly-running-total",
        title="Monthly revenue with running total",
        difficulty=2,
        dataset="retail",
        statement="For completed orders, return each month's revenue and a running total across months. Columns: month (YYYY-MM), revenue, running_revenue — both rounded to 2 decimals, ordered by month.",
        reference_sql="""WITH monthly AS (
  SELECT substr(o.order_date, 1, 7) AS month, SUM(oi.quantity * oi.unit_price) AS revenue
  FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
  WHERE o.status = 'completed'
  GROUP BY substr(o.order_date, 1, 7)
)
SELECT month, ROUND(revenue, 2) AS revenue, ROUND(SUM(revenue) OVER (ORDER BY month), 2) AS running_revenue
FROM monthly ORDER BY month""",
        order_matters=True,
        expected_features=["over", "group by", "with"],
    ),
    SqlProblem(
        id="sql-latest-order",
        title="Latest order per customer",
        difficulty=2,
        dataset="retail",
        statement="Return each customer's most recent order (any status). Columns: customer_id, order_id, order_date. If a customer has two orders on the same latest date, return the one with the higher order_id. Order by customer_id.",
        reference_sql="""SELECT customer_id, order_id, order_date FROM (
  SELECT customer_id, order_id, order_date,
         ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date DESC, order_id DESC) AS rn
  FROM orders
) t WHERE rn = 1 ORDER BY customer_id""",
        order_matters=True,
        expected_features=["row_number", "partition by", "over"],
    ),
    SqlProblem(
        id="sql-customers-no-orders",
        title="Customers who never ordered",
        difficulty=1,
        dataset="retail",
        statement="Return customers who have never placed an order. Columns: customer_id, name. Order by customer_id.",
        reference_sql="""SELECT c.customer_id, c.name FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL ORDER BY c.customer_id""",
        order_matters=True,
        expected_features=["left join", "is null"],
    ),
    SqlProblem(
        id="sql-category-rank",
        title="Best-selling product per category",
        difficulty=3,
        dataset="retail",
        statement="For completed orders, rank products by revenue within their category and return the top product of each category. Columns: category, product_name, revenue (rounded to 2 decimals). Order by category.",
        reference_sql="""WITH pr AS (
  SELECT p.category, p.name AS product_name, SUM(oi.quantity * oi.unit_price) AS revenue
  FROM products p JOIN order_items oi ON oi.product_id = p.product_id
  JOIN orders o ON o.order_id = oi.order_id
  WHERE o.status = 'completed'
  GROUP BY p.category, p.name
), ranked AS (
  SELECT category, product_name, revenue, RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rnk FROM pr
)
SELECT category, product_name, ROUND(revenue, 2) AS revenue FROM ranked WHERE rnk = 1 ORDER BY category""",
        order_matters=True,
        expected_features=["rank", "partition by", "group by", "join"],
    ),
]


def get_sql_problem(problem_id: str) -> SqlProblem | None:
    return next((p for p in SQL_PROBLEMS if p.id == problem_id), None)


def pick_sql_problem(difficulty: int, exclude: set[str]) -> SqlProblem:
    candidates = [p for p in SQL_PROBLEMS if p.id not in exclude] or SQL_PROBLEMS
    return min(candidates, key=lambda p: (abs(p.difficulty - difficulty), p.id))


def schema_view(dataset: str) -> dict[str, Any]:
    ds = DATASETS[dataset]
    tables = []
    for table, rows in ds.rows.items():
        cols = list(rows[0].keys()) if rows else []
        tables.append({"name": table, "columns": cols, "row_count": len(rows), "sample": rows[:3]})
    return {"dataset": dataset, "description": ds.description, "ddl": ds.ddl.strip(), "tables": tables}


def sql_public_view(p: SqlProblem) -> dict[str, Any]:
    return {
        "id": p.id,
        "title": p.title,
        "difficulty": p.difficulty,
        "statement": p.statement,
        "schema": schema_view(p.dataset),
        "starter": {"sql": "-- Write a single SELECT query\nSELECT \n"},
    }
