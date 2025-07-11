from __future__ import annotations

import unittest

import sqlglot
from sqlglot.lineage import lineage
from sqlglot.schema import MappingSchema


class TestLineage(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        sqlglot.schema = MappingSchema()

    def test_lineage(self) -> None:
        node = lineage(
            "a",
            "SELECT a FROM z",
            schema={"x": {"a": "int"}},
            sources={"y": "SELECT * FROM x", "z": "SELECT a FROM y"},
        )
        self.assertEqual(
            node.source.sql(),
            "SELECT z.a AS a FROM (SELECT y.a AS a FROM (SELECT x.a AS a FROM x AS x) AS y /* source: y */) AS z /* source: z */",
        )
        self.assertEqual(node.source_name, "")

        downstream = node.downstream[0]
        self.assertEqual(
            downstream.source.sql(),
            "SELECT y.a AS a FROM (SELECT x.a AS a FROM x AS x) AS y /* source: y */",
        )
        self.assertEqual(downstream.source_name, "z")

        downstream = downstream.downstream[0]
        self.assertEqual(
            downstream.source.sql(),
            "SELECT x.a AS a FROM x AS x",
        )
        self.assertEqual(downstream.source_name, "y")
        self.assertGreater(len(node.to_html()._repr_html_()), 1000)

    def test_lineage_sql_with_cte(self) -> None:
        node = lineage(
            "a",
            "WITH z AS (SELECT a FROM y) SELECT a FROM z",
            schema={"x": {"a": "int"}},
            sources={"y": "SELECT * FROM x"},
        )
        self.assertEqual(
            node.source.sql(),
            "WITH z AS (SELECT y.a AS a FROM (SELECT x.a AS a FROM x AS x) AS y /* source: y */) SELECT z.a AS a FROM z AS z",
        )
        self.assertEqual(node.source_name, "")
        self.assertEqual(node.reference_node_name, "")

        # Node containing expanded CTE expression
        downstream = node.downstream[0]
        self.assertEqual(
            downstream.source.sql(),
            "SELECT y.a AS a FROM (SELECT x.a AS a FROM x AS x) AS y /* source: y */",
        )
        self.assertEqual(downstream.source_name, "")
        self.assertEqual(downstream.reference_node_name, "z")

        downstream = downstream.downstream[0]
        self.assertEqual(
            downstream.source.sql(),
            "SELECT x.a AS a FROM x AS x",
        )
        self.assertEqual(downstream.source_name, "y")
        self.assertEqual(downstream.reference_node_name, "")

    def test_lineage_source_with_cte(self) -> None:
        node = lineage(
            "a",
            "SELECT a FROM z",
            schema={"x": {"a": "int"}},
            sources={"z": "WITH y AS (SELECT * FROM x) SELECT a FROM y"},
        )
        self.assertEqual(
            node.source.sql(),
            "SELECT z.a AS a FROM (WITH y AS (SELECT x.a AS a FROM x AS x) SELECT y.a AS a FROM y AS y) AS z /* source: z */",
        )
        self.assertEqual(node.source_name, "")
        self.assertEqual(node.reference_node_name, "")

        downstream = node.downstream[0]
        self.assertEqual(
            downstream.source.sql(),
            "WITH y AS (SELECT x.a AS a FROM x AS x) SELECT y.a AS a FROM y AS y",
        )
        self.assertEqual(downstream.source_name, "z")
        self.assertEqual(downstream.reference_node_name, "")

        downstream = downstream.downstream[0]
        self.assertEqual(
            downstream.source.sql(),
            "SELECT x.a AS a FROM x AS x",
        )
        self.assertEqual(downstream.source_name, "z")
        self.assertEqual(downstream.reference_node_name, "y")

    def test_lineage_source_with_star(self) -> None:
        node = lineage(
            "a",
            "WITH y AS (SELECT * FROM x) SELECT a FROM y",
        )
        self.assertEqual(
            node.source.sql(),
            "WITH y AS (SELECT * FROM x AS x) SELECT y.a AS a FROM y AS y",
        )
        self.assertEqual(node.source_name, "")
        self.assertEqual(node.reference_node_name, "")

        downstream = node.downstream[0]
        self.assertEqual(
            downstream.source.sql(),
            "SELECT * FROM x AS x",
        )
        self.assertEqual(downstream.source_name, "")
        self.assertEqual(downstream.reference_node_name, "y")

    def test_lineage_external_col(self) -> None:
        node = lineage(
            "a",
            "WITH y AS (SELECT * FROM x) SELECT a FROM y JOIN z USING (uid)",
        )
        self.assertEqual(
            node.source.sql(),
            "WITH y AS (SELECT * FROM x AS x) SELECT a AS a FROM y AS y JOIN z AS z ON y.uid = z.uid",
        )
        self.assertEqual(node.source_name, "")
        self.assertEqual(node.reference_node_name, "")

        downstream = node.downstream[0]
        self.assertEqual(
            downstream.source.sql(),
            "?",
        )
        self.assertEqual(downstream.source_name, "")
        self.assertEqual(downstream.reference_node_name, "")

    def test_lineage_values(self) -> None:
        node = lineage(
            "a",
            "SELECT a FROM y",
            sources={"y": "SELECT a FROM (VALUES (1), (2)) AS t (a)"},
        )
        self.assertEqual(
            node.source.sql(),
            "SELECT y.a AS a FROM (SELECT t.a AS a FROM (VALUES (1), (2)) AS t(a)) AS y /* source: y */",
        )
        self.assertEqual(node.source_name, "")

        downstream = node.downstream[0]
        self.assertEqual(downstream.source.sql(), "SELECT t.a AS a FROM (VALUES (1), (2)) AS t(a)")
        self.assertEqual(downstream.expression.sql(), "t.a AS a")
        self.assertEqual(downstream.source_name, "y")

        downstream = downstream.downstream[0]
        self.assertEqual(downstream.source.sql(), "(VALUES (1), (2)) AS t(a)")
        self.assertEqual(downstream.expression.sql(), "a")
        self.assertEqual(downstream.source_name, "y")

    def test_lineage_cte_name_appears_in_schema(self) -> None:
        schema = {"a": {"b": {"t1": {"c1": "int"}, "t2": {"c2": "int"}}}}

        node = lineage(
            "c2",
            "WITH t1 AS (SELECT * FROM a.b.t2), inter AS (SELECT * FROM t1) SELECT * FROM inter",
            schema=schema,
        )

        self.assertEqual(
            node.source.sql(),
            "WITH t1 AS (SELECT t2.c2 AS c2 FROM a.b.t2 AS t2), inter AS (SELECT t1.c2 AS c2 FROM t1 AS t1) SELECT inter.c2 AS c2 FROM inter AS inter",
        )
        self.assertEqual(node.source_name, "")

        downstream = node.downstream[0]
        self.assertEqual(downstream.source.sql(), "SELECT t1.c2 AS c2 FROM t1 AS t1")
        self.assertEqual(downstream.expression.sql(), "t1.c2 AS c2")
        self.assertEqual(downstream.source_name, "")

        downstream = downstream.downstream[0]
        self.assertEqual(downstream.source.sql(), "SELECT t2.c2 AS c2 FROM a.b.t2 AS t2")
        self.assertEqual(downstream.expression.sql(), "t2.c2 AS c2")
        self.assertEqual(downstream.source_name, "")

        downstream = downstream.downstream[0]
        self.assertEqual(downstream.source.sql(), "a.b.t2 AS t2")
        self.assertEqual(downstream.expression.sql(), "a.b.t2 AS t2")
        self.assertEqual(downstream.source_name, "")

        self.assertEqual(downstream.downstream, [])

    def test_lineage_union(self) -> None:
        node = lineage(
            "x",
            "SELECT ax AS x FROM a UNION SELECT bx FROM b UNION SELECT cx FROM c",
        )
        assert len(node.downstream) == 3

        node = lineage(
            "x",
            "SELECT x FROM (SELECT ax AS x FROM a UNION SELECT bx FROM b UNION SELECT cx FROM c)",
        )
        assert len(node.downstream) == 3

    def test_lineage_lateral_flatten(self) -> None:
        node = lineage(
            "VALUE",
            "SELECT FLATTENED.VALUE FROM TEST_TABLE, LATERAL FLATTEN(INPUT => RESULT, OUTER => TRUE) FLATTENED",
            dialect="snowflake",
        )
        self.assertEqual(node.name, "VALUE")

        downstream = node.downstream[0]
        self.assertEqual(downstream.name, "FLATTENED.VALUE")
        self.assertEqual(
            downstream.source.sql(dialect="snowflake"),
            "LATERAL FLATTEN(INPUT => TEST_TABLE.RESULT, OUTER => TRUE) AS FLATTENED(SEQ, KEY, PATH, INDEX, VALUE, THIS)",
        )
        self.assertEqual(downstream.expression.sql(dialect="snowflake"), "VALUE")
        self.assertEqual(len(downstream.downstream), 1)

        downstream = downstream.downstream[0]
        self.assertEqual(downstream.name, "TEST_TABLE.RESULT")
        self.assertEqual(downstream.source.sql(dialect="snowflake"), "TEST_TABLE AS TEST_TABLE")

        node = lineage(
            "FIELD",
            "SELECT FLATTENED.VALUE:field::text AS FIELD FROM SNOWFLAKE.SCHEMA.MODEL AS MODEL_ALIAS, LATERAL FLATTEN(INPUT => MODEL_ALIAS.A) AS FLATTENED",
            schema={"SNOWFLAKE": {"SCHEMA": {"TABLE": {"A": "integer"}}}},
            sources={"SNOWFLAKE.SCHEMA.MODEL": "SELECT A FROM SNOWFLAKE.SCHEMA.TABLE"},
            dialect="snowflake",
        )
        self.assertEqual(node.name, "FIELD")

        downstream = node.downstream[0]
        self.assertEqual(downstream.name, "FLATTENED.VALUE")
        self.assertEqual(
            downstream.source.sql(dialect="snowflake"),
            "LATERAL FLATTEN(INPUT => MODEL_ALIAS.A) AS FLATTENED(SEQ, KEY, PATH, INDEX, VALUE, THIS)",
        )
        self.assertEqual(downstream.expression.sql(dialect="snowflake"), "VALUE")
        self.assertEqual(len(downstream.downstream), 1)

        downstream = downstream.downstream[0]
        self.assertEqual(downstream.name, "MODEL_ALIAS.A")
        self.assertEqual(downstream.source_name, "SNOWFLAKE.SCHEMA.MODEL")
        self.assertEqual(
            downstream.source.sql(dialect="snowflake"),
            "SELECT TABLE.A AS A FROM SNOWFLAKE.SCHEMA.TABLE AS TABLE",
        )
        self.assertEqual(downstream.expression.sql(dialect="snowflake"), "TABLE.A AS A")
        self.assertEqual(len(downstream.downstream), 1)

        downstream = downstream.downstream[0]
        self.assertEqual(downstream.name, "TABLE.A")
        self.assertEqual(
            downstream.source.sql(dialect="snowflake"), "SNOWFLAKE.SCHEMA.TABLE AS TABLE"
        )
        self.assertEqual(
            downstream.expression.sql(dialect="snowflake"), "SNOWFLAKE.SCHEMA.TABLE AS TABLE"
        )

    def test_subquery(self) -> None:
        node = lineage(
            "output",
            "SELECT (SELECT max(t3.my_column) my_column FROM foo t3) AS output FROM table3",
        )
        self.assertEqual(node.name, "output")
        node = node.downstream[0]
        self.assertEqual(node.name, "my_column")
        node = node.downstream[0]
        self.assertEqual(node.name, "t3.my_column")
        self.assertEqual(node.source.sql(), "foo AS t3")

        node = lineage(
            "y",
            "SELECT SUM((SELECT max(a) a from x) + (SELECT min(b) b from x) + c) AS y FROM x",
        )
        self.assertEqual(node.name, "y")
        self.assertEqual(len(node.downstream), 3)
        self.assertEqual(node.downstream[0].name, "a")
        self.assertEqual(node.downstream[1].name, "b")
        self.assertEqual(node.downstream[2].name, "x.c")

        node = lineage(
            "x",
            "WITH cte AS (SELECT a, b FROM z) SELECT sum(SELECT a FROM cte) AS x, (SELECT b FROM cte) as y FROM cte",
        )
        self.assertEqual(node.name, "x")
        self.assertEqual(len(node.downstream), 1)
        node = node.downstream[0]
        self.assertEqual(node.name, "a")
        node = node.downstream[0]
        self.assertEqual(node.name, "cte.a")
        self.assertEqual(node.reference_node_name, "cte")
        node = node.downstream[0]
        self.assertEqual(node.name, "z.a")

        node = lineage(
            "a",
            """
            WITH foo AS (
              SELECT
                1 AS a
            ), bar AS (
              (
                SELECT
                  a + 1 AS a
                FROM foo
              )
            )
            (
              SELECT
                a + b AS a
              FROM bar
              CROSS JOIN (
                SELECT
                  2 AS b
              ) AS baz
            )
            """,
        )
        self.assertEqual(node.name, "a")
        self.assertEqual(len(node.downstream), 2)
        a, b = sorted(node.downstream, key=lambda n: n.name)
        self.assertEqual(a.name, "bar.a")
        self.assertEqual(len(a.downstream), 1)
        self.assertEqual(b.name, "baz.b")
        self.assertEqual(b.downstream, [])

        node = a.downstream[0]
        self.assertEqual(node.name, "foo.a")

        # Select from derived table
        node = lineage(
            "a",
            "SELECT a FROM (SELECT a FROM x) subquery",
        )
        self.assertEqual(node.name, "a")
        self.assertEqual(len(node.downstream), 1)
        node = node.downstream[0]
        self.assertEqual(node.name, "subquery.a")
        self.assertEqual(node.reference_node_name, "subquery")

        node = lineage(
            "a",
            "SELECT a FROM (SELECT a FROM x)",
        )
        self.assertEqual(node.name, "a")
        self.assertEqual(len(node.downstream), 1)
        node = node.downstream[0]
        self.assertEqual(node.name, "_q_0.a")
        self.assertEqual(node.reference_node_name, "_q_0")

    def test_lineage_cte_union(self) -> None:
        query = """
        WITH dataset AS (
            SELECT *
            FROM catalog.db.table_a

            UNION

            SELECT *
            FROM catalog.db.table_b
        )

        SELECT x, created_at FROM dataset;
        """
        node = lineage("x", query)

        self.assertEqual(node.name, "x")

        downstream_a = node.downstream[0]
        self.assertEqual(downstream_a.name, "0")
        self.assertEqual(downstream_a.source.sql(), "SELECT * FROM catalog.db.table_a AS table_a")
        self.assertEqual(downstream_a.reference_node_name, "dataset")
        downstream_b = node.downstream[1]
        self.assertEqual(downstream_b.name, "0")
        self.assertEqual(downstream_b.source.sql(), "SELECT * FROM catalog.db.table_b AS table_b")
        self.assertEqual(downstream_b.reference_node_name, "dataset")

    def test_lineage_source_union(self) -> None:
        query = "SELECT x, created_at FROM dataset;"
        node = lineage(
            "x",
            query,
            sources={
                "dataset": """
                SELECT *
                FROM catalog.db.table_a

                UNION

                SELECT *
                FROM catalog.db.table_b
                """
            },
        )

        self.assertEqual(node.name, "x")

        downstream_a = node.downstream[0]
        self.assertEqual(downstream_a.name, "0")
        self.assertEqual(downstream_a.source_name, "dataset")
        self.assertEqual(downstream_a.source.sql(), "SELECT * FROM catalog.db.table_a AS table_a")
        self.assertEqual(downstream_a.reference_node_name, "")
        downstream_b = node.downstream[1]
        self.assertEqual(downstream_b.name, "0")
        self.assertEqual(downstream_b.source_name, "dataset")
        self.assertEqual(downstream_b.source.sql(), "SELECT * FROM catalog.db.table_b AS table_b")
        self.assertEqual(downstream_b.reference_node_name, "")

    def test_select_star(self) -> None:
        node = lineage("x", "SELECT x from (SELECT * from table_a)")

        self.assertEqual(node.name, "x")

        downstream = node.downstream[0]
        self.assertEqual(downstream.name, "_q_0.x")
        self.assertEqual(downstream.source.sql(), "SELECT * FROM table_a AS table_a")

        downstream = downstream.downstream[0]
        self.assertEqual(downstream.name, "*")
        self.assertEqual(downstream.source.sql(), "table_a AS table_a")

    def test_unnest(self) -> None:
        node = lineage(
            "b",
            "with _data as (select [struct(1 as a, 2 as b)] as col) select b from _data cross join unnest(col)",
        )
        self.assertEqual(node.name, "b")

    def test_lineage_normalize(self) -> None:
        node = lineage("a", "WITH x AS (SELECT 1 a) SELECT a FROM x", dialect="snowflake")
        self.assertEqual(node.name, "A")

        with self.assertRaises(sqlglot.errors.SqlglotError):
            lineage('"a"', "WITH x AS (SELECT 1 a) SELECT a FROM x", dialect="snowflake")

    def test_ddl_lineage(self) -> None:
        sql = """
        INSERT /*+ HINT1 */
        INTO target (x, y)
        SELECT subq.x, subq.y
        FROM (
          SELECT /*+ HINT2 */
            t.x AS x,
            TO_DATE('2023-12-19', 'YYYY-MM-DD') AS y
          FROM s.t t
          WHERE 1 = 1 AND y = TO_DATE('2023-12-19', 'YYYY-MM-DD')
        ) subq
        """

        node = lineage("y", sql, dialect="oracle")

        self.assertEqual(node.name, "Y")
        self.assertEqual(node.expression.sql(dialect="oracle"), "SUBQ.Y AS Y")

        downstream = node.downstream[0]
        self.assertEqual(downstream.name, "SUBQ.Y")
        self.assertEqual(
            downstream.expression.sql(dialect="oracle"), "TO_DATE('2023-12-19', 'YYYY-MM-DD') AS Y"
        )

    def test_trim(self) -> None:
        sql = """
            SELECT a, b, c
            FROM (select a, b, c from y) z
        """

        node = lineage("a", sql, trim_selects=False)

        self.assertEqual(node.name, "a")
        self.assertEqual(
            node.source.sql(),
            "SELECT z.a AS a, z.b AS b, z.c AS c FROM (SELECT y.a AS a, y.b AS b, y.c AS c FROM y AS y) AS z",
        )

        downstream = node.downstream[0]
        self.assertEqual(downstream.name, "z.a")
        self.assertEqual(downstream.source.sql(), "SELECT y.a AS a, y.b AS b, y.c AS c FROM y AS y")

    def test_node_name_doesnt_contain_comment(self) -> None:
        sql = "SELECT * FROM (SELECT x /* c */ FROM t1) AS t2"
        node = lineage("x", sql)

        self.assertEqual(len(node.downstream), 1)
        self.assertEqual(len(node.downstream[0].downstream), 1)
        self.assertEqual(node.downstream[0].downstream[0].name, "t1.x")

    def test_pivot_without_alias(self) -> None:
        sql = """
        SELECT 
            a as other_a
        FROM (select value,category from sample_data)
        PIVOT (
            sum(value)
            FOR category IN ('a', 'b')
        );
        """
        node = lineage("other_a", sql)

        self.assertEqual(node.downstream[0].name, "_q_0.value")
        self.assertEqual(node.downstream[0].downstream[0].name, "sample_data.value")

    def test_pivot_with_alias(self) -> None:
        sql = """
            SELECT 
                cat_a_s as other_as
            FROM sample_data
            PIVOT (
                sum(value) as s, max(price)
                FOR category IN ('a' as cat_a, 'b')
            )
        """
        node = lineage("other_as", sql)

        self.assertEqual(len(node.downstream), 1)
        self.assertEqual(node.downstream[0].name, "sample_data.value")

    def test_pivot_with_cte(self) -> None:
        sql = """
        WITH t as (
            SELECT 
                a as other_a
            FROM sample_data
            PIVOT (
                sum(value)
                FOR category IN ('a', 'b')
            )
        )
        select other_a from t
        """
        node = lineage("other_a", sql)

        self.assertEqual(node.downstream[0].name, "t.other_a")
        self.assertEqual(node.downstream[0].reference_node_name, "t")
        self.assertEqual(node.downstream[0].downstream[0].name, "sample_data.value")

    def test_pivot_with_implicit_column_of_pivoted_source(self) -> None:
        sql = """
        SELECT empid
        FROM quarterly_sales
            PIVOT(SUM(amount) FOR quarter IN (
            '2023_Q1',
            '2023_Q2',
            '2023_Q3'))
        ORDER BY empid;
        """
        node = lineage("empid", sql)

        self.assertEqual(node.downstream[0].name, "quarterly_sales.empid")

    def test_pivot_with_implicit_column_of_pivoted_source_and_cte(self) -> None:
        sql = """
        WITH t as (
            SELECT empid
            FROM quarterly_sales
            PIVOT(SUM(amount) FOR quarter IN (
                '2023_Q1',
                '2023_Q2',
                '2023_Q3'))
        )
        select empid from t
        """
        node = lineage("empid", sql)

        self.assertEqual(node.downstream[0].name, "t.empid")
        self.assertEqual(node.downstream[0].reference_node_name, "t")
        self.assertEqual(node.downstream[0].downstream[0].name, "quarterly_sales.empid")

    def test_table_udtf_snowflake(self) -> None:
        lateral_flatten = """
        SELECT f.value:external_id::string AS external_id
        FROM database_name.schema_name.table_name AS raw,
        LATERAL FLATTEN(events) AS f
        """
        table_flatten = """
        SELECT f.value:external_id::string AS external_id
        FROM database_name.schema_name.table_name AS raw
        JOIN TABLE(FLATTEN(events)) AS f
        """

        lateral_node = lineage("external_id", lateral_flatten, dialect="snowflake")
        table_node = lineage("external_id", table_flatten, dialect="snowflake")

        self.assertEqual(lateral_node.name, "EXTERNAL_ID")
        self.assertEqual(table_node.name, "EXTERNAL_ID")

        lateral_node = lateral_node.downstream[0]
        table_node = table_node.downstream[0]

        self.assertEqual(lateral_node.name, "F.VALUE")
        self.assertEqual(
            lateral_node.source.sql("snowflake"),
            "LATERAL FLATTEN(RAW.EVENTS) AS F(SEQ, KEY, PATH, INDEX, VALUE, THIS)",
        )

        self.assertEqual(table_node.name, "F.VALUE")
        self.assertEqual(table_node.source.sql("snowflake"), "TABLE(FLATTEN(RAW.EVENTS)) AS F")

        lateral_node = lateral_node.downstream[0]
        table_node = table_node.downstream[0]

        self.assertEqual(lateral_node.name, "RAW.EVENTS")
        self.assertEqual(
            lateral_node.source.sql("snowflake"),
            "DATABASE_NAME.SCHEMA_NAME.TABLE_NAME AS RAW",
        )

        self.assertEqual(table_node.name, "RAW.EVENTS")
        self.assertEqual(
            table_node.source.sql("snowflake"),
            "DATABASE_NAME.SCHEMA_NAME.TABLE_NAME AS RAW",
        )

    def test_pivot_with_subquery(self) -> None:
        schema = {
            "loan_ledger": {
                "product_type": "varchar",
                "month": "date",
                "loan_id": "int",
            }
        }

        sql = """
        WITH cte AS (
            SELECT * FROM (
                SELECT product_type, month, loan_id 
                FROM loan_ledger
            ) PIVOT (
                COUNT(loan_id) FOR month IN ('2024-10', '2024-11')
            )
        )
        SELECT 
            cte.product_type AS product_type,
            cte."2024-10" AS "2024-10"
        FROM cte
        """

        node = lineage("product_type", sql, dialect="duckdb", schema=schema)
        self.assertEqual(node.downstream[0].name, "cte.product_type")
        self.assertEqual(node.downstream[0].downstream[0].name, "_q_0.product_type")
        self.assertEqual(
            node.downstream[0].downstream[0].downstream[0].name, "loan_ledger.product_type"
        )

        node = lineage('"2024-10"', sql, dialect="duckdb", schema=schema)
        self.assertEqual(node.downstream[0].name, "cte.2024-10")
        self.assertEqual(node.downstream[0].downstream[0].name, "_q_0.loan_id")
        self.assertEqual(node.downstream[0].downstream[0].downstream[0].name, "loan_ledger.loan_id")
