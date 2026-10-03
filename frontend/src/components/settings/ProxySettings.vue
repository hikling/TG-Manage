<script setup lang="ts">
import {ref,onMounted} from 'vue'
import {panelRequest,accountPath} from '../../lib/api/communications'
import {errorText} from '../../composables/usePanelAccount'
const items=ref<{account:string;proxy:string}[]>([]),error=ref(''),saved=ref(''),busy=ref('')
async function load(){try{items.value=(await panelRequest<{items:typeof items.value}>('/communications/proxies')).items}catch(e){error.value=errorText(e)}}
async function save(item:typeof items.value[number]){busy.value=item.account;error.value='';saved.value='';try{await panelRequest(`${accountPath(item.account)}/proxy`,'PUT',{proxy:item.proxy});saved.value=`${item.account} 的代理已保存`}catch(e){error.value=errorText(e)}finally{busy.value=''}}
onMounted(load)
</script>
<template><div class="panel-stack"><section class="panel-card"><h2 class="panel-title">代理管理</h2><p class="panel-muted">为每个 Telegram 账号配置连接代理。留空表示直接连接。</p></section><p v-if="error" class="panel-error">{{error}}</p><p v-if="saved" class="panel-success">{{saved}}</p><section class="panel-card panel-stack"><p v-if="!items.length" class="panel-empty">暂无账号，请先添加账号。</p><form v-for="item in items" :key="item.account" class="panel-stack border-b border-[var(--sp-border)] pb-5" @submit.prevent="save(item)"><label :for="`proxy-${item.account}`">{{item.account}}</label><div class="flex flex-wrap gap-3"><input :id="`proxy-${item.account}`" v-model="item.proxy" type="password" autocomplete="off" class="panel-input flex-1 min-w-48" placeholder="socks5://用户名:密码@主机:端口"/><button class="panel-button primary" :disabled="!!busy">{{busy===item.account?'保存中…':'保存代理'}}</button></div></form></section></div></template>
