<template>
  <div class="overview-grid">
    <section class="hero-card">
      <div class="hero-copy">
        <div class="eyebrow">Workspace</div>
        <h2>面向知识库问答的一体化工作台</h2>
        <p>
          当前前端已经按“菜单、路由、按钮权限”三层模型组织。后续扩展功能时，只需要补充业务页面与权限元数据，
          不需要再改整套导航和鉴权骨架。
        </p>
        <div class="hero-actions">
          <router-link class="hero-link" to="/workspace/knowledge-bases">进入知识库管理</router-link>
          <router-link class="hero-link muted" to="/workspace/qa-test">进入召回测试</router-link>
        </div>
      </div>
    </section>

    <section class="summary-card">
      <div class="summary-title">当前可用模块</div>
      <div class="summary-list">
        <div class="summary-item">
          <strong>知识库管理</strong>
          <span>创建知识库，维护默认切分参数、检索阈值与重排配置。</span>
        </div>
        <div class="summary-item">
          <strong>文件处理</strong>
          <span>上传文件、轮询解析状态，并按单文件重设切分策略。</span>
        </div>
        <div class="summary-item">
          <strong>召回测试</strong>
          <span>直接联调检索接口，检查命中片段、相关分数与引用来源。</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.7fr);
  gap: 20px;
}

.hero-card,
.summary-card {
  padding: 28px;
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 40px rgba(32, 50, 45, 0.08);
}

.hero-card {
  min-height: 320px;
  background:
    radial-gradient(circle at top right, rgba(242, 217, 141, 0.35), transparent 26%),
    linear-gradient(135deg, #14362d 0%, #234940 54%, #f0ead5 180%);
  color: #f7f7f1;
}

.eyebrow {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #f2d98d;
}

h2 {
  margin: 16px 0 14px;
  max-width: 560px;
  font-size: 38px;
  line-height: 1.15;
}

p {
  max-width: 560px;
  line-height: 1.8;
  color: rgba(247, 247, 241, 0.82);
}

.hero-actions {
  display: flex;
  gap: 14px;
  margin-top: 24px;
}

.hero-link {
  display: inline-flex;
  align-items: center;
  padding: 12px 18px;
  border-radius: 999px;
  color: #16312a;
  text-decoration: none;
  font-weight: 700;
  background: #f2d98d;
}

.hero-link.muted {
  color: #f7f7f1;
  background: rgba(255, 255, 255, 0.12);
}

.summary-title {
  font-size: 20px;
  font-weight: 800;
  color: #18312a;
}

.summary-list {
  display: grid;
  gap: 14px;
  margin-top: 20px;
}

.summary-item {
  display: grid;
  gap: 6px;
  padding: 16px;
  border-radius: 18px;
  background: #f7faf7;
  border: 1px solid #e4ebe4;
}

.summary-item strong {
  color: #18312a;
}

.summary-item span {
  line-height: 1.6;
  color: #61746e;
}

@media (max-width: 1080px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }

  h2 {
    font-size: 30px;
  }

  .hero-actions {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
