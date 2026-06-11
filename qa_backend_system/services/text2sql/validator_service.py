"""Text2SQL SQL 安全与合规校验服务。

这是整个链路的「安全闸门」：任何 SQL 在执行前都必须通过本服务校验，确保大模型生成的 SQL
既安全又只在授权范围内运行。基于 sqlglot 解析 AST 后逐项校验：

    1. 写操作拦截    ：禁止 DROP/DELETE/UPDATE/INSERT 等任何写/DDL 关键字。
    2. 单语句限制    ：禁止多语句、禁止 UNION，只允许单条 SELECT。
    3. 表数与授权    ：引用表数不超过上限；所有表必须在 allowed_tables 白名单内。
    4. 字段存在性    ：引用字段必须存在于 table_columns_map（权限内字段），且归属唯一。
    5. JOIN 白名单   ：多表只能按已配置的关系（等值连接）JOIN，杜绝凭空关联。
    6. GROUP BY 语义 ：SELECT 中的非聚合字段必须出现在 GROUP BY，避免非法聚合。

任一项不通过即返回 (False, 原因)，由 facade 决定是否触发自动修复。
"""

from __future__ import annotations

import re

from sqlglot import exp, parse_one

# 危险关键字（写操作 / DDL / 提权）：命中即直接拒绝，从源头杜绝 Text2SQL 改动数据。
_DANGEROUS_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|INSERT|UPDATE|CREATE|REPLACE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


