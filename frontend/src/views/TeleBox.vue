<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Puzzle, Play, Square, RefreshCw, Plus, Trash2 } from 'lucide-vue-next'
import { panelRequest } from '../lib/api/communications'
import { errorText } from '../composables/usePanelAccount'
import { useConfirm } from '../composables/useConfirm'

type Runtime = { account: string; status: string; enabled: boolean; version: string; message?: string; plugins: { name: string; kind: string }[] }
type Entry = { time: string; level: string; message: string }
const { confirm } = useConfirm()
const route = useRoute()
const accounts = ref<Runtime[]>([])
const selected = ref('')
const logs = ref<Entry[]>([])
const upstream = ref('')
const version = ref('')
const pluginName = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const success = ref('')
let poller: ReturnType<typeof setInterval> | undefined

async function load(silent = false) {
  try {
    const data = await panelRequest<{ version: string; upstream_commit: string; accounts: Runtime[] }>('/telebox')
    version.value = data.version; upstream.value = data.upstream_commit; accounts.value = data.accounts
    if (!accounts.value.some(item => item.account === selected.value)) {
      const requested = typeof route.query.account === 'string' ? route.query.account : ''
      selected.value = accounts.value.some(item => item.account === requested) ? requested : accounts.value[0]?.account || ''
    }
    if (selected.value) logs.value = (await panelRequest<{ items: Entry[] }>(`/telebox/${encodeURIComponent(selected.value)}/logs`)).items
    if (!silent) error.value = ''
  } catch (err) { if (!silent) error.value = errorText(err) }
}

async function operate(action: 'start' | 'stop' | 'restart') {
  if (!selected.value || busy.value) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    await panelRequest(`/telebox/${encodeURIComponent(selected.value)}/${action}`, 'POST')
    await load(true)
    success.value = action === 'start' ? '已启动授权流程，正在等待独立会话' : action === 'stop' ? '已停止运行' : '正在重新启动'
  } catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}

async function submitPassword() {
  if (!selected.value || !password.value) return
  busy.value = true; error.value = ''
  try {
    await panelRequest(`/telebox/${encodeURIComponent(selected.value)}/password`, 'POST', { password: password.value })
    password.value = ''; success.value = '已提交两步验证，等待 Telegram 确认'; await load(true)
  } catch (err) { error.value = errorText(err) }
  finally { password.value = ''; busy.value = false }
}

async function plugin(action: 'install' | 'uninstall' | 'update' | 'reload', name?: string) {
  if (!selected.value || busy.value || (action === 'install' && !pluginName.value.trim())) return
  const chosen = name || pluginName.value.trim()
  if (action === 'uninstall' && !await confirm({ title: '卸载 TeleBox 插件', message: `确认卸载 ${chosen}？插件数据可能仍保留在账号目录。`, danger: true })) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    await panelRequest(`/telebox/${encodeURIComponent(selected.value)}/plugins`, 'POST', { action, name: action === 'reload' ? undefined : chosen })
    pluginName.value = ''; success.value = `TeleBox 插件操作已完成：${action}`; await load(true)
  } catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}

onMounted(() => { void load(); poller = setInterval(() => void load(true), 5000) })
onUnmounted(() => { if (poller) clearInterval(poller) })
</script>

<template>
  <div class="panel-stack">
    <section class="panel-card">
      <p class="panel-eyebrow"><Puzzle :size="18" />账号自动化</p>
      <h2 class="panel-title">内置 TeleBox</h2>
      <p class="panel-muted">每个 Telegram 账号单独授权和运行 TeleBox，内置命令、TPM 插件、账号数据各自隔离。</p>
      <p class="panel-muted text-xs mt-3">TeleBox {{ version || '—' }} · 上游版本 {{ upstream ? upstream.slice(0, 10) : '—' }}</p>
    </section>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <p v-if="success" class="panel-success" role="status">{{ success }}</p>
    <section class="panel-card panel-stack">
      <div class="panel-row"><h3>运行账号</h3><button class="panel-button" @click="load()"><RefreshCw :size="17" />刷新</button></div>
      <p v-if="!accounts.length" class="panel-empty">请先在账号管理中添加 Telegram 账号</p>
      <select v-else v-model="selected" class="panel-input" aria-label="TeleBox 运行账号" @change="load(true)">
        <option v-for="item in accounts" :key="item.account" :value="item.account">{{ item.account }} · {{ item.status }}</option>
      </select>
      <template v-if="selected">
        <p class="panel-muted">状态：{{ accounts.find(item => item.account === selected)?.status }} <span v-if="accounts.find(item => item.account === selected)?.message">· {{ accounts.find(item => item.account === selected)?.message }}</span></p>
        <div class="panel-row">
          <button class="panel-button primary" :disabled="busy" @click="operate('start')"><Play :size="17" />启动</button>
          <button class="panel-button" :disabled="busy" @click="operate('restart')"><RefreshCw :size="17" />重启</button>
          <button class="panel-button danger" :disabled="busy" @click="operate('stop')"><Square :size="17" />停止</button>
        </div>
        <form v-if="accounts.find(item => item.account === selected)?.status === 'password_required'" class="panel-row" @submit.prevent="submitPassword">
          <input v-model="password" type="password" autocomplete="new-password" class="panel-input flex-1" placeholder="Telegram 两步验证密码" required />
          <button class="panel-button primary" :disabled="busy">确认授权</button>
        </form>
      </template>
    </section>
    <div v-if="selected" class="panel-columns">
      <section class="panel-card panel-stack">
        <h3>拓展插件 · TeleBox</h3>
        <p class="panel-muted">内置命令保留，已安装的 TPM 插件属于当前账号。</p>
        <form class="panel-row" @submit.prevent="plugin('install')">
          <input v-model="pluginName" class="panel-input flex-1" placeholder="TeleBox TPM 插件名" pattern="[A-Za-z0-9_-]+" required />
          <button class="panel-button primary" :disabled="busy"><Plus :size="17" />安装</button>
        </form>
        <div class="panel-row"><button class="panel-button" :disabled="busy" @click="plugin('reload')"><RefreshCw :size="16" />重载插件</button><button class="panel-button" :disabled="busy" @click="plugin('update')">更新全部插件</button></div>
        <div v-for="item in accounts.find(row => row.account === selected)?.plugins || []" :key="`${item.kind}:${item.name}`" class="panel-row border-b border-[var(--sp-border)] py-2">
          <span class="flex-1">{{ item.name }} <small class="panel-muted">{{ item.kind === 'builtin' ? '内置' : '已安装' }}</small></span>
          <template v-if="item.kind !== 'builtin'">
            <button class="panel-button danger" :disabled="busy" :aria-label="`卸载 ${item.name}`" @click="plugin('uninstall', item.name)"><Trash2 :size="16" /></button>
          </template>
        </div>
      </section>
      <section class="panel-card panel-stack">
        <div class="panel-row"><h3>最近运行日志</h3><button class="panel-button" @click="load(true)"><RefreshCw :size="16" /></button></div>
        <p v-if="!logs.length" class="panel-empty">暂无运行记录</p>
        <div class="max-h-[540px] overflow-y-auto panel-stack"><p v-for="(entry, i) in logs" :key="i" class="text-xs leading-relaxed break-words"><time class="panel-muted">{{ new Date(entry.time).toLocaleString() }}</time> · {{ entry.message }}</p></div>
      </section>
    </div>
  </div>
</template>
