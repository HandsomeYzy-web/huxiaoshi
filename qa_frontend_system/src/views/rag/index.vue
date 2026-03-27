<template>
  <div class="legacy-page">
    <h2>知识库页面已迁移到工作台</h2>
    <p>请使用“知识库管理”或“文件处理”模块继续操作。</p>
    <div class="actions">
      <router-link class="link" to="/workspace/knowledge-bases">知识库管理</router-link>
      <router-link class="link secondary" to="/workspace/files">文件处理</router-link>
    </div>
  </div>
</template>

<style scoped>
.legacy-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  text-align: center;
  gap: 16px;
  padding: 24px;
}

.actions {
  display: flex;
  gap: 12px;
}

.link {
  display: inline-flex;
  padding: 10px 16px;
  border-radius: 999px;
  text-decoration: none;
  color: #fff;
  background: #1d4540;
}

.secondary {
  background: #5f746d;
}
</style>
