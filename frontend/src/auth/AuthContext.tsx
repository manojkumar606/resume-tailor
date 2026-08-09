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
import type { User } from '../lib/types'

interface AuthState {
  user: User | null
  /** True until the stored token has been checked, so routes don't flash. */
  initialising: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string, fullName?: string) => Promise<void>
  /** Redeem an emailed token and adopt the returned session. */
  verify: (token: string) => Promise<void>
  /** Re-read the user, for after verifying in another tab. */
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

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.auth.login(email, password)
    tokenStore.set(res.access_token)
    setUser(res.user)
  }, [])

  const signup = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const res = await api.auth.signup(email, password, fullName)
      tokenStore.set(res.access_token)
      setUser(res.user)
    },
    [],
  )

  const verify = useCallback(async (token: string) => {
    const res = await api.auth.verify(token)
    // The response carries a fresh token, so a link opened while signed out
    // still lands the user straight in the app.
    tokenStore.set(res.access_token)
    setUser(res.user)
  }, [])

  const refresh = useCallback(async () => {
    setUser(await api.auth.me())
  }, [])

  const value = useMemo(
    () => ({ user, initialising, login, signup, verify, refresh, logout }),
    [user, initialising, login, signup, verify, refresh, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside an AuthProvider')
  return ctx
}
