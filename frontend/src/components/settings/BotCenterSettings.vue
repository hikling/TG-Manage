<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Bot, Plus, RefreshCw, Trash2, Send } from 'lucide-vue-next'
import { panelRequest, type Bot as BotInfo } from '../../lib/api/communications'
import { errorText } from '../../composables/usePanelAccount'
import { useConfirm } from '../../composables/useConfirm'

const { confirm } = useConfirm()
const items = ref<BotInfo[]>([])
const selected = ref<BotInfo | null>(null)
const token = ref('')
const commands = ref<{ command: string; description: string }[]>([])
const messageChat = ref('')
const messageText = ref('')
const error = ref('')
const success = ref('')
const busy = ref(false)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    items.value = (await panelRequest<{ items: BotInfo[] }>('/bots')).items
    if (selected.value) selected.value = items.value.find(item => item.id === selected.value?.id) || null
    error.value = ''
  } catch (err) { error.value = errorText(err) }
  finally { loading.value = false }
}

async function select(item: BotInfo) {
  selected.value = item
  error.value = ''
  try {
    selected.value = await panelRequest<BotInfo>(`/bots/${item.id}`)
    commands.value = (await panelRequest<{ commands: typeof commands.value }>(`/bots/${item.id}/commands`)).commands
  } catch (err) { error.value = errorText(err) }
}

async function add() {
  if (!token.value.trim()) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    const added = await panelRequest<BotInfo>('/bots', 'POST', { token: token.value.trim() })
    token.value = ''
    await load()
    await select(added)
    success.value = '机器人已接入'
  } catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}

async function saveProfile() {
  if (!selected.value) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    selected.value = await panelRequest<BotInfo>(`/bots/${selected.value.id}`, 'PUT', {
      first_name: selected.value.first_name,
      description: selected.value.description,
      short_description: selected.value.short_description,
    })
    await load(); success.value = '资料已同步到 Telegram'
  } catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}

async function saveCommands() {
  if (!selected.value) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    commands.value = (await panelRequest<{ commands: typeof commands.value }>(`/bots/${selected.value.id}/commands`, 'PUT', { commands: commands.value })).commands
    success.value = '命令菜单已同步到 Telegram'
  } catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}

async function send() {
  if (!selected.value || !messageChat.value || !messageText.value.trim()) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    await panelRequest(`/bots/${selected.value.id}/messages`, 'POST', { chat_id: messageChat.value, text: messageText.value })
    messageText.value = ''; success.value = '消息已发送'
  } catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}

async function remove() {
  if (!selected.value || !await confirm({ title: '移除机器人', message: '只删除面板中的机器人记录，不会在 Telegram 注销机器人。', danger: true })) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    await panelRequest(`/bots/${selected.value.id}`, 'DELETE')
    selected.value = null; commands.value = []; await load()
    success.value = '机器人记录已移除'
  } catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}

onMounted(load)
</script>

<template>
  <div class="panel-stack bot-center-settings">
    <section class="panel-card">
      <p class="panel-eyebrow"><Bot :size="18" />机器人中心</p>
      <h2 class="panel-title">机器人管理</h2>
      <p class="panel-muted">接入 BotFather 创建的机器人，管理公开资料、命令和消息。Token 只提交一次，之后不在页面显示。</p>
      <form class="panel-row mt-6" @submit.prevent="add">
        <label class="bot-center-field">机器人 Token
          <input v-model="token" type="password" autocomplete="off" class="panel-input mt-2" placeholder="粘贴 BotFather 提供的 Token" />
        </label>
        <button class="panel-button primary" :disabled="busy || !token.trim()"><Plus :size="18" aria-hidden="true" />接入机器人</button>
      </form>
    </section>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <p v-if="success" class="panel-success" role="status">{{ success }}</p>
    <div class="panel-columns">
      <section class="panel-card panel-stack">
        <div class="panel-row"><h3>机器人列表 · {{ items.length }}</h3><button type="button" class="panel-button" :disabled="loading" @click="load"><RefreshCw :size="17" aria-hidden="true" />{{ loading ? '读取中…' : '刷新' }}</button></div>
        <p v-if="loading && !items.length" class="panel-empty" role="status">正在读取机器人…</p>
        <p v-else-if="!items.length" class="panel-empty">尚未接入机器人</p>
        <button v-for="item in items" :key="item.id" type="button" class="panel-button justify-between bot-center-list-item" :aria-pressed="selected?.id === item.id" @click="select(item)"><span>{{ item.first_name || item.username }} · @{{ item.username }}</span><span class="panel-badge">已接入</span></button>
      </section>
      <div v-if="selected" class="panel-stack">
        <form class="panel-card panel-stack" @submit.prevent="saveProfile">
          <div class="panel-row"><h3>{{ selected.username }} · 公开资料</h3><button type="button" class="panel-button danger" @click="remove"><Trash2 :size="17" />移除</button></div>
          <label>机器人名称<input v-model="selected.first_name" class="panel-input mt-2" required maxlength="64" /></label>
          <label>简介<textarea v-model="selected.description" class="panel-input mt-2" rows="3" maxlength="512" /></label>
          <label>简短介绍<input v-model="selected.short_description" class="panel-input mt-2" maxlength="120" /></label>
          <button class="panel-button primary" :disabled="busy">保存到 Telegram</button>
        </form>
        <form class="panel-card panel-stack" @submit.prevent="saveCommands">
          <div class="panel-row"><h3>命令菜单</h3><button type="button" class="panel-button" @click="commands.push({ command: '', description: '' })"><Plus :size="17" aria-hidden="true" />添加命令</button></div>
          <div v-for="(item, index) in commands" :key="index" class="bot-center-command-row">
            <label>命令 {{ index + 1 }}<input v-model="item.command" class="panel-input mt-2" placeholder="如 start" pattern="[a-z0-9_]+" required /></label>
            <label>用途<input v-model="item.description" class="panel-input mt-2" placeholder="命令说明" required /></label>
            <button type="button" class="panel-button danger" :aria-label="`删除命令 ${index+1}`" @click="commands.splice(index, 1)"><Trash2 :size="16" /></button>
          </div>
          <button class="panel-button primary" :disabled="busy">保存命令菜单</button>
        </form>
        <form class="panel-card panel-stack" @submit.prevent="send">
          <h3>发送机器人消息</h3>
          <p class="panel-muted">目标必须先与机器人开始会话，或将机器人加入群聊。</p>
          <label>目标 Chat ID<input v-model="messageChat" class="panel-input mt-2" placeholder="目标 Chat ID" pattern="-?[0-9]+" inputmode="numeric" required /></label>
          <label>消息内容<textarea v-model="messageText" class="panel-input mt-2" rows="3" placeholder="消息内容" required /></label>
          <button class="panel-button primary" :disabled="busy"><Send :size="17" />发送</button>
        </form>
      </div>
    </div>
  </div>
</template>
