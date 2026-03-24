from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 请确保这里的端口和密码与你 Docker 中的 MySQL 一致 (映射的是 3307 端口)
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:root@127.0.0.1:3307/qa_system"

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# FastAPI 依赖注入，用于普通的 HTTP 请求
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()