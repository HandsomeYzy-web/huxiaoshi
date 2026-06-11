<template>
  <div class="text2sql-panel">
    <section class="panel-card">
      <div class="panel-header">
        <div>
          <div class="panel-title">Text2SQL 数据库连接配置</div>
          <div class="panel-subtitle">配置用于 Text2SQL 自然语言转 SQL 功能的业务数据库连接。</div>
        </div>

      </div>

      <el-alert
        v-if="!canUpdate"
        title="当前账户对数据库连接设置是只读的，无修改权限。"
        type="warning"
        :closable="false"
        show-icon
        class="block-alert"
      />

      <el-form v-loading="loading" :model="form" label-position="top" class="form-grid">
        <el-form-item label="数据库类型 (DB Type)">
          <el-select v-model="form.db_type" style="width: 100%" @change="handleDbTypeChange">
            <el-option label="MySQL" value="mysql" />
            <el-option label="SQL Server" value="sqlserver" />
          </el-select>
        </el-form-item>
        <el-form-item label="主机 (Host)">
          <el-input v-model="form.host" placeholder="127.0.0.1" />
        </el-form-item>
        <el-form-item label="端口 (Port)">
          <el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" />
        </el-form-item>
        <el-form-item label="用户名 (Username)">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码 (Password)">
          <el-input v-model="form.password" type="password" show-password placeholder="留空以复用已保存的密码" />
          <div v-if="configured && hasPassword && !form.password" class="password-tip">
            密码已保存。如果连接目标没有改变，留空将直接复用该密码。
          </div>
        </el-form-item>
        <el-form-item label="数据库名称 (Database)">
          <el-input v-model="form.database" />
        </el-form-item>
        <el-form-item label="字符集 (Charset)">
          <el-input v-model="form.charset" placeholder="utf8mb4" />
        </el-form-item>
      </el-form>

      <div class="form-actions">
        <el-button :disabled="saving || testing" @click="loadConnection">重新加载</el-button>
        <el-button type="success" :loading="testing" :disabled="!canUpdate || saving" @click="handleTest">
          测试连接
        </el-button>
        <el-button type="primary" :loading="saving" :disabled="!canUpdate || testing" @click="handleSave">
          保存连接
        </el-button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  getText2SQLConnection,
  saveText2SQLConnection,
  testText2SQLConnection,
  type Text2SQLConnectionPayload,
  type Text2SQLConnectionResponse,
  type Text2SQLDbType,
} from '../../api/text2sql'

// 各数据库类型的默认端口与字符集；切换类型时若当前值仍是其它类型的默认值，则自动跟随切换。
const DB_TYPE_DEFAULTS: Record<Text2SQLDbType, { port: number; charset: string }> = {
  mysql: { port: 3306, charset: 'utf8mb4' },
  sqlserver: { port: 1433, charset: 'UTF-8' },
}
const KNOWN_DEFAULT_PORTS = Object.values(DB_TYPE_DEFAULTS).map((item) => item.port)
const KNOWN_DEFAULT_CHARSETS = Object.values(DB_TYPE_DEFAULTS).map((item) => item.charset)

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const configured = ref(false)
const hasPassword = ref(false)

const form = reactive<Text2SQLConnectionPayload>({
  db_type: 'mysql',
  host: '',
  port: 3306,
  username: '',
  password: '',
  database: '',
  charset: 'utf8mb4',
})

const canUpdate = computed(() => true)

function applyConnection(data: Text2SQLConnectionResponse) {
  configured.value = data.configured
  hasPassword.value = data.has_password
  form.db_type = data.db_type ?? 'mysql'
  form.host = data.host ?? ''
  form.port = data.port || 3306
  form.username = data.username ?? ''
  form.password = ''
  form.database = data.database ?? ''
  form.charset = data.charset || 'utf8mb4'
}

function handleDbTypeChange(dbType: Text2SQLDbType) {
  const defaults = DB_TYPE_DEFAULTS[dbType] ?? DB_TYPE_DEFAULTS.mysql
  // 仅在端口/字符集仍是「某个类型的默认值」时才自动切换，避免覆盖用户手填的自定义值。
  if (!form.port || KNOWN_DEFAULT_PORTS.includes(form.port)) {
    form.port = defaults.port
  }
  const currentCharset = String(form.charset ?? '').trim()
  if (!currentCharset || KNOWN_DEFAULT_CHARSETS.includes(currentCharset)) {
    form.charset = defaults.charset
  }
}

function buildPayload(): Text2SQLConnectionPayload {
  const password = String(form.password ?? '').trim()
  const dbType: Text2SQLDbType = form.db_type === 'sqlserver' ? 'sqlserver' : 'mysql'
  const defaults = DB_TYPE_DEFAULTS[dbType]
  return {
    db_type: dbType,
    host: form.host.trim(),
    port: form.port,
    username: form.username.trim(),
    password: password ? password : null,
    database: form.database.trim(),
    charset: form.charset.trim() || defaults.charset,
  }
}

function validatePayload(payload: Text2SQLConnectionPayload) {
  if (!payload.host || !payload.username || !payload.database) {
    ElMessage.warning('主机（Host）、用户名（Username）和数据库名称（Database）为必填项。')
    return false
  }
  return true
}

async function loadConnection() {
  loading.value = true
  try {
    const data = await getText2SQLConnection()
    applyConnection(data)
  } finally {
    loading.value = false
  }
}

async function handleTest() {
  const payload = buildPayload()
  if (!validatePayload(payload)) return

  testing.value = true
  try {
    const data = await testText2SQLConnection(payload)
    ElMessage.success(data.message || '数据库连接测试成功。')
  } finally {
    testing.value = false
  }
}

async function handleSave() {
  const payload = buildPayload()
  if (!validatePayload(payload)) return

  saving.value = true
  try {
    const data = await saveText2SQLConnection(payload)
    applyConnection(data)
    ElMessage.success('数据库连接已成功保存。')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadConnection()
})
</script>

<style scoped>
.text2sql-panel {
  min-height: calc(100vh - 220px);
}

.panel-card {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid #ead8c6;
  background: linear-gradient(180deg, #fffdfb 0%, #f9f2e8 100%);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 22px;
  font-weight: 700;
  color: #4a2a24;
}

.panel-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #81695b;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 14px;
}

.password-tip {
  margin-top: 6px;
  font-size: 12px;
  color: #7d6758;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.block-alert {
  margin-bottom: 12px;
}

@media (max-width: 980px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