class Text2SQLValidatorService:
    """负责 SQL 安全与语义校验。"""

    @staticmethod
    def normalize_identifier(value: str | None) -> str:
        """标准化标识符，便于大小写无关比较。"""
        return (value or "").strip().strip("`").strip('"').lower()

    @staticmethod
    def normalize_table_identifier(value: str | None) -> str:
        """标准化表名，自动去掉 schema 前缀。"""
        table_name = Text2SQLValidatorService.normalize_identifier(value)
        if "." in table_name:
            table_name = table_name.split(".")[-1]
        return table_name

    @staticmethod
    def split_sql_statements(sql: str) -> list[str]:
        """按分号拆分 SQL 语句。"""
        return [part.strip() for part in sql.rstrip(";").split(";") if part.strip()]

    @staticmethod
    def build_alias_map(tree: exp.Expression) -> dict[str, str]:
        """构建 SQL 中别名到真实表名的映射。"""
        alias_map: dict[str, str] = {}
        for table in tree.find_all(exp.Table):
            if table.name:
                real_table = str(table.name)
                alias_map[real_table] = real_table
                if table.alias:
                    alias_map[str(table.alias)] = real_table
        return alias_map

    @staticmethod
    def extract_tables_from_ast(tree: exp.Expression) -> list[str]:
        """从 AST 中提取涉及的表名。"""
        tables: list[str] = []
        for table in tree.find_all(exp.Table):
            if table.name:
                tables.append(str(table.name))
        return list(dict.fromkeys(tables))

    @staticmethod
    def extract_column_references(tree: exp.Expression) -> list[dict[str, str | None]]:
        """从 AST 中提取字段引用及其表别名。"""
        refs: list[dict[str, str | None]] = []
        for column in tree.find_all(exp.Column):
            if not column.name or column.name == "*":
                continue
            refs.append(
                {
                    "table_alias": str(column.table) if column.table else None,
                    "column": str(column.name),
                }
            )
        return refs

    @staticmethod
    def normalize_table_columns_map(
        table_columns_map: dict[str, set[str]] | None,
    ) -> dict[str, set[str]]:
        """标准化表字段白名单映射。"""
        normalized: dict[str, set[str]] = {}
        for table_name, columns in (table_columns_map or {}).items():
            normalized_table = Text2SQLValidatorService.normalize_table_identifier(table_name)
            if not normalized_table:
                continue
            normalized_columns = {
                Text2SQLValidatorService.normalize_identifier(column)
                for column in (columns or set())
                if Text2SQLValidatorService.normalize_identifier(column)
            }
            normalized.setdefault(normalized_table, set()).update(normalized_columns)
        return normalized

    @staticmethod
    def validate_columns_exist(
        tree: exp.Expression,
        table_columns_map: dict[str, set[str]],
    ) -> tuple[bool, str]:
        """校验 SQL 引用字段是否存在且归属明确。"""
        alias_map = Text2SQLValidatorService.build_alias_map(tree)
        normalized_alias_map = {
            Text2SQLValidatorService.normalize_identifier(alias): Text2SQLValidatorService.normalize_table_identifier(table)
            for alias, table in alias_map.items()
            if alias and table
        }
        involved_tables = set(normalized_alias_map.values())
        for ref in Text2SQLValidatorService.extract_column_references(tree):
            column_name = ref["column"]
            normalized_column = Text2SQLValidatorService.normalize_identifier(column_name)
            table_alias = ref["table_alias"]

            if table_alias:
                real_table = normalized_alias_map.get(
                    Text2SQLValidatorService.normalize_identifier(table_alias)
                )
                if not real_table:
                    return False, f"SQL 中存在未知表别名: {table_alias}"
                if normalized_column not in table_columns_map.get(real_table, set()):
                    return False, f"字段不存在: {real_table}.{column_name}"
                continue

            matched_tables = [
                table_name
                for table_name in involved_tables
                if normalized_column in table_columns_map.get(table_name, set())
            ]
            if not matched_tables:
                return False, f"字段不存在: {column_name}"
            if len(matched_tables) > 1:
                return False, f"字段归属不明确: {column_name}"
        return True, ""

    @staticmethod
    def _split_and_conditions(expression: exp.Expression | None) -> list[exp.Expression]:
        if expression is None:
            return []
        if isinstance(expression, exp.And):
            return (
                Text2SQLValidatorService._split_and_conditions(expression.this)
                + Text2SQLValidatorService._split_and_conditions(expression.expression)
            )
        return [expression]

    @staticmethod
    def _parse_column_reference(
        column: exp.Expression | None,
        alias_map: dict[str, str],
    ) -> tuple[str | None, str, bool] | None:
        if not isinstance(column, exp.Column):
            return None
        column_name = Text2SQLValidatorService.normalize_identifier(str(column.name or ""))
        if not column_name:
            return None

        table_alias = Text2SQLValidatorService.normalize_identifier(str(column.table or ""))
        if not table_alias:
            return None, column_name, False

        real_table = alias_map.get(table_alias)
        if not real_table:
            return "__unknown__", column_name, True
        return real_table, column_name, True

    @staticmethod
    def _canonical_condition_pair(
        left_endpoint: tuple[str, str],
        right_endpoint: tuple[str, str],
    ) -> tuple[str, str, str, str]:
        left_table, left_column = left_endpoint
        right_table, right_column = right_endpoint
        left_tuple = (left_table, left_column)
        right_tuple = (right_table, right_column)
        if left_tuple <= right_tuple:
            return left_table, left_column, right_table, right_column
        return right_table, right_column, left_table, left_column

    @classmethod
    def _match_allowed_pair_for_condition(
        cls,
        left_ref: tuple[str | None, str, bool],
        right_ref: tuple[str | None, str, bool],
        allowed_pairs: set[tuple[str, str, str, str]],
    ) -> tuple[tuple[str, str, str, str] | None, str]:
        left_table, left_column, left_explicit = left_ref
        right_table, right_column, right_explicit = right_ref

        if left_explicit and left_table == "__unknown__":
            return None, "JOIN ON 存在未知表别名，请检查 SQL 中的表别名是否正确"
        if right_explicit and right_table == "__unknown__":
            return None, "JOIN ON 存在未知表别名，请检查 SQL 中的表别名是否正确"

        matched_pairs: set[tuple[str, str, str, str]] = set()
        for pair in allowed_pairs:
            pair_left = (pair[0], pair[1])
            pair_right = (pair[2], pair[3])
            oriented_candidates = [(pair_left, pair_right), (pair_right, pair_left)]
            for oriented_left, oriented_right in oriented_candidates:
                oriented_left_table, oriented_left_column = oriented_left
                oriented_right_table, oriented_right_column = oriented_right
                if left_column != oriented_left_column or right_column != oriented_right_column:
                    continue
                if left_table and left_table != oriented_left_table:
                    continue
                if right_table and right_table != oriented_right_table:
                    continue
                matched_pairs.add(pair)

        if not matched_pairs:
            if not left_explicit or not right_explicit:
                return None, "JOIN ON 字段缺少表别名且无法从关系白名单唯一推断，请显式添加表别名"
            return None, "JOIN 条件未命中关系白名单"

        if len(matched_pairs) > 1:
            return None, "JOIN ON 存在歧义字段，请显式添加表别名或调整关系配置"

        return next(iter(matched_pairs)), ""

    @classmethod
    def _build_allowed_join_signatures(
        cls,
        relation_hints: list[dict] | None,
    ) -> dict[frozenset[str], set[frozenset[tuple[str, str, str, str]]]]:
        """把关系白名单编译成「允许的 JOIN 签名」：{两表集合: {该关系的列对集合}}。

        后续校验时，实际 JOIN 的列对集合必须与某条白名单关系完全一致，才算合法。
        """
        allowed: dict[frozenset[str], set[frozenset[tuple[str, str, str, str]]]] = {}
        for relation in relation_hints or []:
            source_table = cls.normalize_table_identifier(str(relation.get("source_table") or ""))
            target_table = cls.normalize_table_identifier(str(relation.get("target_table") or ""))
            source_columns = [
                cls.normalize_identifier(str(item))
                for item in (relation.get("source_columns") or [])
                if cls.normalize_identifier(str(item))
            ]
            target_columns = [
                cls.normalize_identifier(str(item))
                for item in (relation.get("target_columns") or [])
                if cls.normalize_identifier(str(item))
            ]
            if not source_table or not target_table or not source_columns or len(source_columns) != len(target_columns):
                continue

            pairs = {
                cls._canonical_condition_pair(
                    (source_table, source_column),
                    (target_table, target_column),
                )
                for source_column, target_column in zip(source_columns, target_columns)
            }
            if not pairs:
                continue

            tables_key = frozenset({source_table, target_table})
            allowed.setdefault(tables_key, set()).add(frozenset(pairs))
        return allowed

    @classmethod
    def validate_join_constraints(
        cls,
        tree: exp.Expression,
        relation_hints: list[dict] | None,
    ) -> tuple[bool, str]:
        """校验多表 JOIN 是否严格命中关系白名单。

        要求：每个 JOIN 必须有 ON、只能用等值连接（= 与 AND 组合）、只连接两张表，
        且其列对集合必须与白名单中某条关系完全一致；缺别名导致歧义时也会拒绝。
        这是防止大模型「乱 JOIN」产生错误结果或笛卡尔积的关键约束。
        """
        allowed_signatures = cls._build_allowed_join_signatures(relation_hints)
        if not allowed_signatures:
            return False, "当前未配置可用关系白名单，不允许多表 JOIN"

        alias_map = cls.build_alias_map(tree)
        normalized_alias_map = {
            cls.normalize_identifier(alias): cls.normalize_table_identifier(table)
            for alias, table in alias_map.items()
            if cls.normalize_identifier(alias) and cls.normalize_table_identifier(table)
        }

        join_nodes = list(tree.find_all(exp.Join))
        if not join_nodes:
            return False, "多表查询必须使用 JOIN 且提供 ON 条件"

        allowed_pairs: set[tuple[str, str, str, str]] = set()
        for signatures in allowed_signatures.values():
            for signature in signatures:
                allowed_pairs.update(signature)

        for join_node in join_nodes:
            on_expr = join_node.args.get("on")
            if on_expr is None:
                return False, "JOIN 必须包含 ON 条件，且只能使用等值连接"

            conditions = cls._split_and_conditions(on_expr)
            if not conditions:
                return False, "JOIN ON 条件不能为空"

            condition_pairs: set[tuple[str, str, str, str]] = set()
            joined_tables: set[str] = set()
            for condition in conditions:
                if not isinstance(condition, exp.EQ):
                    return False, "JOIN ON 仅允许使用等值连接（=）和 AND 组合"

                left_ref = cls._parse_column_reference(condition.this, normalized_alias_map)
                right_ref = cls._parse_column_reference(condition.expression, normalized_alias_map)
                if left_ref is None or right_ref is None:
                    return False, "JOIN ON 仅允许列与列比较"

                canonical_pair, match_error = cls._match_allowed_pair_for_condition(
                    left_ref,
                    right_ref,
                    allowed_pairs,
                )
                if canonical_pair is None:
                    return False, match_error
                condition_pairs.add(canonical_pair)
                joined_tables.add(canonical_pair[0])
                joined_tables.add(canonical_pair[2])

            if len(joined_tables) != 2:
                return False, "JOIN ON 必须只连接两张表"

            signature = frozenset(condition_pairs)
            tables_key = frozenset(joined_tables)
            if signature not in allowed_signatures.get(tables_key, set()):
                return False, "JOIN 条件未命中关系白名单"
        return True, ""

    @staticmethod
    def _normalize_expression_sql(expression: exp.Expression) -> str:
        sql_text = expression.sql(dialect="mysql")
        sql_text = re.sub(r"\s+", " ", str(sql_text or "")).strip().lower()
        return sql_text.replace("`", "").replace('"', "")

    @classmethod
    def _column_signature(
        cls,
        column: exp.Column,
        alias_map: dict[str, str],
    ) -> tuple[str, str] | None:
        normalized_column = cls.normalize_identifier(str(column.name or ""))
        if not normalized_column:
            return None

        table_alias = cls.normalize_identifier(str(column.table or ""))
        if not table_alias:
            return "", normalized_column

        resolved_table = alias_map.get(table_alias)
        if resolved_table:
            return resolved_table, normalized_column
        return cls.normalize_table_identifier(table_alias), normalized_column

    @classmethod
    def _collect_group_by_column_signatures(
        cls,
        group_expressions: list[exp.Expression],
        alias_map: dict[str, str],
    ) -> set[tuple[str, str]]:
        signatures: set[tuple[str, str]] = set()
        for group_expression in group_expressions:
            for column in group_expression.find_all(exp.Column):
                signature = cls._column_signature(column, alias_map)
                if signature is not None:
                    signatures.add(signature)
        return signatures

    @classmethod
    def _collect_non_agg_column_signatures(
        cls,
        expression: exp.Expression,
        alias_map: dict[str, str],
    ) -> set[tuple[str, str]]:
        signatures: set[tuple[str, str]] = set()

        def _walk(node: exp.Expression | None) -> None:
            if node is None:
                return
            if isinstance(node, exp.AggFunc):
                return
            if isinstance(node, exp.Column):
                signature = cls._column_signature(node, alias_map)
                if signature is not None:
                    signatures.add(signature)
                return
            for child in node.iter_expressions():
                _walk(child)

        _walk(expression)
        return signatures

    @classmethod
    def validate_group_by_semantics(cls, tree: exp.Expression) -> tuple[bool, str]:
        """校验 GROUP BY 语义：SELECT 中所有「非聚合」字段都必须出现在 GROUP BY 中。

        避免 MySQL 宽松模式下「选了未分组字段却不报错、结果不确定」的隐患，
        命中问题会提示把字段加入 GROUP BY 或改为聚合函数（也是常见的可自动修复错误）。
        """
        group_expr = tree.args.get("group")
        if group_expr is None:
            return True, ""
        group_expressions = list(group_expr.expressions or [])
        if not group_expressions:
            return True, ""

        alias_map = cls.build_alias_map(tree)
        normalized_alias_map = {
            cls.normalize_identifier(alias): cls.normalize_table_identifier(table)
            for alias, table in alias_map.items()
            if cls.normalize_identifier(alias) and cls.normalize_table_identifier(table)
        }
        group_expression_sql_set = {
            cls._normalize_expression_sql(group_expression)
            for group_expression in group_expressions
        }
        group_column_signatures = cls._collect_group_by_column_signatures(
            group_expressions,
            normalized_alias_map,
        )

        for raw_select_expression in list(tree.expressions or []):
            select_expression = raw_select_expression.this if isinstance(raw_select_expression, exp.Alias) else raw_select_expression
            if not isinstance(select_expression, exp.Expression):
                continue
            if isinstance(select_expression, exp.Star):
                continue

            if cls._normalize_expression_sql(select_expression) in group_expression_sql_set:
                continue

            non_agg_columns = cls._collect_non_agg_column_signatures(
                select_expression,
                normalized_alias_map,
            )
            if not non_agg_columns:
                continue

            missing_columns = sorted(
                signature for signature in non_agg_columns if signature not in group_column_signatures
            )
            if missing_columns:
                missing_text = ", ".join(
                    f"{table_name}.{column_name}" if table_name else column_name
                    for table_name, column_name in missing_columns
                )
                return (
                    False,
                    (
                        "GROUP BY 校验失败：SELECT 中存在未聚合且未分组字段: "
                        f"{missing_text}。请将字段加入 GROUP BY 或改为聚合函数。"
                    ),
                )
        return True, ""

    @staticmethod
    def validate_sql(
        sql: str,
        allowed_tables: list[str] | None = None,
        table_columns_map: dict[str, set[str]] | None = None,
        max_tables: int | None = None,
        relation_hints: list[dict] | None = None,
    ) -> tuple[bool, str]:
        """校验 SQL 结构安全性、表权限和字段合法性。"""
        # 闸门 1：非空 + 写操作关键字拦截（最优先，防止任何破坏性语句）。
        normalized = sql.strip()
        if not normalized:
            return False, "SQL 不能为空"
        if _DANGEROUS_KEYWORDS.search(sql):
            return False, "SQL 包含禁止的写操作关键字"
        # 闸门 2：只允许单条语句，禁止多语句注入。
        statements = Text2SQLValidatorService.split_sql_statements(sql)
        if len(statements) != 1:
            return False, "不允许执行多条 SQL 语句"
        try:
            tree = parse_one(statements[0], read="mysql")
        except Exception as error:  # noqa: BLE001
            return False, f"SQL 解析失败: {error}"
        # 闸门 3：只允许 SELECT，且禁止 UNION（防止绕过表/字段白名单读取其它数据）。
        if not isinstance(tree, exp.Select):
            return False, "仅允许 SELECT 查询"
        if list(tree.find_all(exp.Union)):
            return False, "暂不允许 UNION 查询"
        referenced_tables = Text2SQLValidatorService.extract_tables_from_ast(tree)
        if not referenced_tables:
            return False, "SQL 必须至少引用一张真实表"

        # 闸门 4：表数量上限 + 多表必须显式 JOIN 且命中关系白名单。
        max_allowed_tables = max(1, int(max_tables or 1))
        if len(referenced_tables) > max_allowed_tables:
            return False, f"SQL 引用了过多表，最多允许 {max_allowed_tables} 张表"
        if len(referenced_tables) > 1:
            joins = list(tree.find_all(exp.Join))
            if not joins:
                return False, "多表查询必须使用显式 JOIN 语法"
            if not relation_hints:
                return False, "当前系统仅支持单表查询，不允许未授权的多表或 JOIN SQL"
            joins_valid, join_error = Text2SQLValidatorService.validate_join_constraints(tree, relation_hints)
            if not joins_valid:
                return False, join_error

        # 闸门 5：GROUP BY 语义校验。
        group_by_valid, group_by_error = Text2SQLValidatorService.validate_group_by_semantics(tree)
        if not group_by_valid:
            return False, group_by_error

        # 闸门 6：表授权——所有引用表必须在允许表白名单内。
        if allowed_tables:
            allowed_table_set = {
                Text2SQLValidatorService.normalize_table_identifier(item)
                for item in allowed_tables
                if item and str(item).strip()
            }
            illegal_tables = [
                table
                for table in referenced_tables
                if Text2SQLValidatorService.normalize_table_identifier(table) not in allowed_table_set
            ]
            if illegal_tables:
                return False, f"SQL 使用了未授权的表: {', '.join(illegal_tables)}"

        # 闸门 7：字段存在性 + 字段级授权——引用字段必须在权限内字段映射中且归属唯一。
        if table_columns_map is not None:
            normalized_map = Text2SQLValidatorService.normalize_table_columns_map(table_columns_map)
            missing_tables = [
                table_name
                for table_name in referenced_tables
                if Text2SQLValidatorService.normalize_table_identifier(table_name) not in normalized_map
            ]
            if missing_tables:
                return False, f"SQL 使用了不存在的表: {', '.join(missing_tables)}"

            columns_valid, error_message = Text2SQLValidatorService.validate_columns_exist(tree, normalized_map)
            if not columns_valid:
                return False, error_message
        return True, ""
