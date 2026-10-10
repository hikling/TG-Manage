<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { Search, RefreshCw, Send, Paperclip, ArrowLeft, Archive, CheckCheck, Pencil, Trash2, Reply, Download, ShieldCheck } from 'lucide-vue-next'
import { usePanelAccount, errorText } from '../composables/usePanelAccount'
import { useConfirm } from '../composables/useConfirm'
import { listDialogs, listMessages, sendMessage, uploadMedia, downloadMedia, editMessage, deleteMessage, dialogAction, type Dialog, type Message } from '../lib/api/communications'
import ChatAvatar from '../components/ChatAvatar.vue'
import { chatAvatarCache } from '../lib/chat-avatar-cache'
import { getGlobalSettings, saveGlobalSettings } from '../lib/api/settings'
import { listAccountOfficialMessages, type OfficialMessageInfo } from '../lib/api/accounts'
import { getAuthToken } from '../lib/api/core'
import { formatDateTime } from '../lib/datetime'
import { useI18n } from '../composables/useI18n'
const {store, account, error} = usePanelAccount(); const {confirm} = useConfirm()
const { t, locale } = useI18n()
watch(locale, () => { error.value = '' })
const enabled = ref(false), settingsReady = ref(false)
const settingsBusy = ref(false), officialLoading = ref(false)
const officialMessages = ref<OfficialMessageInfo[]>([])
let officialGeneration = 0
let active = true
async function loadOfficialMessages() {
  const acc = account.value
  const gen = ++officialGeneration
  officialMessages.value = []
  if (!active || !acc || enabled.value) return
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
    error.value = t('chats.cacheCleared')
  }
}
onMounted(async () => {
  window.addEventListener('chat-center-changed', onChatCenterChanged)
  try {
    const settings = await getGlobalSettings(getAuthToken())
    if (!active) return
    enabled.value = settings.chat_center_enabled === true
    settingsReady.value = true
    if (enabled.value) void loadDialogs()
    else void loadOfficialMessages()
  } catch (cause) { if (active) error.value = errorText(cause) }
  finally { if (active) settingsReady.value = true }
})
const dialogs=ref<Dialog[]>([]), messages=ref<Message[]>([]), selected=ref<Dialog|null>(null), query=ref(''), archived=ref(false), text=ref(''), busy=ref(false), loading=ref(false), moreDialogs=ref(false), moreMessages=ref(false), reply=ref<Message|null>(null), editing=ref<Message|null>(null), file=ref<File|null>(null)
let generation=0, messageGeneration=0, nextOffset=0, before=0, timer: ReturnType<typeof setTimeout>|undefined
async function loadDialogs(append=false) { if(!active||!enabled.value||!account.value)return; const gen=++generation; loading.value=true; error.value=''; try{const page=await listDialogs(account.value,query.value,append?nextOffset:0,archived.value,'groups'); if(gen!==generation)return; dialogs.value=append?[...dialogs.value,...page.items]:page.items; nextOffset=page.next_offset??0; moreDialogs.value=page.has_more; enforceMemoryLimit()}catch(e){if(gen===generation)error.value=errorText(e)}finally{if(gen===generation)loading.value=false} }
async function loadMessages(older=false) { if(!active||!enabled.value||!selected.value)return; const gen=++messageGeneration; const acc=account.value, chat=selected.value.id; try{const page=await listMessages(acc,chat,older?before:0); if(gen!==messageGeneration||account.value!==acc||selected.value?.id!==chat)return; messages.value=older?[...page.items,...messages.value]:page.items; before=page.next_before_id??0; moreMessages.value=page.has_more; enforceMemoryLimit()}catch(e){if(gen===messageGeneration)error.value=errorText(e)} }
function choose(dialog:Dialog){ selected.value=dialog; messages.value=[]; text.value=''; file.value=null; reply.value=null; editing.value=null; moreMessages.value=false; void loadMessages() }
watch(account,()=>{++generation;loading.value=false;selected.value=null; messages.value=[]; dialogs.value=[]; ++messageGeneration; if (settingsReady.value && !enabled.value) void loadOfficialMessages(); else void loadDialogs()})
watch([query,archived],()=>{clearTimeout(timer); timer=setTimeout(()=>void loadDialogs(),300)})
onUnmounted(()=>{active=false;chatAvatarCache.clear();++generation;++messageGeneration;++officialGeneration;clearTimeout(timer);window.removeEventListener('chat-center-changed', onChatCenterChanged)})
async function submit() {
  if (!active || busy.value || !selected.value || (!text.value.trim() && !file.value)) return
  const acc = account.value, chat = selected.value.id
  const ownsSelection = () => active && account.value === acc && selected.value?.id === chat
  busy.value = true
  error.value = ''
  try {
    if (editing.value) await editMessage(acc, chat, editing.value.id, text.value)
    else if (file.value) await uploadMedia(acc, chat, file.value, text.value, reply.value?.id)
    else await sendMessage(acc, chat, text.value, reply.value?.id)
    if (ownsSelection()) {
      text.value = ''; file.value = null; reply.value = null; editing.value = null
      await loadMessages()
    }
    if (active && account.value === acc) await loadDialogs()
  } catch (cause) { if (ownsSelection()) error.value = errorText(cause) }
  finally { if (active) busy.value = false }
}
async function remove(message: Message) {
  if (!active || !selected.value) return
  const acc = account.value, chat = selected.value.id
  const ownsSelection = () => active && account.value === acc && selected.value?.id === chat
  if (!await confirm({ title: t('chats.deleteMessage'), message: t('chats.deleteMessageConfirm'), danger: true }) || !ownsSelection()) return
  try {
    await deleteMessage(acc, chat, message.id)
    if (ownsSelection()) await loadMessages()
  } catch (cause) { if (ownsSelection()) error.value = errorText(cause) }
}
async function action(value: string) {
  if (!active || !selected.value) return
  const acc = account.value, chat = selected.value.id
  const ownsSelection = () => active && account.value === acc && selected.value?.id === chat
  try {
    await dialogAction(acc, chat, value)
    if (!active || account.value !== acc) return
    await loadDialogs()
    if (ownsSelection() && (value === 'archive' || value === 'unarchive')) selected.value = null
  } catch (cause) { if (ownsSelection()) error.value = errorText(cause) }
}
async function download(message:Message){try{const blob=await downloadMedia(account.value,message.chat_id,message.id);if(!active)return;const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`telegram-${message.id}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){error.value=errorText(e)}}
function selectFile(event:Event){const input=event.target as HTMLInputElement;const item=input.files?.[0];if(item&&item.size>20*1024*1024){error.value=t('chats.attachmentTooLarge');input.value='';return}file.value=item??null}
</script>
<template>
  <div class="panel-stack">
    <header class="panel-card panel-row flex-wrap">
      <div class="flex-1 min-w-48"><h2 class="panel-title">{{ t('chats.title') }}</h2><p class="panel-muted">{{ t('chats.description') }}</p></div>
      <button type="button" class="panel-button" role="switch" :aria-label="t('chats.enabled')" :aria-checked="enabled" :disabled="!settingsReady || settingsBusy" @click="toggleChatCenter">{{ settingsBusy ? t('common.saving') : enabled ? t('chats.disable') : t('chats.enable') }}</button>
    </header>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <div v-if="!settingsReady" class="panel-card panel-empty" role="status">{{ t('chats.checkingSettings') }}</div>
    <section v-else-if="!enabled" class="panel-card panel-stack" :aria-label="t('chats.officialMessages')">
      <div class="panel-row flex-wrap"><div class="flex-1"><h3 class="panel-row"><ShieldCheck :size="20" /> {{ t('chats.officialMessages') }}</h3><p class="panel-muted">{{ t('chats.officialDescription') }}</p></div><button class="panel-button" :disabled="officialLoading || !account" @click="loadOfficialMessages"><RefreshCw :size="17" />{{ t('common.refresh') }}</button></div>
      <label>{{ t('chats.chooseAccount') }}<select v-model="account" class="panel-input mt-2"><option value="" disabled>{{ t('chats.chooseAccount') }}</option><option v-for="a in store.accounts" :key="a.name" :value="a.name">{{a.name}}</option></select></label>
      <p v-if="!account" class="panel-empty">{{ t('chats.loginAccountFirst') }}</p>
      <p v-else-if="officialLoading" class="panel-empty" role="status">{{ t('chats.loadingOfficial') }}</p>
      <p v-else-if="!officialMessages.length" class="panel-empty">{{ t('chats.noOfficialMessages') }}</p>
      <article v-for="message in officialMessages" :key="message.id ?? message.date ?? message.text" class="chat-official-message"><div class="min-w-0 flex-1"><div class="panel-row"><strong>Telegram · 777000</strong><time class="panel-muted">{{formatDateTime(message.date, locale === 'en' ? 'en-US' : 'zh-CN')}}</time></div><p class="whitespace-pre-wrap break-words mt-2">{{message.text || t('chats.emptyMessage')}}</p></div></article>
    </section>
    <div v-else class="chat-frame">
      <aside class="chat-list" :class="{'mobile-hidden':selected}">
        <div class="chat-list-toolbar"><div class="panel-row"><h2>{{ t('chats.groupConversations') }}</h2><button class="panel-button" :disabled="loading" :aria-label="t('chats.refreshConversations')" @click="loadDialogs()"><RefreshCw :size="17"/></button></div>
          <select v-model="account" :aria-label="t('chats.operateAccount')" class="panel-input"><option value="" disabled>{{ t('chats.chooseAccount') }}</option><option v-for="a in store.accounts" :key="a.name" :value="a.name">{{a.name}}</option></select>
          <label class="panel-search"><Search :size="18"/><input v-model="query" :placeholder="t('chats.searchPlaceholder')"/></label>
          <div class="panel-tabs"><button :class="{active:!archived}" @click="archived=false">{{ t('chats.allGroups') }}</button><button :class="{active:archived}" @click="archived=true">{{ t('chats.archived') }}</button></div>
        </div>
        <p v-if="!account" class="panel-empty">{{ t('chats.loginAccountFirst') }}</p>
        <p v-else-if="!dialogs.length" class="panel-empty">{{loading ? t('chats.loadingConversations') : t('chats.noConversations')}}</p>
        <button v-for="d in dialogs" :key="d.id" class="chat-dialog" :class="{active:selected?.id===d.id}" @click="choose(d)"><ChatAvatar :account="account" :chat-id="d.id" :name="d.title"/><span class="min-w-0 flex-1"><strong class="block truncate">{{d.title}}</strong><span class="block truncate panel-muted">{{d.last_message||d.type}}</span></span><span class="chat-dialog-meta"><time v-if="d.last_message_at">{{new Date(d.last_message_at).toLocaleDateString(locale === 'en' ? 'en-US' : 'zh-CN')}}</time><span v-if="d.unread_count" class="panel-badge">{{d.unread_count}}</span></span></button>
        <button v-if="moreDialogs" class="panel-button m-4" :disabled="loading" @click="loadDialogs(true)">{{ t('chats.loadMore') }}</button>
      </aside>
      <section class="chat-main" :class="{'mobile-hidden':!selected}">
        <template v-if="selected">
          <header class="panel-row chat-heading"><button class="panel-button lg:hidden" :aria-label="t('chats.backToConversations')" @click="selected=null"><ArrowLeft :size="18"/></button><ChatAvatar :account="account" :chat-id="selected.id" :name="selected.title"/><div class="flex-1 min-w-0"><h2 class="truncate">{{selected.title}}</h2><p class="panel-muted text-sm">{{selected.type}} <span v-if="selected.username">· @{{selected.username}}</span></p></div><button class="panel-button" :title="t('chats.markRead')" :aria-label="t('chats.markRead')" @click="action('read')"><CheckCheck :size="18"/></button><button class="panel-button" :title="archived?t('chats.unarchive'):t('chats.archive')" :aria-label="archived?t('chats.unarchive'):t('chats.archive')" @click="action(archived?'unarchive':'archive')"><Archive :size="18"/></button><button class="panel-button" :title="t('chats.refreshMessages')" :aria-label="t('chats.refreshMessages')" @click="loadMessages()"><RefreshCw :size="18"/></button></header>
          <div class="chat-messages"><button v-if="moreMessages" class="panel-button mx-auto" @click="loadMessages(true)">{{ t('chats.olderMessages') }}</button><p v-if="!messages.length" class="panel-empty">{{ t('chats.noMessages') }}</p><article v-for="m in messages" :key="m.id" class="chat-bubble" :class="{outgoing:m.outgoing}"><p class="chat-sender">{{m.sender_name}}</p><p class="whitespace-pre-wrap break-words">{{m.text}}</p><button v-if="m.has_media" class="panel-button mt-2" @click="download(m)"><Download :size="14"/>{{ t('chats.download') }} {{m.media_type||t('chats.attachment')}}</button><div class="chat-message-tools"><time>{{new Date(m.date).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN')}}</time><button :aria-label="t('chats.reply')" :title="t('chats.reply')" @click="reply=m;editing=null"><Reply :size="14"/></button><button v-if="m.outgoing" :aria-label="t('chats.edit')" :title="t('chats.edit')" @click="editing=m;text=m.text;reply=null"><Pencil :size="14"/></button><button :aria-label="t('chats.delete')" :title="t('chats.delete')" @click="remove(m)"><Trash2 :size="14"/></button></div></article></div>
          <form class="chat-compose" @submit.prevent="submit"><div v-if="reply||editing||file" class="panel-row mb-2 text-sm"><span class="truncate">{{editing?t('chats.editMessage'):reply?t('chats.replyTo',{name:reply.sender_name}):file?.name}}</span><button type="button" @click="reply=null;editing=null;file=null;text=''">{{ t('common.cancel') }}</button></div><div class="flex gap-3 items-end"><label v-if="!editing" class="panel-button" :title="t('chats.addAttachment')"><Paperclip :size="20"/><input type="file" class="sr-only" :aria-label="t('chats.addAttachment')" @change="selectFile"/></label><textarea v-model="text" class="panel-input flex-1" rows="2" :placeholder="t('chats.messagePlaceholder')" :disabled="busy" @keydown.enter.exact.prevent="submit"/><button class="panel-button primary" :disabled="busy||(!text.trim()&&!file)" :aria-label="t('chats.send')"><Send :size="20"/><span class="sr-only">{{ t('chats.send') }}</span></button></div><p class="text-xs panel-muted mt-2 text-right">{{ t('chats.composerHint') }}</p></form>
        </template>
        <div v-else class="panel-empty m-auto">{{ t('chats.selectConversation') }}</div>
      </section>
    </div>
  </div>
</template>
