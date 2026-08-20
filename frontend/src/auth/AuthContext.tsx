import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { api, setUnauthorizedHandler, tokenStore } from '../lib/api'
import type { CodeSent, User } from '../lib/types'
import type { SignOutReason } from './idle'
import { useIdleTimeout } from './useIdleTimeout'

interface AuthState {
  user: User | null
  /** True until the stored token has been checked, so routes don't flash. */
  initialising: boolean

  /* Step one. Neither of these produces a session — both send a code. */
  requestSignup: (
    email: string,
    password: string,
    fullName?: string,
  ) => Promise<CodeSent>
  requestLogin: (email: string, password: string) => Promise<CodeSent>

  /** Step two, and the only thing that establishes a session. */
  submitCode: (email: string, code: string) => Promise<void>
  resendCode: (email: string) => Promise<string>

  /** Re-read the current user. */
  refresh: () => Promise<void>
  logout: () => Promise<void>

  /**
   * Why the last session ended, so the sign-in page can say so. Cleared once
   * shown; deliberately not persisted, since a fresh page load is not the
   * moment to explain something that happened before it.
   */
  signOutReason: SignOutReason
  clearSignOutReason: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [initialising, setInitialising] = useState(true)
  const [signOutReason, setSignOutReason] = useState<SignOutReason>(null)

  /**
   * Clear the local session. The server call comes first so the session row is
   * revoked, but its failure is swallowed: the token is dropped locally either
   * way, and a session left to expire on idle is far better than a sign-out
   * button that refuses to work because the network is down.
   */
  const endSession = useCallback(
    async (reason: Exclude<SignOutReason, null>) => {
      if (tokenStore.get()) {
        try {
          await api.auth.logout()
        } catch {
          // Deliberately silent: the user asked to leave, and telling them the
          // sign-out "failed" while signing them out anyway is just alarming.
        }
      }
      tokenStore.clear()
      setUser(null)
      setSignOutReason(reason)
    },
    [],
  )

  const logout = useCallback(() => endSession('manual'), [endSession])

  // A 401 from any request means the token is dead — drop the session once,
  // centrally, instead of every caller handling it.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      // The server ended it — idle timeout it enforced itself, a sign-out from
      // another device, or the absolute expiry. Worth saying, since from here
      // it looks like being thrown out at random.
      setSignOutReason('expired')
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  // Only armed while signed in, so the timer is not running on the landing or
  // sign-in pages.
  useIdleTimeout(() => {
    void endSession('idle')
  }, user !== null)

  // A token in localStorage is not proof of a valid session: it may have
  // expired, or the user may have been deleted. Verify it before trusting it.
  useEffect(() => {
    if (!tokenStore.get()) {
      setInitialising(false)
      return
    }

    let cancelled = false
    api.auth
      .me()
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        tokenStore.clear()
      })
      .finally(() => {
        if (!cancelled) setInitialising(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const requestSignup = useCallback(
    (email: string, password: string, fullName?: string) =>
      api.auth.signup(email, password, fullName),
    [],
  )

  const requestLogin = useCallback(
    (email: string, password: string) => api.auth.login(email, password),
    [],
  )

  const submitCode = useCallback(async (email: string, code: string) => {
    const res = await api.auth.verifyCode(email, code)
    tokenStore.set(res.access_token)
    setUser(res.user)
    setSignOutReason(null)
  }, [])

  const clearSignOutReason = useCallback(() => setSignOutReason(null), [])

  const resendCode = useCallback(async (email: string) => {
    const res = await api.auth.resendCode(email)
    return res.detail
  }, [])

  const refresh = useCallback(async () => {
    setUser(await api.auth.me())
  }, [])

  const value = useMemo(
    () => ({
      user,
      initialising,
      requestSignup,
      requestLogin,
      submitCode,
      resendCode,
      refresh,
      logout,
      signOutReason,
      clearSignOutReason,
    }),
    [
      user,
      initialising,
      requestSignup,
      requestLogin,
      submitCode,
      resendCode,
      refresh,
      logout,
      signOutReason,
      clearSignOutReason,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside an AuthProvider')
  return ctx
}
