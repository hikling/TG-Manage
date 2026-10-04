<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Puzzle, RefreshCw, Plus, Trash2, Search, ExternalLink } from 'lucide-vue-next'
import { panelRequest } from '../lib/api/communications'
import { errorText } from '../composables/usePanelAccount'
import { useConfirm } from '../composables/useConfirm'

type Runtime = { account: string; status: string; enabled: boolean; version: string; message?: string; plugins: { name: string; kind: string }[]; automations: { name: string; source: string; triggers: string[] }[] }
type CatalogItem = { name: string; description: string }
type Catalog = { source: string; items: CatalogItem[]; stale: boolean }
const { confirm } = useConfirm()
const route = useRoute()
const accounts = ref<Runtime[]>([])
const selected = ref('')
const catalog = ref<CatalogItem[]>([])
const catalogStale = ref(false)
const catalogError = ref('')
const catalogLoading = ref(false)
const query = ref('')
const visibleCount = ref(24)
const upstream = ref('')
const version = ref('')
const pluginName = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const success = ref('')
let poller: ReturnType<typeof setInterval> | undefined
const selectedRuntime = computed(() => accounts.value.find(item => item.account === selected.value))
const installedNames = computed(() => new Set(
  selectedRuntime.value?.plugins.filter(item => item.kind !== 'builtin').map(item => item.name) || [],
))
const filteredCatalog = computed(() => {
  const term = query.value.trim().toLocaleLowerCase()
  return catalog.value.filter(item => !term || item.name.toLocaleLowerCase().includes(term) ||
    item.description.toLocaleLowerCase().includes(term))
})
const shownCatalog = computed(() => filteredCatalog.value.slice(0, visibleCount.value))
function automationLabel(name: string) {
  if (selectedRuntime.value?.status !== 'running') return 'TeleBox 未运行'
  const triggers = selectedRuntime.value?.automations?.find(item => item.name === name)?.triggers || []
  if (!triggers.length) return '未声明内置监听或定时'
  return triggers.map(trigger => ({ message: '消息监听', event: '事件处理', cron: '插件定时' })[trigger as 'message' | 'event' | 'cron'] || trigger).join(' · ')
}

async function loadCatalog() {
  catalogLoading.value = true; catalogError.value = ''
  try {
    const data = await panelRequest<Catalog>('/telebox/catalog')
    catalog.value = data.items
    catalogStale.value = data.stale
  } catch (err) { catalogError.value = errorText(err) }
  finally { catalogLoading.value = false }
}

async function load(silent = false) {
  try {
    const data = await panelRequest<{ version: string; upstream_commit: string; accounts: Runtime[] }>('/telebox')
    version.value = data.version; upstream.value = data.upstream_commit; accounts.value = data.accounts
    if (!accounts.value.some(item => item.account === selected.value)) {
      const requested = typeof route.query.account === 'string' ? route.query.account : ''
      selected.value = accounts.value.some(item => item.account === requested) ? requested : accounts.value[0]?.account || ''
    }
    if (!silent) error.value = ''
  } catch (err) { if (!silent) error.value = errorText(err) }
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
  if (!selected.value || busy.value || (action === 'install' && !(name || pluginName.value.trim()))) return
  const chosen = name || pluginName.value.trim()
  if (action === 'uninstall' && !await confirm({ title: '卸载 TeleBox 插件', message: `确认卸载 ${chosen}？插件数据可能仍保留在账号目录。`, danger: true })) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    await panelRequest(`/telebox/${encodeURIComponent(selected.value)}/plugins`, 'POST', { action, name: action === 'reload' ? undefined : chosen })
    pluginName.value = ''; success.value = `TeleBox 插件操作已完成：${action}`; await load(true)
  } catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}

onMounted(() => { void load(); void loadCatalog(); poller = setInterval(() => void load(true), 5000) })
onUnmounted(() => { if (poller) clearInterval(poller) })
</script>

