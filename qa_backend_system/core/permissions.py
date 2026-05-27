from dataclasses import dataclass


@dataclass(frozen=True)
class PermDef:
    code: str
    name: str
    description: str
    module: str
    parent_code: str | None = None
    icon: str | None = None
    path: str | None = None
    # type 仅为展示/分类字段（'feature' | 'admin'），供前端渲染用。
    # 后端权限校验只依赖 permission_code，与 type 无关。
    type: str = "feature"
    status: str = "active"
    sort: int = 0


@dataclass(frozen=True)
class RoleSeed:
    code: str
    name: str
    description: str
    role_type: str
    status: str = "active"
    permissions: tuple[str, ...] = ()


# ═══════════════════════════════════════════════════════════════
# 三级权限树定义
# Level 1: 菜单分组（左侧Tab栏目）
# Level 2: 子页面/子目录
# Level 3: 增删查改业务操作
# ═══════════════════════════════════════════════════════════════

ALL_PERMISSIONS: list[PermDef] = [
    # ─── Level 1: 菜单分组 ────────────────────────────────────
    PermDef("chat", "智能问答", "智能问答模块", "chat",
            icon="ChatDotRound", path="/chat", sort=10),
    PermDef("workspace", "工作台", "工作台模块", "workspace",
            icon="DataAnalysis", path="/", sort=20),
    PermDef("admin", "系统管理", "系统管理模块", "admin",
            icon="Setting", path="/admin", type="admin", sort=90),

    # ─── Level 2: 子页面 ──────────────────────────────────────
    # chat 下
    PermDef("chat.use", "对话问答", "访问聊天问答能力", "chat",
            parent_code="chat", path="/chat", sort=11),

    # workspace 下
    PermDef("workspace.overview", "工作台概览", "查看工作台概览", "workspace",
            parent_code="workspace", icon="DataAnalysis", path="/workspace/overview", sort=21),
    PermDef("workspace.kb", "知识库管理", "知识库管理页面", "workspace",
            parent_code="workspace", icon="FolderOpened", path="/workspace/knowledge-bases", sort=22),
    PermDef("workspace.file", "文件处理", "文件管理页面", "workspace",
            parent_code="workspace", icon="Files", path="/workspace/files", sort=23),
    PermDef("workspace.qa", "问答测试", "问答测试页面", "workspace",
            parent_code="workspace", icon="ChatLineRound", path="/workspace/qa-test", sort=24),

    # admin 下
    PermDef("admin.role", "角色管理", "管理系统角色", "admin",
            parent_code="admin", type="admin", sort=91),
    PermDef("admin.user", "用户管理", "管理系统用户", "admin",
            parent_code="admin", type="admin", sort=92),
    PermDef("admin.permission", "权限管理", "管理权限定义", "admin",
            parent_code="admin", type="admin", sort=93),
    PermDef("admin.kb_access", "知识库授权", "配置知识库角色访问", "admin",
            parent_code="admin", type="admin", sort=94),
    PermDef("admin.model", "模型配置", "管理模型配置", "admin",
            parent_code="admin", type="admin", sort=95),

    # ─── Level 3: 业务操作 ────────────────────────────────────
    # workspace.kb 下
    PermDef("kb.view", "查看知识库", "查看知识库列表和详情", "workspace",
            parent_code="workspace.kb", sort=221),
    PermDef("kb.create", "创建知识库", "创建知识库", "workspace",
            parent_code="workspace.kb", sort=222),
    PermDef("kb.update", "编辑知识库", "编辑知识库配置", "workspace",
            parent_code="workspace.kb", sort=223),
    PermDef("kb.delete", "删除知识库", "删除知识库", "workspace",
            parent_code="workspace.kb", sort=224),
    PermDef("kb.grant", "知识库授权", "配置知识库角色访问范围", "workspace",
            parent_code="workspace.kb", sort=225),

    # workspace.file 下
    PermDef("file.upload", "上传文件", "上传文件到知识库", "workspace",
            parent_code="workspace.file", sort=231),
    PermDef("file.delete", "删除文件", "删除知识库文件", "workspace",
            parent_code="workspace.file", sort=232),
    PermDef("file.reprocess", "重新处理", "重新处理文件切分", "workspace",
            parent_code="workspace.file", sort=233),

    # workspace.qa 下
    PermDef("qa.run", "执行测试", "执行问答召回测试", "workspace",
            parent_code="workspace.qa", sort=241),

    # admin.role 下
    PermDef("role.view", "查看角色", "查看角色列表", "admin",
            parent_code="admin.role", type="admin", sort=911),
    PermDef("role.create", "创建角色", "创建角色", "admin",
            parent_code="admin.role", type="admin", sort=912),
    PermDef("role.update", "编辑角色", "编辑角色", "admin",
            parent_code="admin.role", type="admin", sort=913),
    PermDef("role.delete", "删除角色", "删除角色", "admin",
            parent_code="admin.role", type="admin", sort=914),
    PermDef("role.assign", "角色授权", "为角色配置权限", "admin",
            parent_code="admin.role", type="admin", sort=915),

    # admin.user 下
    PermDef("user.view", "查看用户", "查看用户列表", "admin",
            parent_code="admin.user", type="admin", sort=921),
    PermDef("user.assign", "分配角色", "为用户分配角色", "admin",
            parent_code="admin.user", type="admin", sort=922),

    # admin.permission 下
    PermDef("permission.view", "查看权限", "查看权限定义", "admin",
            parent_code="admin.permission", type="admin", sort=931),
    PermDef("permission.create", "创建权限", "创建权限定义", "admin",
            parent_code="admin.permission", type="admin", sort=932),
    PermDef("permission.update", "编辑权限", "编辑权限定义", "admin",
            parent_code="admin.permission", type="admin", sort=933),
    PermDef("permission.delete", "删除权限", "删除权限定义", "admin",
            parent_code="admin.permission", type="admin", sort=934),

    # admin.kb_access 下
    PermDef("kb_access.view", "查看授权", "查看知识库授权配置", "admin",
            parent_code="admin.kb_access", type="admin", sort=941),
    PermDef("kb_access.assign", "配置授权", "配置知识库角色访问", "admin",
            parent_code="admin.kb_access", type="admin", sort=942),

    # admin.model 下
    PermDef("model.view", "查看模型", "查看模型配置", "admin",
            parent_code="admin.model", type="admin", sort=951),
    PermDef("model.create", "创建模型", "创建模型配置", "admin",
            parent_code="admin.model", type="admin", sort=952),
    PermDef("model.update", "编辑模型", "编辑模型配置", "admin",
            parent_code="admin.model", type="admin", sort=953),
    PermDef("model.delete", "删除模型", "删除模型配置", "admin",
            parent_code="admin.model", type="admin", sort=954),
    PermDef("model.activate", "启用模型", "激活模型配置", "admin",
            parent_code="admin.model", type="admin", sort=955),
]

DEFAULT_USER_ROLE_CODE = "base_user"
SUPER_ADMIN_ROLE_CODE = "super_admin"

DEFAULT_ROLE_SEEDS: list[RoleSeed] = [
    RoleSeed(
        code=SUPER_ADMIN_ROLE_CODE,
        name="超级管理员",
        description="系统最高管理角色",
        role_type="system",
        permissions=tuple(item.code for item in ALL_PERMISSIONS),
    ),
    RoleSeed(
        code=DEFAULT_USER_ROLE_CODE,
        name="默认用户",
        description="系统默认用户角色",
        role_type="system",
        permissions=(
            "chat", "chat.use",
            "workspace", "workspace.overview",
            "workspace.kb", "kb.view", "kb.create", "kb.update", "kb.delete",
            "workspace.file", "file.upload", "file.delete", "file.reprocess",
            "workspace.qa", "qa.run",
        ),
    ),
]
