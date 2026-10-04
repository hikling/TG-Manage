import { panelRequest } from './communications'

export interface TeleBoxAccount {
  account: string
  status: string
  enabled: boolean
  authorized: boolean
  message?: string
}

export const listTeleBoxAccounts = () => panelRequest<{ accounts: TeleBoxAccount[] }>('/telebox')
export const startTeleBox = (account: string) =>
  panelRequest<TeleBoxAccount>(`/telebox/${encodeURIComponent(account)}/start`, 'POST')
export const stopTeleBox = (account: string) =>
  panelRequest<TeleBoxAccount>(`/telebox/${encodeURIComponent(account)}/stop`, 'POST')
export const logoutTeleBox = (account: string) =>
  panelRequest<TeleBoxAccount & { remote_revoked: boolean }>(`/telebox/${encodeURIComponent(account)}/logout`, 'POST')
export const submitTeleBoxPassword = (account: string, password: string) =>
  panelRequest<TeleBoxAccount>(`/telebox/${encodeURIComponent(account)}/password`, 'POST', { password })
