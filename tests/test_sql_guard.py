import unittest

from agent.sql_guard import MAX_ROWS, UnsafeSQLError, validate


class SQLGuardTests(unittest.TestCase):
    def test_allows_simple_select_on_analytics(self):
        sql = validate("SELECT category_en, SUM(price) FROM analytics.v_order_items_delivered GROUP BY 1")
        self.assertIn(f"LIMIT {MAX_ROWS}", sql)

    def test_allows_cte_referencing_analytics(self):
        sql = validate(
            "WITH x AS (SELECT * FROM analytics.v_customers) SELECT count(*) FROM x"
        )
        self.assertIn("LIMIT", sql)

    def test_allows_union_of_selects(self):
        validate(
            "SELECT 1 AS a FROM analytics.v_customers UNION SELECT 2 FROM analytics.v_customers"
        )

    def test_rejects_multiple_statements(self):
        with self.assertRaises(UnsafeSQLError):
            validate("SELECT 1 FROM analytics.v_customers; DROP TABLE analytics.v_customers")

    def test_rejects_delete_and_update(self):
        for sql in [
            "DELETE FROM analytics.v_customers",
            "UPDATE analytics.v_customers SET order_count = 0",
            "INSERT INTO analytics.v_customers VALUES (1)",
        ]:
            with self.subTest(sql=sql), self.assertRaises(UnsafeSQLError):
                validate(sql)

    def test_rejects_data_modifying_cte(self):
        with self.assertRaises(UnsafeSQLError):
            validate(
                "WITH d AS (DELETE FROM analytics.v_customers RETURNING 1) SELECT * FROM d"
            )

    def test_rejects_raw_schema(self):
        with self.assertRaises(UnsafeSQLError) as ctx:
            validate("SELECT * FROM raw.orders")
        self.assertIn("raw.orders", str(ctx.exception))

    def test_rejects_unqualified_table(self):
        with self.assertRaises(UnsafeSQLError):
            validate("SELECT * FROM v_customers")

    def test_rejects_dangerous_function(self):
        with self.assertRaises(UnsafeSQLError):
            validate("SELECT pg_sleep(100)")

    def test_rejects_invalid_sql(self):
        with self.assertRaises(UnsafeSQLError):
            validate("SELEC * FROM")


if __name__ == "__main__":
    unittest.main()
