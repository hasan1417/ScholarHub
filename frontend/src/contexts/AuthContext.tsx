import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authAPI, setupTokenRefreshTimer, subscriptionAPI } from '../services/api'
import type { SubscriptionState, UserSubscription, UsageTracking } from '../types'

interface User {
  id: string
  email: string
  first_name?: string
  last_name?: string
  avatar_url?: string
  is_active: boolean
  is_verified: boolean
  auth_provider?: string  // "local" or "google"
  created_at: string
  updated_at: string
}

interface RegisterResponse {
  id: string
  email: string
  message: string
  dev_verification_url?: string
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  subscription: SubscriptionState
  login: (email: string, password: string) => Promise<void>
  register: (userData: {
    email: string
    password: string
    first_name?: string
    last_name?: string
  }) => Promise<RegisterResponse>
  logout: () => void
  refreshUser: () => Promise<void>
  updateUser: (userData: Partial<User>) => void
  refreshSubscription: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [subscription, setSubscription] = useState<SubscriptionState>({
    subscription: null,
    usage: null,
    limits: {},
    loading: false,
  })

  const isAuthenticated = !!user

  const refreshSubscription = async () => {
    if (!user) return
    setSubscription(prev => ({ ...prev, loading: true }))
    try {
      const response = await subscriptionAPI.getMySubscription()
      setSubscription({
        subscription: response.data.subscription,
        usage: response.data.usage,
        limits: response.data.limits,
        loading: false,
      })
    } catch (error) {
      console.error('Failed to fetch subscription:', error)
      setSubscription(prev => ({ ...prev, loading: false }))
    }
  }

  useEffect(() => {
    refreshUser()
  }, [])

  useEffect(() => {
    if (user) {
      refreshSubscription()
    }
  }, [user?.id])

  const login = async (email: string, password: string) => {
    try {
      const response = await authAPI.login({ email, password })
      const data = response.data as { access_token: string }
      const { access_token } = data
      
      localStorage.setItem('access_token', access_token)
      setupTokenRefreshTimer()
      await refreshUser()
    } catch (error) {
      console.error('Login failed:', error)
      throw error
    }
  }

  const register = async (userData: {
    email: string
    password: string
    first_name?: string
    last_name?: string
  }): Promise<RegisterResponse> => {
    try {
      const response = await authAPI.register(userData)
      // Return the response data so the Register page can show verification info
      return response.data as RegisterResponse
    } catch (error) {
      console.error('Registration failed:', error)
      throw error
    }
  }

  const logout = () => {
    authAPI.logout().catch(() => {
      // ignore logout errors (e.g., network issues)
    })
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    setUser(null)
  }

  const refreshUser = async () => {
    try {
      const response = await authAPI.getCurrentUser()
      const userData = response.data as User
      setUser(userData)
      localStorage.setItem('user', JSON.stringify(userData))
      setupTokenRefreshTimer()
    } catch (error: any) {
      console.error('Failed to refresh user:', error)
      
      // If token is expired or invalid (401), logout the user
      if (error.response?.status === 401) {
        logout()
        return
      }
      
      // For other errors, keep user logged in (network issues, etc.)
    } finally {
      setIsLoading(false)
    }
  }

  const updateUser = (userData: Partial<User>) => {
    if (user) {
      const updatedUser = { ...user, ...userData }
      setUser(updatedUser)
      localStorage.setItem('user', JSON.stringify(updatedUser))
    }
  }

  const value: AuthContextType = {
    user,
    isAuthenticated,
    isLoading,
    subscription,
    login,
    register,
    logout,
    refreshUser,
    updateUser,
    refreshSubscription,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
