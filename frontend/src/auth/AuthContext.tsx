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
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [initialising, setInitialising] = useState(true)

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  // A 401 from any request means the token is dead — drop the session once,
  // centrally, instead of every caller handling it.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

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
  }, [])

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
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside an AuthProvider')
  return ctx
}
