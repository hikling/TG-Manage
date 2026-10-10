import { ref, watch } from 'vue'
import i18n from '../i18n'

export interface ConfirmOptions {
  title: string
  message: string
  /** 确认按钮文案，默认走 i18n common.confirm */
  confirmText?: string
  /** 取消按钮文案，默认走 i18n common.cancel */
  cancelText?: string
  /** 危险操作：红色确认按钮 */
  danger?: boolean
}

interface ConfirmState extends ConfirmOptions {
  open: boolean
}

const state = ref<ConfirmState>({
  open: false,
  title: '',
  message: '',
  confirmText: undefined,
  cancelText: undefined,
  danger: false,
})

let pending: {
  resolve: (value: boolean) => void
} | null = null

function close(result: boolean) {
  state.value = {
    ...state.value,
    open: false,
  }
  const p = pending
  pending = null
  p?.resolve(result)
}

// A pending decision is cancelled when its resolved text belongs to the old locale.
watch(i18n.global.locale, () => close(false))

/**
 * 全局确认对话框（Promise 化），替代 window.confirm
 */
export function useConfirm() {
  const confirm = (options: ConfirmOptions): Promise<boolean> => {
    // 若已有未关闭的对话框，先以 false 结束，避免悬挂
    if (pending) {
      pending.resolve(false)
      pending = null
    }
    return new Promise<boolean>((resolve) => {
      pending = { resolve }
      state.value = {
        open: true,
        title: options.title,
        message: options.message,
        confirmText: options.confirmText,
        cancelText: options.cancelText,
        danger: !!options.danger,
      }
    })
  }

  const accept = () => close(true)
  const cancel = () => close(false)

  return {
    state,
    confirm,
    accept,
    cancel,
  }
}
