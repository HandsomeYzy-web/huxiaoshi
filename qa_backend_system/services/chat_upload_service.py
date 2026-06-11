"""聊天表格上传分析服务（短期存储，分析成功后即删）。

用户在聊天中上传 xlsx/xls/csv 表格 → 解析后写入本地临时 SQLite 文件
（短期存储，不进 MinIO/ES/知识库）→ 提问时由 LLM 生成只读 SELECT 在该
SQLite 上执行 → 流式生成分析回答 → 分析成功后立即删除文件；
失败的上传保留以便用户重试，超时未分析的文件由 TTL 兜底清理。
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Generator
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from core.config import settings
from core.exceptions import BusinessError
from core.logger import logger

# SQLite 中承载上传数据的固定表名
_TABLE_NAME = "uploaded_data"

_ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

# 只读守卫：禁止出现任何写操作/危险关键字（词边界匹配，大小写不敏感）
_FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum|reindex|truncate)\b",
    re.IGNORECASE,
)

_SQL_GEN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "你是一个数据分析 SQL 生成器。用户上传了一份表格，数据已存入 SQLite 数据库的 "
                f"`{_TABLE_NAME}` 表中。请根据表结构和用户问题，生成一条 SQLite 方言的 SELECT 查询。\n\n"
                "要求：\n"
                "1. 只能生成一条只读 SELECT 语句（可用 WITH），禁止任何写操作；\n"
                f"2. 只能查询 `{_TABLE_NAME}` 表；\n"
                "3. 列名包含中文或特殊字符时用双引号包裹；\n"
                "4. 结果行数较多时加 LIMIT（默认不超过 {max_rows} 行）；\n"
                "5. 只返回 SQL 本身，不要任何解释、注释或代码块标记。"
            ),
        ),
        (
            "human",
            "表结构与样本数据：\n{schema}\n\n用户问题：{question}{error_block}\n\nSQL：",
        ),
    ]
)


def _safe_column_names(raw_columns: list[object]) -> list[str]:
    """清洗列名：去空白、空名补位、重名去重，保留中文等原始字符。"""
    seen: dict[str, int] = {}
    columns: list[str] = []
    for index, raw in enumerate(raw_columns):
        name = str(raw if raw is not None else "").strip() or f"col_{index + 1}"
        name = name.replace('"', "'").replace("\n", " ")[:64]
        count = seen.get(name, 0)
        seen[name] = count + 1
        columns.append(name if count == 0 else f"{name}_{count + 1}")
    return columns


class ChatUploadService:
    """聊天上传表格的短期存储与分析（一次性：分析成功后删除）。"""

    def __init__(self) -> None:
        self._upload_dir = Path(tempfile.gettempdir()) / "qa_chat_uploads"
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 路径与元数据
    # ------------------------------------------------------------------

    def _db_path(self, upload_id: str) -> Path:
        return self._upload_dir / f"{upload_id}.db"

    def _meta_path(self, upload_id: str) -> Path:
        return self._upload_dir / f"{upload_id}.json"

    @staticmethod
    def _ttl_seconds() -> int:
        return max(1, int(getattr(settings, "CHAT_UPLOAD_TTL_MINUTES", 30))) * 60

    def _load_meta(self, upload_id: str) -> dict | None:
        if not re.fullmatch(r"[0-9a-f]{32}", str(upload_id or "")):
            return None
        meta_path = self._meta_path(upload_id)
        if not meta_path.exists() or not self._db_path(upload_id).exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def cleanup_expired(self) -> None:
        """TTL 兜底清理：删除超过保留时长仍未被分析删除的上传文件。"""
        deadline = time.time() - self._ttl_seconds()
        try:
            for path in self._upload_dir.iterdir():
                try:
                    if path.is_file() and path.stat().st_mtime < deadline:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
        except OSError:
            pass

    def delete_upload(self, upload_id: str, user_id: int | None = None) -> bool:
        """删除一次上传（数据文件 + 元数据）；传 user_id 时校验归属。"""
        meta = self._load_meta(upload_id)
        if meta is None:
            return False
        if user_id is not None and int(meta.get("user_id", 0)) != int(user_id):
            return False
        self._db_path(upload_id).unlink(missing_ok=True)
        self._meta_path(upload_id).unlink(missing_ok=True)
        logger.info(f"Chat upload deleted: upload_id={upload_id}")
        return True

    # ------------------------------------------------------------------
    # 上传与解析
    # ------------------------------------------------------------------

    def save_upload(self, user_id: int, file_name: str, content: bytes) -> dict:
        """解析上传表格并落入临时 SQLite；返回元数据（含 upload_id）。"""
        self.cleanup_expired()

        ext = (file_name.rsplit(".", 1)[-1] if "." in file_name else "").lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise BusinessError(f"仅支持表格文件（{'/'.join(sorted(_ALLOWED_EXTENSIONS))}），不支持 .{ext}")

        max_bytes = int(getattr(settings, "CHAT_UPLOAD_MAX_SIZE_MB", 10)) * 1024 * 1024
        if not content:
            raise BusinessError("上传文件为空")
        if len(content) > max_bytes:
            raise BusinessError(f"文件超过大小限制（{getattr(settings, 'CHAT_UPLOAD_MAX_SIZE_MB', 10)}MB）")

        frame = self._parse_table(ext, content)
        if frame.empty or not len(frame.columns):
            raise BusinessError("未能从文件中解析出有效的表格数据")

        max_rows = int(getattr(settings, "CHAT_UPLOAD_MAX_ROWS", 50000))
        truncated = len(frame) > max_rows
        if truncated:
            frame = frame.head(max_rows)

        frame.columns = _safe_column_names(list(frame.columns))

        upload_id = uuid.uuid4().hex
        db_path = self._db_path(upload_id)
        try:
            with sqlite3.connect(db_path) as conn:
                frame.to_sql(_TABLE_NAME, conn, index=False)
        except Exception as exc:
            db_path.unlink(missing_ok=True)
            raise BusinessError(f"表格数据入库失败: {exc}") from exc

        meta = {
            "upload_id": upload_id,
            "user_id": int(user_id),
            "file_name": file_name,
            "row_count": int(len(frame)),
            "columns": list(frame.columns),
            "dtypes": {col: str(dtype) for col, dtype in frame.dtypes.items()},
            "truncated": truncated,
            "created_at": time.time(),
        }
        self._meta_path(upload_id).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        logger.info(
            f"Chat upload saved: upload_id={upload_id} file={file_name} rows={meta['row_count']} user_id={user_id}"
        )
        return {**meta, "expires_in_seconds": self._ttl_seconds()}

    @staticmethod
    def _parse_table(ext: str, content: bytes):
        import pandas as pd

        try:
            if ext == "csv":
                last_error: Exception | None = None
                for encoding in ("utf-8-sig", "gbk", "utf-8"):
                    try:
                        frame = pd.read_csv(io.BytesIO(content), encoding=encoding)
                        break
                    except (UnicodeDecodeError, ValueError) as exc:
                        last_error = exc
                else:
                    raise BusinessError(f"CSV 解析失败: {last_error}")
            else:
                frame = pd.read_excel(io.BytesIO(content))
        except BusinessError:
            raise
        except Exception as exc:
            raise BusinessError(f"表格解析失败: {exc}") from exc

        # 丢弃全空行/全空列，避免无效数据干扰分析
        frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
        return frame

    # ------------------------------------------------------------------
    # 分析
    # ------------------------------------------------------------------

    def _build_schema_text(self, meta: dict) -> str:
        lines = [f"表名: {_TABLE_NAME}", f"总行数: {meta['row_count']}", "列定义:"]
        dtypes = meta.get("dtypes", {})
        for col in meta["columns"]:
            lines.append(f'  - "{col}" ({dtypes.get(col, "text")})')

        sample_rows: list[dict] = []
        try:
            columns, rows = self._execute_select(
                meta["upload_id"], f'SELECT * FROM "{_TABLE_NAME}" LIMIT 5', max_rows=5
            )
            sample_rows = rows
        except Exception:  # noqa: BLE001
            columns = meta["columns"]
        if sample_rows:
            lines.append("样本数据（前几行）:")
            lines.append(" | ".join(str(col) for col in columns))
            for row in sample_rows:
                lines.append(" | ".join(str(row.get(col, "")) for col in columns))
        if meta.get("truncated"):
            lines.append(f"(注意：原始文件行数超限，仅保留前 {meta['row_count']} 行)")
        return "\n".join(lines)

    @staticmethod
    def _sanitize_sql(raw: str) -> str:
        """剥掉代码块标记并校验为单条只读 SELECT，未通过抛 BusinessError。"""
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:sql)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        text = text.rstrip(";").strip()
        if not text:
            raise BusinessError("模型未生成有效 SQL")
        if ";" in text:
            raise BusinessError("仅允许单条查询语句")
        if not re.match(r"^\s*(select|with)\b", text, re.IGNORECASE):
            raise BusinessError("仅允许 SELECT 查询")
        if _FORBIDDEN_SQL_PATTERN.search(text):
            raise BusinessError("查询包含禁止的写操作关键字")
        return text

    def _execute_select(self, upload_id: str, sql: str, max_rows: int | None = None) -> tuple[list[str], list[dict]]:
        """以只读模式在上传数据的 SQLite 上执行 SELECT，返回 (columns, rows)。"""
        limit = max_rows or int(getattr(settings, "CHAT_UPLOAD_RESULT_MAX_ROWS", 200))
        db_path = self._db_path(upload_id)
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description or []]
            fetched = cursor.fetchmany(limit)
            rows = [
                {col: (value if value is None or isinstance(value, (int, float, str)) else str(value))
                 for col, value in zip(columns, row)}
                for row in fetched
            ]
            return columns, rows
        finally:
            conn.close()

    def _generate_sql(self, question: str, schema_text: str, previous_error: str | None = None) -> str:
        from services.llm_service import llm_service

        if llm_service.model is None:
            raise BusinessError("LLM 未配置，无法进行表格分析")

        error_block = ""
        if previous_error:
            error_block = f"\n\n上一次生成的 SQL 执行失败，错误信息：{previous_error}\n请修正后重新生成。"
        chain = _SQL_GEN_PROMPT | llm_service.model | StrOutputParser()
        raw = chain.invoke(
            {
                "schema": schema_text,
                "question": question,
                "error_block": error_block,
                "max_rows": int(getattr(settings, "CHAT_UPLOAD_RESULT_MAX_ROWS", 200)),
            }
        )
        return self._sanitize_sql(raw)

    def analyze_stream(self, upload_id: str, user_id: int, question: str) -> Generator[tuple[str, dict], None, None]:
        """对上传表格做一次分析，按事件流返回进度/结果/回答增量。

        事件：("status", {...}) / ("sql_result", {sql, columns, rows}) /
              ("model", {model_used}) / ("delta", {content})。
        分析成功后删除上传文件（一次性）；失败保留以便重试，由 TTL 兜底清理。
        """
        from services.llm_service import llm_service

        meta = self._load_meta(upload_id)
        if meta is None:
            raise BusinessError("上传文件不存在或已过期，请重新上传")
        if int(meta.get("user_id", 0)) != int(user_id):
            raise BusinessError("无权访问该上传文件")

        yield "status", {"step": "analyzing_schema", "message": "正在解析表格结构..."}
        schema_text = self._build_schema_text(meta)

        yield "status", {"step": "generating_sql", "message": "正在生成分析查询..."}
        sql = self._generate_sql(question, schema_text)

        yield "status", {"step": "executing", "message": "正在执行查询..."}
        try:
            columns, rows = self._execute_select(upload_id, sql)
        except (sqlite3.Error, BusinessError) as exc:
            # 一轮自动修复：把执行错误回给 LLM 重新生成
            yield "status", {"step": "repairing", "message": "查询执行失败，正在自动修复..."}
            sql = self._generate_sql(question, schema_text, previous_error=str(exc))
            columns, rows = self._execute_select(upload_id, sql)

        yield "sql_result", {"sql": sql, "columns": columns, "rows": rows}

        yield "status", {"step": "generating", "message": "正在生成分析结论..."}
        for chunk, is_model_info, model_name in llm_service.stream_merged_answer(
            question, contexts=None, sql=sql, sql_columns=columns, sql_rows=rows
        ):
            if is_model_info:
                yield "model", {"model_used": model_name}
                continue
            if chunk:
                yield "delta", {"content": chunk}

        # 短期存储承诺：分析成功即删除上传数据
        self.delete_upload(upload_id)


chat_upload_service = ChatUploadService()
