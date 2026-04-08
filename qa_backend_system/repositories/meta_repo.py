from sqlalchemy.orm import Session

from repositories.chat_repo import ChatRepo
from repositories.file_repo import FileRepo
from repositories.kb_repo import KBRepo


class MetaRepo(KBRepo, FileRepo, ChatRepo):
    """
    统一元数据仓库 — 向后兼容的组合 facade。

    职责已拆分至三个独立子仓库：
      - KBRepo  : 知识库（KnowledgeBase）
      - FileRepo: 文件与分段（KnowledgeFile / DocumentChunk）
      - ChatRepo: 会话与消息（ChatSession / ChatMessage）

    现有 Service 层代码无需修改，直接继续使用 MetaRepo(db)。
    如需在新代码中使用更细粒度的仓库，可直接实例化子仓库：
        kb_repo   = KBRepo(db)
        file_repo = FileRepo(db)
        chat_repo = ChatRepo(db)
    """

    def __init__(self, db: Session):
        # 三个父类共享同一个 db Session，无需重复初始化
        self.db = db
