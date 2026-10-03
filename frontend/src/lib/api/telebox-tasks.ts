import { panelRequest } from './communications'

export interface TeleBoxCommand { plugin: string; command: string }
export interface TeleBoxAccount {
  account: string
  status: string
  enabled: boolean
  commands: TeleBoxCommand[]
  plugins: { name: string; kind: string }[]
}
export interface TeleBoxTask {
  id: string
  name: string
  kind: 'plugin' | 'message'
  accounts: string[]
  time: string
  enabled: boolean
  plugin?: string | null
  command?: string | null
  args: string
  chats: string[]
  text: string
}
export type TaskInput = Omit<TeleBoxTask, 'id'>
export interface TeleBoxTaskRun {
  task_id: string
  task: string
  time: string
  success: boolean
  message: string
}

const root = '/telebox-tasks'
export const listTeleBoxTasks = () => panelRequest<{ items: TeleBoxTask[]; history: TeleBoxTaskRun[] }>(root)
export const listTeleBoxAccounts = () => panelRequest<{ accounts: TeleBoxAccount[] }>('/telebox')
export const createTeleBoxTask = (task: TaskInput) => panelRequest<TeleBoxTask>(root, 'POST', task)
export const updateTeleBoxTask = (id: string, task: TaskInput) => panelRequest<TeleBoxTask>(`${root}/${encodeURIComponent(id)}`, 'PUT', task)
export const deleteTeleBoxTask = (id: string) => panelRequest(`${root}/${encodeURIComponent(id)}`, 'DELETE')
export const runTeleBoxTask = (id: string) => panelRequest<TeleBoxTaskRun>(`${root}/${encodeURIComponent(id)}/run`, 'POST')
