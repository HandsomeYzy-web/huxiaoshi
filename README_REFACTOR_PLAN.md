# 项目重构与推进计划

## 1. 目标

这个计划解决两类问题：

1. 让当前项目从“能跑”提升到“可维护、可迭代”
2. 让后续功能推进有明确节奏，而不是继续堆页面和接口

当前项目结构：

- 前端：`qa_frontend_system`
- 后端：`qa_backend_system`

当前已具备的主要能力：

- 知识库管理
- 文件管理
- 召回测试
- Chat 对话
- RAG 检索与回答

接下来不建议直接继续叠加功能。先做结构治理，再做功能推进，整体成本更低。

---

## 2. 当前主要问题

结合现有目录和代码形态，后续最容易失控的点主要在这里：

- 前端页面文件职责过重，页面结构、状态、请求、交互混在一起
- Chat、QA、知识库相关数据流没有统一抽象
- 后端 `service` 层容易持续膨胀
- 接口契约和类型边界不够稳定
- 测试覆盖不足，重构风险高
- 工程规范还不够完整，后续多人维护成本会越来越高

---

## 3. 总体策略

采用“分阶段、小步重构、持续可运行”的方式推进。

原则：

- 不做一次性全量重写
- 每次只收敛一个模块
- 每次重构都带构建验证
- 每次结构变更都补最小测试
- 先稳定 Chat，再复制模式到其他页面和服务

---

## 4. 四阶段推进方案

### 第一阶段：稳定基础设施

目标：先把项目拉到可维护基线。

#### 前端任务

- 统一编码格式，处理历史乱码和异常文本
- 引入 `eslint`、`prettier`
- 固定 TypeScript 检查流程
- 清理无效依赖和临时类型声明
- 建立统一的目录规范和命名规范

#### 后端任务

- 补齐 `pytest`
- 梳理配置项，整理 `.env.example`
- 统一异常处理和返回结构
- 固定依赖版本，补充启动说明

#### 交付物

- 前端规范：`lint`、`format`、`type-check`
- 后端测试基础框架
- 环境变量示例文件
- 本地开发文档

#### 验收标准

- 前端可执行 `lint`、`build`
- 后端可执行最小测试集
- 新成员能根据文档在本地启动项目

---

### 第二阶段：前端结构重构

目标：把页面层变薄，把状态和展示拆开。

#### 重构方向

- `views` 只保留页面编排
- `components` 只做展示和局部交互
- `composables` 负责页面状态和业务流程
- `api` 只定义请求方法
- `types` 管理接口类型和前端模型
- `constants` 管理文案、配置和枚举

#### Chat 模块优先拆分

建议拆成这些单元：

- `ChatSessionList`
- `ChatMessageList`
- `ChatMessageBubble`
- `ChatMessageDocuments`
- `ChatComposer`
- `useChatSession`
- `useChatMessages`

#### 重点任务

- 统一聊天消息的数据结构
- 将文档引用展示独立组件化
- 将发送消息、切换会话、滚动到底部等行为抽到 composable
- 减少页面内直接写数据转换逻辑
- 梳理哪些状态属于页面局部，哪些状态适合进入 Pinia

#### 验收标准

- Chat 页主文件显著缩短
- 组件边界清晰
- 同类逻辑不再重复出现在多个页面
- 结构可复制到 `qa-test`、文件管理、知识库页面

---

### 第三阶段：后端职责重构

目标：让业务逻辑边界清晰，降低后续扩展成本。

#### 建议职责划分

- `router`：处理请求和响应
- `service`：处理业务逻辑
- `repository`：负责数据读写
- `schema`：输入输出契约
- `assembler` / `mapper`：负责复杂响应组装

#### 优先重构模块

- `services/chat_service.py`
- `services/qa_service.py`
- `services/rag_service.py`

#### 重点任务

- 把“检索”“生成”“引用整理”“会话存储”拆开
- 统一 `citation`、`involved_documents` 的转换逻辑
- 收敛 service 中重复的拼装代码
- 统一错误处理和异常语义
- 明确 chat 接口的稳定返回模型

#### 验收标准

- Chat / QA 核心流程职责清晰
- service 层可单测
- repository 不再承载业务逻辑
- 前端不依赖后端隐式字段

