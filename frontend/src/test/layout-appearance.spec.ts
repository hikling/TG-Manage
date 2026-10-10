import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, onMounted } from 'vue'
import i18n from '../i18n'
import { flushPromises } from './composable-test-utils'

const api = vi.hoisted(() => ({
  getHeroImage: vi.fn(), getHeroSettings: vi.fn(), saveHeroSettings: vi.fn(),
  uploadHeroImage: vi.fn(), deleteHeroImage: vi.fn(), getGlobalSettings: vi.fn(), saveGlobalSettings: vi.fn(),
}))
vi.mock('../lib/api/appearance', () => ({ ...api, MAX_HERO_IMAGE_BYTES: 1024 * 1024 }))
vi.mock('../lib/api/settings', () => api)
vi.mock('vue-router', () => ({ useRoute: () => ({ name: 'dashboard' }) }))
import Layout from '../views/Layout.vue'

const cover = defineComponent({
  props: ['src', 'positionX', 'positionY'], emits: ['geometry'],
  setup(_, { emit }) { onMounted(() => emit('geometry', { width: 576, height: 336, overflowX: 96, overflowY: 126 })); },
  template: '<div class="cover-stub" />',
})
const wrappers: ReturnType<typeof mount>[] = []
function dispatchPointer(element: Element, type: string, detail: Record<string, number>) {
  const event = new Event(type, { bubbles: true })
  for (const [key, value] of Object.entries(detail)) Object.defineProperty(event, key, { value })
  element.dispatchEvent(event)
}
function showLayout() {
  const wrapper = mount(Layout, { global: { plugins: [i18n], stubs: {
    Modal: { template: '<div><slot /></div>' }, HeroCover: cover,
    UserProfileModal: true, RouterLink: { template: '<a><slot /></a>' }, RouterView: true,
  } } })
  wrappers.push(wrapper)
  return wrapper
}

describe('cover framing controls', () => {
  const previousLocale = i18n.global.locale.value
  beforeEach(() => {
    vi.useFakeTimers()
    i18n.global.locale.value = 'en-US'
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:cover')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    api.getGlobalSettings.mockResolvedValue({})
    api.getHeroImage.mockResolvedValue(new Blob(['cover']))
    api.getHeroSettings.mockResolvedValue({ present: true, position_x: 50, position_y: 50 })
    api.saveHeroSettings.mockResolvedValue({})
    api.deleteHeroImage.mockResolvedValue(undefined)
  })
  afterEach(() => {
    for (const wrapper of wrappers.splice(0)) wrapper.unmount()
    vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals()
    i18n.global.locale.value = previousLocale
  })

  it('moves both axes with pointer drag and arrow keys, then persists the final position', async () => {
    const wrapper = showLayout()
    await flushPromises()
    const preview = wrapper.find('.appearance-cover-preview')
    dispatchPointer(preview.element, 'pointerdown', { pointerId: 1, button: 0, clientX: 100, clientY: 100 })
    dispatchPointer(preview.element, 'pointermove', { pointerId: 1, clientX: 120, clientY: 110 })
    dispatchPointer(preview.element, 'pointerup', { pointerId: 1 })
    await flushPromises()
    expect(api.saveHeroSettings).toHaveBeenLastCalledWith(29, 42)
    await preview.trigger('keydown', { key: 'ArrowRight' })
    await preview.trigger('keydown', { key: 'ArrowDown' })
    await vi.advanceTimersByTimeAsync(250)
    expect(api.saveHeroSettings).toHaveBeenLastCalledWith(31, 44)
    expect(wrapper.text()).not.toMatch(/\p{Script=Han}/u)
  })

  it('waits for an in-flight position save before reset and drops queued positions', async () => {
    let finish!: () => void
    api.saveHeroSettings.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve }))
    const wrapper = showLayout()
    await flushPromises()
    await wrapper.find('input[type="range"]').setValue(10)
    await flushPromises()
    await wrapper.find('input[type="range"]').setValue(90)
    await flushPromises()
    const reset = wrapper.findAll('button').find(button => button.text() === 'Reset cover')!
    await reset.trigger('click')
    expect(api.deleteHeroImage).not.toHaveBeenCalled()
    finish()
    await flushPromises()
    expect(api.saveHeroSettings).toHaveBeenCalledTimes(1)
    expect(api.deleteHeroImage).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.appearance-cover-preview').exists()).toBe(false)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:cover')
  })

  it('does not create an ObjectURL when loading completes after unmount', async () => {
    let finish!: (blob: Blob) => void
    api.getHeroImage.mockImplementationOnce(() => new Promise<Blob>(resolve => { finish = resolve }))
    const wrapper = showLayout()
    await flushPromises()
    wrapper.unmount()
    wrappers.splice(wrappers.indexOf(wrapper), 1)
    finish(new Blob(['late']))
    await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('preserves a newly chosen accent when initial settings arrive late', async () => {
    let finish!: (settings: Record<string, unknown>) => void
    api.getGlobalSettings.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = showLayout()
    await wrapper.find('input[type="color"]').setValue('#ab12cd')
    finish({ appearance_accent_color: '#3d6fa8' })
    await flushPromises()
    expect((wrapper.find('input[type="color"]').element as HTMLInputElement).value).toBe('#ab12cd')
    await vi.advanceTimersByTimeAsync(350)
    expect(api.saveGlobalSettings).toHaveBeenLastCalledWith(expect.any(String), { appearance_accent_color: '#ab12cd' })
  })

  it('does not replace a new upload with an older cover hydration response', async () => {
    let finish!: (blob: Blob) => void
    api.getHeroImage.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    api.uploadHeroImage.mockResolvedValue(undefined)
    const wrapper = showLayout()
    await flushPromises()
    const file = new File(['new cover'], 'new.png', { type: 'image/png' })
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
    finish(new Blob(['old cover']))
    await flushPromises()
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(URL.createObjectURL).toHaveBeenCalledWith(file)
    expect(wrapper.find('.appearance-cover-preview').exists()).toBe(true)
  })

  it('does not start cover requests if settings reject after the layout unmounts', async () => {
    let fail!: (reason: Error) => void
    api.getGlobalSettings.mockImplementationOnce(() => new Promise((_resolve, reject) => { fail = reject }))
    const wrapper = showLayout()
    wrapper.unmount()
    wrappers.splice(wrappers.indexOf(wrapper), 1)
    fail(new Error('connection closed'))
    await flushPromises()
    expect(api.getHeroImage).not.toHaveBeenCalled()
    expect(api.getHeroSettings).not.toHaveBeenCalled()
  })
})
