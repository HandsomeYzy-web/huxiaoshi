from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from core.config import settings
from models.entities import Base  # 导入基类，用于获取 metadata

# ==========================================
# 1. 创建 SQLAlchemy 引擎 (Engine)
# ==========================================
# pool_pre_ping=True: 每次从连接池取出连接时，先 ping 一下数据库，防止“MySQL server has gone away”报错
# pool_recycle=3600: 每小时主动回收重建一次连接池中的连接，保持连接的健康
# echo=False: 如果你在本地调试时想看到生成的 SQL 语句，可以将其改为 True
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

# ==========================================
# 2. 创建会话工厂 (Session Factory)
# ==========================================
# autocommit=False: 关闭自动提交，我们在业务代码中手动 commit，保证事务的完整性
# autoflush=False: 关闭自动刷新，避免在未提交前频繁向数据库发送无用 SQL
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ==========================================
# 3. 依赖注入函数 (Dependency Injection)
# ==========================================
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 的专属依赖函数。
    每次接收到 API 请求时，它会生成一个 db session。
    利用 yield 机制，在路由函数执行完毕后，finally 块会确保连接被正确关闭并归还到连接池。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 4. 初始化建表函数 (供 main.py 启动时调用)
# ==========================================
def init_db():
    """
    启动时基于我们写的 entities 自动在 MySQL 中生成对应的表结构。
    注意：在企业级生产环境中，如果表结构需要频繁修改，推荐使用 Alembic 做版本控制迁移，
    但目前在从零开发阶段，直接 create_all 是最快捷的。
    """
    from core.logger import logger
    try:
        # Base.metadata.create_all 会扫描所有继承自 Base 的类，并生成建表 SQL
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表结构同步成功！")
    except Exception as e:
        logger.error(f"数据库连接或建表失败: {e}")
        raise e