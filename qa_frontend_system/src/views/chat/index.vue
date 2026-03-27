<template>
  <div class="legacy-page">
    <h2>聊天入口已并入工作台</h2>
    <p>请使用左侧导航中的“问答测试”模块联调知识库问答接口。</p>
    <router-link class="link" to="/workspace/qa-test">前往问答测试</router-link>
  </div>
</template>

<style scoped>
.legacy-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  text-align: center;
  gap: 12px;
  padding: 24px;
}

.link {
  display: inline-flex;
  padding: 10px 16px;
  border-radius: 999px;
  text-decoration: none;
  color: #fff;
  background: #1d4540;
}
</style>
