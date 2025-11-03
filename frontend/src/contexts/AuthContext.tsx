import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authAPI, setupTokenRefreshTimer } from '../services/api'

interface User {
  id: string
  email: string
  first_name?: string
  last_name?: string
  is_active: boolean
  is_verified: boolean
  created_at: string
  updated_at: string
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (userData: {
    email: string
    password: string
    first_name?: string
    last_name?: string
  }) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  updateUser: (userData: Partial<User>) => void
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

  const isAuthenticated = !!user

  useEffect(() => {
    refreshUser()
  }, [])

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
  }) => {
    try {
      await authAPI.register(userData)
      // After successful registration, log the user in
      await login(userData.email, userData.password)
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
    login,
    register,
    logout,
    refreshUser,
    updateUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
