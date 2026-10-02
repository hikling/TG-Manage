import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAccountsStore } from '../stores/accounts'
export const errorText = (error: unknown) => error instanceof Error ? error.message : '请求失败，请重试'
export function usePanelAccount() {
  const store = useAccountsStore(); const route = useRoute(); const account = ref(''); const error = ref('')
  onMounted(async () => {
    try { await store.ensureAccounts(); const selected = typeof route.query.account === 'string' ? route.query.account : ''; account.value = store.accounts.some(a => a.name === selected) ? selected : store.accounts[0]?.name || '' }
    catch (e) { error.value = errorText(e) }
  })
  return {store, account, error}
}