<template>
  <div class="panel-stack">
    <section class="panel-card">
      <p class="panel-eyebrow"><Puzzle :size="18" />账号自动化</p>
      <h2 class="panel-title">内置 TeleBox</h2>
      <p class="panel-muted">在账号管理登录时选择启用 TeleBox，成功后自动启动。安装插件后，插件自带的监听与定时规则由 TeleBox 持续运行。</p>
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
        <p v-if="!accounts.find(item => item.account === selected)?.enabled" class="panel-muted">此账号未启用 TeleBox；请从账号管理重新登录并勾选启用。</p>
        <form v-if="accounts.find(item => item.account === selected)?.status === 'password_required'" class="panel-row" @submit.prevent="submitPassword">
          <input v-model="password" type="password" autocomplete="new-password" class="panel-input flex-1" placeholder="Telegram 两步验证密码" required />
          <button class="panel-button primary" :disabled="busy">确认授权</button>
        </form>
      </template>
    </section>
    <div class="panel-columns">
      <section v-if="selected" class="panel-card panel-stack">
        <h3>拓展插件 · TeleBox</h3>
        <p class="panel-muted">内置命令保留，已安装的 TPM 插件属于当前账号。</p>
        <details class="panel-muted text-sm">
          <summary class="cursor-pointer">按插件名安装</summary>
          <form class="panel-row mt-3" @submit.prevent="plugin('install')">
            <input v-model="pluginName" class="panel-input flex-1" aria-label="TeleBox TPM 插件名" placeholder="插件名" pattern="[A-Za-z0-9_-]+" required />
            <button class="panel-button primary" :disabled="busy || selectedRuntime?.status !== 'running'"><Plus :size="17" aria-hidden="true" />安装</button>
          </form>
        </details>
        <div class="panel-row"><button class="panel-button" :disabled="busy" @click="plugin('reload')"><RefreshCw :size="16" />重载插件</button><button class="panel-button" :disabled="busy" @click="plugin('update')">更新全部插件</button></div>
        <div v-for="item in accounts.find(row => row.account === selected)?.plugins || []" :key="`${item.kind}:${item.name}`" class="panel-row border-b border-[var(--sp-border)] py-2">
          <span class="flex-1">{{ item.name }} <small class="panel-muted">{{ item.kind === 'builtin' ? '内置' : automationLabel(item.name) }}</small></span>
          <template v-if="item.kind !== 'builtin'">
            <button class="panel-button danger" :disabled="busy" :aria-label="`卸载 ${item.name}`" @click="plugin('uninstall', item.name)"><Trash2 :size="16" /></button>
          </template>
        </div>
      </section>
      <section class="panel-card panel-stack plugin-center" :class="{ 'plugin-center-only': !selected }">
        <div class="panel-row">
          <div class="flex-1"><p class="panel-eyebrow">OFFICIAL CATALOG</p><h3>插件中心</h3></div>
          <button type="button" class="panel-button" :disabled="catalogLoading" aria-label="刷新插件目录" @click="loadCatalog"><RefreshCw :size="16" aria-hidden="true" />刷新</button>
        </div>
        <p class="panel-muted text-sm">来自 <a class="plugin-source" href="https://github.com/TeleBoxOrg/TeleBox-Plugins" target="_blank" rel="noopener noreferrer">TeleBox 官方插件仓库 <ExternalLink :size="13" aria-hidden="true" /></a>。安装后自动加载；只有插件自身声明的监听、事件或定时规则会持续运行。</p>
        <label class="plugin-search"><Search :size="17" aria-hidden="true" /><span class="sr-only">搜索插件</span><input v-model="query" type="search" placeholder="搜索名称或功能" @input="visibleCount = 24" /></label>
        <p v-if="catalogError" class="panel-error" role="alert">{{ catalogError }} <button type="button" class="underline" @click="loadCatalog">重试</button></p>
        <p v-if="catalogStale" class="panel-muted text-sm" role="status">当前展示缓存目录，官方源暂时不可用。</p>
        <p v-if="catalogLoading && !catalog.length" class="panel-empty" role="status">正在加载插件目录…</p>
        <p v-else-if="!filteredCatalog.length && !catalogError" class="panel-empty">没有找到匹配的插件。</p>
        <div v-else-if="shownCatalog.length" class="plugin-list">
          <article v-for="item in shownCatalog" :key="item.name" class="plugin-item">
            <div class="plugin-item-copy"><strong>{{ item.name }}</strong><p>{{ item.description || '官方插件' }}</p><small v-if="installedNames.has(item.name)" class="panel-muted">{{ automationLabel(item.name) }}</small></div>
            <span v-if="installedNames.has(item.name)" class="plugin-installed">已安装</span>
            <button v-else type="button" class="panel-button primary" :disabled="busy || selectedRuntime?.status !== 'running'" :aria-label="`为 ${selected} 安装 ${item.name}`" @click="plugin('install', item.name)">安装</button>
          </article>
          <button v-if="shownCatalog.length < filteredCatalog.length" type="button" class="panel-button w-full" @click="visibleCount += 24">显示更多（{{ filteredCatalog.length - shownCatalog.length }}）</button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.plugin-center { align-self: start; }
.plugin-center-only { grid-column: 1 / -1; }
.plugin-source { display: inline-flex; align-items: center; gap: .2rem; color: var(--sp-accent); font-weight: 650; text-decoration: underline; text-underline-offset: 3px; }
.plugin-search { display: flex; align-items: center; gap: .65rem; min-height: 46px; padding: 0 .9rem; border: 1px solid var(--sp-border-strong); border-radius: 11px; color: var(--sp-text-muted); background: var(--sp-bg-elevated); }
.plugin-search:focus-within { outline: 2px solid var(--sp-accent); outline-offset: 2px; }
.plugin-search input { width: 100%; min-width: 0; outline: none; background: transparent; color: var(--sp-text); font-size: .9rem; }
.plugin-list { display: grid; gap: 8px; }
.plugin-item { display: flex; align-items: center; gap: 12px; min-width: 0; padding: 13px 14px; border: 1px solid var(--sp-border); border-radius: 12px; background: var(--sp-bg-elevated-2); }
.plugin-item-copy { flex: 1; min-width: 0; }
.plugin-item-copy strong { display: block; font-size: .9rem; color: var(--sp-text); overflow-wrap: anywhere; }
.plugin-item-copy p { margin-top: 3px; font-size: .8rem; line-height: 1.45; color: var(--sp-text-muted); overflow-wrap: anywhere; }
.plugin-installed { flex: none; padding: .35rem .6rem; border-radius: 999px; background: var(--sp-accent-soft); color: var(--sp-accent); font-size: .75rem; font-weight: 700; }
.plugin-item .panel-button { flex: none; min-height: 40px; }
@media (max-width: 480px) {
  .plugin-item { flex-wrap: wrap; }
  .plugin-item-copy { flex-basis: 100%; }
}
</style>