---

### 第四阶段：功能推进

目标：在结构稳定之后，再做真正有价值的产品能力。

#### 优先功能

- 会话重命名、删除、归档
- 文档引用点击后查看原始片段
- 流式输出回答
- 指定知识库对话
- 多轮上下文控制
- 检索参数配置化：`top_k`、阈值、重排
- 回答质量评估
- 上传解析异步化和任务进度反馈
- 操作日志和错误追踪

#### 如果要向产品化继续推进

- 用户体系
- 空间隔离和权限控制
- 审计日志
- 任务中心
- 观测与告警
- CI/CD 与部署脚本

#### 验收标准

- 核心功能具备可演示性
- 用户能理解回答来源
- 上传、检索、问答流程更完整
- 线上排障成本下降

---

## 5. 推荐迭代节奏

### 第 1 周

- 清理工程基础问题
- 增加前端 lint / format / type-check
- 增加后端测试基础设施
- 梳理环境配置和 README

### 第 2 周

- 重构 Chat 前端结构
- 提炼 Chat 通用组件和 composable
- 统一消息与文档引用展示模型

### 第 3 周

- 重构后端 chat / qa / rag 核心逻辑
- 收敛接口契约
- 增加 service 和 router 测试

### 第 4 周

- 做流式输出
- 做文档引用交互
- 做会话管理能力
- 做体验和性能优化

---

## 6. 任务优先级

如果只能先做最关键的 5 件事，按这个顺序推进：

1. 建立前端工程规范：`lint`、`format`、`type-check`
2. 重构 Chat 页面，拆组件和 composable
3. 重构后端 `chat_service` 和 `qa_service`
4. 给 Chat / QA 接口补测试
5. 统一 `citation` 和文档引用的数据模型

---

## 7. 推荐目录演进方案

### 前端建议

`qa_frontend_system/src`

- `api/`
- `components/`
- `composables/`
- `types/`
- `constants/`
- `views/`
- `stores/`
- `utils/`

Chat 目录建议进一步模块化：

- `views/chat/index.vue`
- `components/chat/ChatSessionList.vue`
- `components/chat/ChatMessageList.vue`
- `components/chat/ChatMessageBubble.vue`
- `components/chat/ChatMessageDocuments.vue`
- `components/chat/ChatComposer.vue`
- `composables/useChatSession.ts`
- `composables/useChatMessages.ts`

### 后端建议

`qa_backend_system`

- `api/routers/`
- `services/`
- `repositories/`
- `models/schemas/`
- `models/entities/`
- `core/`
- `tests/`

如果后续业务继续增加，建议新增：

- `assemblers/`
- `domain/`
- `validators/`

---

## 8. 风险与控制

### 风险 1：重构过程中功能回归

控制方式：

- 每次只改一个模块
- 每次改动后跑构建和测试
- 优先补接口测试再做内部结构调整

### 风险 2：前后端接口频繁变化

控制方式：

- 先定义稳定 schema
- 前端统一从 `api + types` 读取，不在页面里猜字段

### 风险 3：重构拖慢需求推进

控制方式：

- 采用“一个迭代只重构一个核心面”
- 新功能尽量建立在新结构上，不再给旧结构继续加复杂度

---

## 9. 里程碑定义

### M1：工程基线完成

- 前端规范工具齐全
- 后端测试框架可用
- 文档齐全

### M2：Chat 模块重构完成

- Chat 页面结构清晰
- 消息、引用、会话逻辑已拆开
- 接口类型稳定

### M3：后端问答链路重构完成

- 检索、生成、引用整理解耦
- service 可测试
- 接口行为稳定

### M4：产品能力增强

- 流式输出
- 文档引用交互
- 会话管理
- 更好的可观测性

---

## 10. 下一步落地建议

最现实的推进方式：

1. 先完成第一阶段工程基线
2. 然后只盯住 Chat 模块做一轮完整重构
3. Chat 跑通后，把模式复制到 `qa-test`、文件管理、知识库管理
4. 再开始后端 service 收敛和功能增强

建议你把后续任务拆成 issue 或看板列，最少分为：

- `基础治理`
- `前端重构`
- `后端重构`
- `功能增强`
- `测试与发布`

这样推进不会乱。
