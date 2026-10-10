import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAccountsStore } from '../stores/accounts'
import i18n from '../i18n'
import { getLocalizedErrorMessage } from '../lib/types'

export const errorText = (error: unknown) => getLocalizedErrorMessage(
  error,
  key => String(i18n.global.t(key)),
  String(i18n.global.t('common.requestFailed')),
)
export function usePanelAccount() {
  const store = useAccountsStore(); const route = useRoute(); const account = ref(''); const error = ref('')
  onMounted(async () => {
    try { await store.ensureAccounts(); const selected = typeof route.query.account === 'string' ? route.query.account : ''; account.value = store.accounts.some(a => a.name === selected) ? selected : store.accounts[0]?.name || '' }
    catch (e) { error.value = errorText(e) }
  })
  return {store, account, error}
}
