"""
权限相关常量 — 系统内所有可分配的权限 code 及其元信息。
管理员在初始化时会将这些权限写入数据库。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PermDef:
    code: str
    name: str
    description: str
    module: str


# ─── 知识库模块 ───────────────────────────────────────────────
KB_MANAGE = PermDef("kb.manage", "管理知识库", "可创建、编辑、删除知识库", "kb")
KB_QUERY = PermDef("kb.query", "检索知识库", "可在知识库中执行问答检索", "kb")

# ─── 文件模块 ─────────────────────────────────────────────────
FILE_MANAGE = PermDef("file.manage", "管理文件", "可上传、删除知识库文件", "file")

# ─── 聊天模块 ─────────────────────────────────────────────────
CHAT_USE = PermDef("chat.use", "使用聊天", "可使用跨库聊天功能", "chat")

# ─── QA测试模块 ───────────────────────────────────────────────
QA_TEST = PermDef("qa.test", "召回测试", "可使用QA召回测试功能", "qa")

# ─── 管理员模块 ───────────────────────────────────────────────
ADMIN_ROLES = PermDef("admin.roles", "管理角色", "可创建、编辑、删除角色及分配权限", "admin")
ADMIN_USERS = PermDef("admin.users", "管理用户", "可查看用户列表及分配角色", "admin")
ADMIN_KB_ACCESS = PermDef("admin.kb_access", "知识库访问控制", "可配置知识库对哪些角色可见", "admin")

# 所有权限列表（用于初始化）
ALL_PERMISSIONS: list[PermDef] = [
    KB_MANAGE, KB_QUERY,
    FILE_MANAGE,
    CHAT_USE,
    QA_TEST,
    ADMIN_ROLES, ADMIN_USERS, ADMIN_KB_ACCESS,
]

# 普通用户默认权限
DEFAULT_USER_PERMISSIONS: list[str] = [KB_QUERY.code, CHAT_USE.code]

# 管理员拥有所有权限
ADMIN_PERMISSIONS: list[str] = [p.code for p in ALL_PERMISSIONS]
