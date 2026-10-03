<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { Search, RefreshCw, Send, Paperclip, ArrowLeft, Archive, CheckCheck, Pencil, Trash2, Reply, Download, ShieldCheck } from 'lucide-vue-next'
import { usePanelAccount, errorText } from '../composables/usePanelAccount'
import { useConfirm } from '../composables/useConfirm'
import { listDialogs, listMessages, sendMessage, uploadMedia, downloadMedia, editMessage, deleteMessage, dialogAction, type Dialog, type Message } from '../lib/api/communications'
import ChatAvatar from '../components/ChatAvatar.vue'
import { getGlobalSettings, saveGlobalSettings } from '../lib/api/settings'
import { listAccountOfficialMessages, type OfficialMessageInfo } from '../lib/api/accounts'
import { getAuthToken } from '../lib/api/core'
import { formatDateTime } from '../lib/datetime'
const {store, account, error} = usePanelAccount(); const {confirm} = useConfirm()
const enabled = ref(false), settingsReady = ref(false)
const settingsBusy = ref(false), officialLoading = ref(false)
const officialMessages = ref<OfficialMessageInfo[]>([])
let officialGeneration = 0
async function loadOfficialMessages() {
  const acc = account.value
  const gen = ++officialGeneration
  officialMessages.value = []
  if (!acc || enabled.value) return
  officialLoading.value = true
  try {
    const response = await listAccountOfficialMessages(getAuthToken(), acc, 20)
    if (gen === officialGeneration && !enabled.value && account.value === acc) officialMessages.value = response.messages
  } catch (cause) {
    if (gen === officialGeneration) error.value = errorText(cause)
  } finally {
    if (gen === officialGeneration) officialLoading.value = false
  }
}
async function toggleChatCenter() {
  if (settingsBusy.value) return
  settingsBusy.value = true
  error.value = ''
  try { await saveGlobalSettings(getAuthToken(), { chat_center_enabled: !enabled.value }) }
  catch (cause) { error.value = errorText(cause) }
  finally { settingsBusy.value = false }
}
function onChatCenterChanged(event: Event) {
  enabled.value = (event as CustomEvent<boolean>).detail === true
  if (!enabled.value) {
    ++generation; ++messageGeneration
    dialogs.value = []; messages.value = []; selected.value = null
    moreDialogs.value = false; moreMessages.value = false
    void loadOfficialMessages()
  } else {
    ++officialGeneration; officialMessages.value = []; officialLoading.value = false
    void loadDialogs()
  }
}
const CACHE_LIMIT = 5 * 1024 * 1024
function enforceMemoryLimit() {
  const size = new TextEncoder().encode(JSON.stringify({dialogs:dialogs.value, messages:messages.value})).byteLength
  if (size > CACHE_LIMIT) {
    dialogs.value = []; messages.value = []; selected.value = null
    moreDialogs.value = false; moreMessages.value = false
    error.value = '聊天缓存已超过 5 MB，已强制清理。请缩小搜索范围后重试。'
  }
}
onMounted(async () => {
  window.addEventListener('chat-center-changed', onChatCenterChanged)
  try {
    enabled.value = (await getGlobalSettings(getAuthToken())).chat_center_enabled === true
    settingsReady.value = true
    if (enabled.value) void loadDialogs()
    else void loadOfficialMessages()
  } catch (cause) { error.value = errorText(cause) }
  finally { settingsReady.value = true }
})
const dialogs=ref<Dialog[]>([]), messages=ref<Message[]>([]), selected=ref<Dialog|null>(null), query=ref(''), archived=ref(false), text=ref(''), busy=ref(false), loading=ref(false), moreDialogs=ref(false), moreMessages=ref(false), reply=ref<Message|null>(null), editing=ref<Message|null>(null), file=ref<File|null>(null)
let generation=0, messageGeneration=0, nextOffset=0, before=0, timer: ReturnType<typeof setTimeout>|undefined
async function loadDialogs(append=false) { if(!enabled.value||!account.value)return; const gen=++generation; loading.value=true; error.value=''; try{const page=await listDialogs(account.value,query.value,append?nextOffset:0,archived.value,'groups'); if(gen!==generation)return; dialogs.value=append?[...dialogs.value,...page.items]:page.items; nextOffset=page.next_offset??0; moreDialogs.value=page.has_more; enforceMemoryLimit()}catch(e){if(gen===generation)error.value=errorText(e)}finally{if(gen===generation)loading.value=false} }
async function loadMessages(older=false) { if(!enabled.value||!selected.value)return; const gen=++messageGeneration; const acc=account.value, chat=selected.value.id; try{const page=await listMessages(acc,chat,older?before:0); if(gen!==messageGeneration||account.value!==acc||selected.value?.id!==chat)return; messages.value=older?[...page.items,...messages.value]:page.items; before=page.next_before_id??0; moreMessages.value=page.has_more; enforceMemoryLimit()}catch(e){if(gen===messageGeneration)error.value=errorText(e)} }
function choose(dialog:Dialog){ selected.value=dialog; messages.value=[]; text.value=''; file.value=null; reply.value=null; editing.value=null; moreMessages.value=false; void loadMessages() }
watch(account,()=>{selected.value=null; messages.value=[]; dialogs.value=[]; ++messageGeneration; if (settingsReady.value && !enabled.value) void loadOfficialMessages(); else void loadDialogs()})
watch([query,archived],()=>{clearTimeout(timer); timer=setTimeout(()=>void loadDialogs(),300)})
onUnmounted(()=>{++generation;++messageGeneration;++officialGeneration;clearTimeout(timer);window.removeEventListener('chat-center-changed', onChatCenterChanged)})
async function submit(){if(busy.value||!selected.value||(!text.value.trim()&&!file.value))return; const acc=account.value, chat=selected.value.id; busy.value=true; error.value=''; try{if(editing.value)await editMessage(acc,chat,editing.value.id,text.value); else if(file.value)await uploadMedia(acc,chat,file.value,text.value,reply.value?.id);else await sendMessage(acc,chat,text.value,reply.value?.id); if(account.value===acc&&selected.value?.id===chat){text.value='';file.value=null;reply.value=null;editing.value=null;await loadMessages()} await loadDialogs()}catch(e){error.value=errorText(e)}finally{busy.value=false}}
async function remove(message:Message){if(!selected.value||!await confirm({title:'删除消息',message:'从 Telegram 删除此消息？此操作无法撤销。',danger:true}))return; try{await deleteMessage(account.value,selected.value.id,message.id);await loadMessages()}catch(e){error.value=errorText(e)}}
async function action(value:string){if(!selected.value)return;try{await dialogAction(account.value,selected.value.id,value);await loadDialogs();if(value==='archive'||value==='unarchive')selected.value=null}catch(e){error.value=errorText(e)}}
async function download(message:Message){try{const blob=await downloadMedia(account.value,message.chat_id,message.id);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`telegram-${message.id}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){error.value=errorText(e)}}
function selectFile(event:Event){const input=event.target as HTMLInputElement;const item=input.files?.[0];if(item&&item.size>20*1024*1024){error.value='附件不能超过 20 MB';input.value='';return}file.value=item??null}
</script>
<template>
<div class="panel-stack">
<header class="panel-card panel-row flex-wrap">
  <div class="flex-1 min-w-48"><p class="panel-eyebrow">TELEGRAM / MESSAGES</p><h2 class="panel-title">聊天中心</h2><p class="panel-muted">关闭普通聊天时仍可查看 Telegram 官方验证码。</p></div>
  <button type="button" class="panel-button" role="switch" aria-label="是否开启聊天" :aria-checked="enabled" :disabled="!settingsReady || settingsBusy" @click="toggleChatCenter">{{settingsBusy ? '保存中…' : enabled ? '关闭聊天' : '开启聊天'}}</button>
</header>
<p v-if="error" class="panel-error" role="alert">{{error}}</p>
<div v-if="!settingsReady" class="panel-card panel-empty">正在检查聊天中心设置…</div>
<section v-else-if="!enabled" class="panel-card panel-stack" aria-label="Telegram 官方验证码">
  <div class="panel-row flex-wrap"><div class="flex-1"><h3 class="panel-row"><ShieldCheck :size="20" /> Telegram 官方验证码</h3><p class="panel-muted">仅读取官方服务号 777000，其他会话和消息不会获取。</p></div><button class="panel-button" :disabled="officialLoading || !account" @click="loadOfficialMessages"><RefreshCw :size="17" />刷新</button></div>
  <label>选择账号<select v-model="account" class="panel-input mt-2"><option value="" disabled>选择账号</option><option v-for="a in store.accounts" :key="a.name" :value="a.name">{{a.name}}</option></select></label>
  <p v-if="!account" class="panel-empty">请先在账号管理登录 Telegram 账号</p>
  <p v-else-if="officialLoading" class="panel-empty" role="status">正在读取官方消息…</p>
  <p v-else-if="!officialMessages.length" class="panel-empty">暂无官方验证码消息</p>
  <article v-for="message in officialMessages" :key="message.id ?? message.date ?? message.text" class="workbench-option"><div class="min-w-0 flex-1"><div class="panel-row"><strong>Telegram · 777000</strong><time class="panel-muted">{{formatDateTime(message.date)}}</time></div><p class="whitespace-pre-wrap break-words mt-2">{{message.text || '空消息'}}</p></div></article>
</section>
<div v-else class="chat-frame">
<aside class="chat-list" :class="{'mobile-hidden':selected}"><div class="chat-list-toolbar"><div class="panel-row"><div><p class="panel-eyebrow">GROUP MESSAGES</p><h2>群组对话</h2></div><button class="panel-button" :disabled="loading" aria-label="刷新群组对话" @click="loadDialogs()"><RefreshCw :size="17"/></button></div><select v-model="account" aria-label="操作账号" class="panel-input"><option value="" disabled>选择账号</option><option v-for="a in store.accounts" :key="a.name" :value="a.name">{{a.name}}</option></select><label class="panel-search"><Search :size="18"/><input v-model="query" placeholder="搜索群组名称或用户名"/></label><div class="panel-tabs"><button :class="{active:!archived}" @click="archived=false">全部群组</button><button :class="{active:archived}" @click="archived=true">已归档</button></div></div><p v-if="!account" class="panel-empty">请先在账号管理中登录 Telegram 账号</p><p v-else-if="!dialogs.length" class="panel-empty">{{loading?'读取群组对话中…':'没有找到群组对话'}}</p><button v-for="d in dialogs" :key="d.id" class="chat-dialog" :class="{active:selected?.id===d.id}" @click="choose(d)"><ChatAvatar :account="account" :chat-id="d.id" :name="d.title"/><span class="min-w-0 flex-1"><strong class="block truncate">{{d.title}}</strong><span class="block truncate panel-muted">{{d.last_message||d.type}}</span></span><span class="chat-dialog-meta"><time v-if="d.last_message_at">{{new Date(d.last_message_at).toLocaleDateString()}}</time><span v-if="d.unread_count" class="panel-badge">{{d.unread_count}}</span></span></button><button v-if="moreDialogs" class="panel-button m-4" :disabled="loading" @click="loadDialogs(true)">加载更多群组</button></aside>
<section class="chat-main" :class="{'mobile-hidden':!selected}"><template v-if="selected"><header class="panel-row chat-heading"><button class="panel-button lg:hidden" aria-label="返回会话" @click="selected=null"><ArrowLeft :size="18"/></button><ChatAvatar :account="account" :chat-id="selected.id" :name="selected.title"/><div class="flex-1 min-w-0"><h2 class="truncate">{{selected.title}}</h2><p class="panel-muted text-sm">{{selected.type}} <span v-if="selected.username">· @{{selected.username}}</span></p></div><button class="panel-button" title="标为已读" aria-label="标为已读" @click="action('read')"><CheckCheck :size="18"/></button><button class="panel-button" :title="archived?'取消归档':'归档'" :aria-label="archived?'取消归档':'归档'" @click="action(archived?'unarchive':'archive')"><Archive :size="18"/></button><button class="panel-button" title="刷新消息" aria-label="刷新消息" @click="loadMessages()"><RefreshCw :size="18"/></button></header><div class="chat-messages"><button v-if="moreMessages" class="panel-button mx-auto" @click="loadMessages(true)">较早消息</button><p v-if="!messages.length" class="panel-empty">暂无消息，点击刷新重新读取</p><article v-for="m in messages" :key="m.id" class="chat-bubble" :class="{outgoing:m.outgoing}"><p class="chat-sender">{{m.sender_name}}</p><p class="whitespace-pre-wrap break-words">{{m.text}}</p><button v-if="m.has_media" class="panel-button mt-2" @click="download(m)"><Download :size="14"/>下载 {{m.media_type||'附件'}}</button><div class="chat-message-tools"><time>{{new Date(m.date).toLocaleString()}}</time><button aria-label="回复" @click="reply=m;editing=null"><Reply :size="14"/></button><button v-if="m.outgoing" aria-label="编辑" @click="editing=m;text=m.text;reply=null"><Pencil :size="14"/></button><button aria-label="删除" @click="remove(m)"><Trash2 :size="14"/></button></div></article></div><form class="chat-compose" @submit.prevent="submit"><div v-if="reply||editing||file" class="panel-row mb-2 text-sm"><span class="truncate">{{editing?'编辑消息':reply?`回复 ${reply.sender_name}`:file?.name}}</span><button type="button" @click="reply=null;editing=null;file=null;text=''">取消</button></div><div class="flex gap-3 items-end"><label v-if="!editing" class="panel-button" title="添加附件"><Paperclip :size="20"/><input type="file" class="sr-only" @change="selectFile"/></label><textarea v-model="text" class="panel-input flex-1" rows="2" placeholder="输入消息…" :disabled="busy" @keydown.enter.exact.prevent="submit"/><button class="panel-button primary" :disabled="busy||(!text.trim()&&!file)"><Send :size="20"/><span class="sr-only">发送</span></button></div><p class="text-xs panel-muted mt-2 text-right">Enter 发送，Shift + Enter 换行 · 附件最大 20 MB</p></form></template><div v-else class="panel-empty m-auto">选择一个会话，查看和管理 Telegram 消息</div></section>
</div></div>
</template>
