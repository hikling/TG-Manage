import { request, requestBlob, fetchWithAuth, getAuthToken, MEDIUM_TIMEOUT_MS } from './core'
export interface Dialog { id: string; title: string; username?: string; type: string; unread_count: number; archived: boolean; last_message?: string; last_message_at?: string }
export interface Message { id: number; chat_id: string; text: string; date: string; outgoing: boolean; sender_name: string; reply_to_message_id?: number; media_type?: string; has_media: boolean }
export interface Page<T> { items: T[]; has_more: boolean; next_offset?: number; next_before_id?: number }
export interface Group { id: string; title: string; description: string; members_count?: number; username?: string }
export interface Bot { id: string; username: string; first_name: string; description: string; short_description: string; running: boolean }
export const accountPath = (account: string) => `/communications/${encodeURIComponent(account)}`
export const panelRequest = <T>(path: string, method = 'GET', data?: unknown) => request<T>(path, { method, ...(data === undefined ? {} : { body: JSON.stringify(data) }) }, getAuthToken(), MEDIUM_TIMEOUT_MS)
export const listDialogs = (account: string, query = '', offset = 0, archived = false, kind = 'all') => panelRequest<Page<Dialog>>(`${accountPath(account)}/dialogs?${new URLSearchParams({ query, offset: String(offset), limit: '50', archived: String(archived), kind })}`)
export const listMessages = (account: string, chat: string, before = 0) => panelRequest<Page<Message>>(`${accountPath(account)}/messages?${new URLSearchParams({chat_id: chat, before_id: String(before), limit: '50'})}`)
export const chatAvatar = (account: string, chat: string) => requestBlob(`/sign-tasks/chats/${encodeURIComponent(account)}/avatar/${encodeURIComponent(chat)}`, {}, getAuthToken(), MEDIUM_TIMEOUT_MS)
export const sendMessage = (account: string, chat_id: string, text: string, reply_to_message_id?: number) => panelRequest<Message>(`${accountPath(account)}/messages`, 'POST', {chat_id, text, reply_to_message_id})
export const editMessage = (account: string, chat_id: string, id: number, text: string) => panelRequest(`${accountPath(account)}/messages/${id}`, 'PUT', {chat_id, text})
export const deleteMessage = (account: string, chat_id: string, id: number) => panelRequest(`${accountPath(account)}/messages/${id}`, 'DELETE', {chat_id})
export const dialogAction = (account: string, chat_id: string, action: string) => panelRequest(`${accountPath(account)}/dialogs/action`, 'POST', {chat_id, action})
export async function uploadMedia(account: string, chat_id: string, file: File, caption: string, reply?: number) {
  const form = new FormData(); form.append('chat_id', chat_id); form.append('file', file); form.append('caption', caption)
  if (reply) form.append('reply_to_message_id', String(reply))
  const response = await fetchWithAuth(`${accountPath(account)}/media`, {}, {method: 'POST', body: form}, getAuthToken(), MEDIUM_TIMEOUT_MS)
  return response.json() as Promise<Message>
}
export const downloadMedia = (account: string, chat_id: string, id: number) => requestBlob(`${accountPath(account)}/media/${id}?${new URLSearchParams({chat_id})}`, {}, getAuthToken(), MEDIUM_TIMEOUT_MS)
