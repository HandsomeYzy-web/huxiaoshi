<template>
  <el-container class="admin-layout">
    <el-aside width="240px" class="aside-menu">
      <div class="logo">
        <el-icon :size="24" color="#409EFC"><Cpu /></el-icon>
        <span>AI Agent 控制台</span>
      </div>
      <el-menu
        :default-active="route.path"
        class="el-menu-vertical"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
        router
      >
        <el-menu-item index="/admin/kb">
          <el-icon><Document /></el-icon>
          <span>知识库与文档构建</span>
        </el-menu-item>
        <el-menu-item index="/admin/db">
          <el-icon><DataBoard /></el-icon>
          <span>业务数据库接入 (BI)</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>返回用户对话端</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <span class="page-title">{{ pageTitle }}</span>
        </div>
        <div class="header-right">
          <el-avatar :size="32" src="https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png" />
          <span class="admin-name">超级管理员</span>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Cpu, Document, DataBoard, ChatDotRound } from '@element-plus/icons-vue'

const route = useRoute()

// 动态显示顶部标题
const pageTitle = computed(() => {
  if (route.path.includes('/admin/kb')) return '📚 知识库与一级索引管理'
  if (route.path.includes('/admin/db')) return '🔌 数据源接入与表结构分析'
  return '管理控制台'
})
</script>

<style scoped>
.admin-layout { height: 100vh; background-color: #f0f2f5; }
.aside-menu { background-color: #304156; display: flex; flex-direction: column; }
.logo { height: 60px; display: flex; align-items: center; justify-content: center; gap: 10px; color: #fff; font-size: 18px; font-weight: bold; background-color: #2b3649; }
.el-menu-vertical { border-right: none; flex: 1; }
.header { background: #fff; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 1px 4px rgba(0,21,41,.08); padding: 0 20px; }
.page-title { font-size: 18px; font-weight: 600; color: #333; }
.header-right { display: flex; align-items: center; gap: 10px; }
.admin-name { font-size: 14px; color: #666; }
.main-content { padding: 24px; overflow-y: auto; }
</style>