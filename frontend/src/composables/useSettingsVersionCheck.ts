/**
 * 设置页：应用版本加载与更新检查。
 */
import { computed, ref } from 'vue'
import {
  getAppVersion,
  checkAppVersion,
  type AppVersionInfo,
  type UpdateCheckInfo,
} from '../lib/api'
import { withToken } from '../lib/api/core'
import { useI18n } from './useI18n'
import { devLog } from '../lib/devLog'
import {
  fetchGithubLatestRelease,
  friendlyGithubError,
  isUpdateAvailable,
  loadCachedUpdateCheck,
  safeHttpUrl,
  saveCachedUpdateCheck,
} from '../lib/version-utils'

export type VersionBanner = {
  kind: 'update' | 'latest' | 'error' | 'info'
  text: string
  url?: string | null
}

export function useSettingsVersionCheck() {
  const { t, locale } = useI18n()

  const appVersion = ref<AppVersionInfo | null>(null)
  const versionLoading = ref(false)
  const checkLoading = ref(false)
  const bannerState = ref<{
    kind: VersionBanner['kind']; key: string; url?: string | null;
    named?: Record<string, unknown>
  } | null>(null)
  const versionBanner = computed<VersionBanner | null>(() => {
    const state = bannerState.value
    if (!state) return null
    const named = state.named ? { ...state.named } : undefined
    if (named?.error && locale.value === 'en' && /\p{Script=Han}/u.test(String(named.error))) {
      named.error = t('common.requestFailed')
    }
    return { kind: state.kind, text: t(state.key, named), url: state.url }
  })

  const setUpdateBanner = (
    kind: VersionBanner['kind'],
    key: string,
    url?: string | null,
    named?: Record<string, unknown>,
  ) => {
    bannerState.value = { kind, key, named, url: safeHttpUrl(url ?? null) }
  }

  const applyClientCache = () => {
    const cached = loadCachedUpdateCheck()
    if (!cached?.update_available || !cached.latest_version) return
    setUpdateBanner(
      'update',
      'settings.updateAvailable',
      cached.latest_url,
      { version: cached.latest_version },
    )
  }

  const loadVersion = async (token: string) => {
    if (versionLoading.value) return
    versionLoading.value = true
    try {
      appVersion.value = await getAppVersion(token)
      applyClientCache()
    } catch (e: unknown) {
      devLog.error('Failed to load app version', e)
    } finally {
      versionLoading.value = false
    }
  }

  const runBrowserFallbackCheck = async (currentVersion: string) => {
    const latest = await fetchGithubLatestRelease()
    const available = Boolean(latest.version && isUpdateAvailable(currentVersion, latest.version))
    const safeUrl = safeHttpUrl(latest.url)
    saveCachedUpdateCheck({
      latest_version: latest.version,
      latest_url: safeUrl,
      update_available: available,
      checked_at: new Date().toISOString(),
      error: null,
    })
    if (!latest.version) {
      setUpdateBanner('info', 'settings.noPublishedRelease', safeUrl)
    } else if (available) {
      setUpdateBanner(
        'update',
        'settings.updateAvailable',
        safeUrl,
        { version: latest.version },
      )
    } else {
      setUpdateBanner('latest', 'settings.alreadyLatest')
    }
  }

  const showFromRemote = (uc: UpdateCheckInfo) => {
    if (uc.source?.replace(/_stale$/, '') === 'github_no_releases' && !uc.latest_version && !uc.error) {
      saveCachedUpdateCheck({
        latest_version: null,
        latest_url: null,
        update_available: false,
        checked_at: uc.checked_at || new Date().toISOString(),
        error: null,
      })
      setUpdateBanner('info', 'settings.noPublishedRelease', uc.latest_url)
      return
    }
    if (uc.error && !uc.latest_version) {
      setUpdateBanner(
        'error',
        'settings.updateCheckFailed',
        null,
        { error: uc.error },
      )
      return
    }
    const safeUrl = safeHttpUrl(uc.latest_url)
    if (uc.update_available && uc.latest_version) {
      saveCachedUpdateCheck({
        latest_version: uc.latest_version,
        latest_url: safeUrl,
        update_available: true,
        checked_at: uc.checked_at || new Date().toISOString(),
        error: null,
      })
      setUpdateBanner(
        'update',
        'settings.updateAvailable',
        safeUrl,
        { version: uc.latest_version },
      )
      return
    }
    saveCachedUpdateCheck({
      latest_version: uc.latest_version,
      latest_url: safeUrl,
      update_available: false,
      checked_at: uc.checked_at || new Date().toISOString(),
      error: null,
    })
    setUpdateBanner('latest', 'settings.alreadyLatest')
  }

  const handleCheckUpdate = async (force = true) => {
    if (!appVersion.value || checkLoading.value) return
    return withToken(async (token) => {
      if (!appVersion.value) return
      checkLoading.value = true
      bannerState.value = null
      const current = appVersion.value.version

      try {
        if (appVersion.value.update_check_enabled) {
          try {
            const res = await checkAppVersion(token, force)
            appVersion.value = {
              version: res.version,
              git_sha: res.git_sha,
              git_branch: res.git_branch,
              build_time: res.build_time,
              app_name: res.app_name,
              python: res.python,
              update_check_enabled: res.update_check_enabled,
            }
            if (res.update_check.error && !res.update_check.latest_version) {
              try {
                await runBrowserFallbackCheck(res.version)
              } catch (browserErr) {
                const msg =
                  res.update_check.error ||
                  friendlyGithubError(browserErr)
                setUpdateBanner(
                  'error',
                  'settings.updateCheckFailed',
                  null,
                  { error: msg },
                )
              }
              return
            }
            showFromRemote(res.update_check)
            return
          } catch {
            try {
              await runBrowserFallbackCheck(current)
            } catch (browserErr) {
              setUpdateBanner(
                'error',
                'settings.updateCheckFailed',
                null,
                {
                  error: friendlyGithubError(browserErr),
                },
              )
            }
            return
          }
        }
        setUpdateBanner('info', 'settings.updateCheckDisabled')
        try {
          await runBrowserFallbackCheck(current)
        } catch (browserErr) {
          setUpdateBanner(
            'error',
            'settings.updateCheckFailed',
            null,
            {
              error: friendlyGithubError(browserErr),
            },
          )
        }
      } finally {
        checkLoading.value = false
      }
    })
  }

  return {
    appVersion,
    versionLoading,
    checkLoading,
    versionBanner,
    loadVersion,
    handleCheckUpdate,
  }
}
