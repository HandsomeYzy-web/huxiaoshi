from sqlalchemy import text

from core.database import SessionLocal, engine
from core.logger import setup_logger
from models.entities import Base
from services.role_service import role_service


PERMISSION_TABLES = [
    "kb_role_access",
    "role_permission",
    "user_role",
    "permission",
    "role",
]


def reset_permission_system() -> None:
    setup_logger()

    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table_name in PERMISSION_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    tables = [Base.metadata.tables[name] for name in PERMISSION_TABLES]
    Base.metadata.create_all(bind=engine, tables=tables)

    db = SessionLocal()
    try:
        role_service.init_defaults(db)
    finally:
        db.close()


if __name__ == "__main__":
    reset_permission_system()
