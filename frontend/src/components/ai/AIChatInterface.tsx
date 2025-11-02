import React, { useState, useEffect, useRef } from 'react'
import { aiAPI } from '../../services/api'
// AIChatResponse type is used in the component logic

interface AIChatInterfaceProps {
  isOpen: boolean
  onClose: () => void
}

interface ChatMessage {
  id: string
  type: 'user' | 'ai'
  content: string
  timestamp: Date
  sources?: Array<{
    chunk_id?: string
    document_id: string
    text?: string
    text_preview?: string
    similarity?: number
    metadata?: any
  }>
}

const AIChatInterface: React.FC<AIChatInterfaceProps> = ({ isOpen, onClose }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [aiStatus, setAiStatus] = useState<{
    status: string
    progress: number
    message: string
  } | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isOpen) {
      loadAIStatus()
      loadChatHistory()
    }
  }, [isOpen])

  // Refresh chat history periodically to catch new messages
  useEffect(() => {
    if (isOpen) {
      const interval = setInterval(() => {
        loadChatHistory()
      }, 5000) // Refresh every 5 seconds
      
      return () => clearInterval(interval)
    }
  }, [isOpen])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const ensureMessageOrder = (messages: ChatMessage[]) => {
    // Sort messages by timestamp to ensure chronological order (oldest first)
    return messages.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
  }

  const addMessageWithOrder = (newMessage: ChatMessage) => {
    setMessages(prev => {
      const newMessages = ensureMessageOrder([...prev, newMessage])
      return newMessages
    })
  }

  const loadAIStatus = async () => {
    try {
      const response = await aiAPI.getAIStatus()
      setAiStatus(response.data)
    } catch (error) {
      console.error('Error loading AI status:', error)
    }
  }

  const loadChatHistory = async () => {
    try {
      const response = await aiAPI.getChatHistory(10)
      
      if (response.data.chat_sessions && response.data.chat_sessions.length > 0) {
        // Create chat history with proper ordering
        const chatHistory = response.data.chat_sessions.map((session: any) => [
          {
            id: `user-${session.id}`,
            type: 'user' as const,
            content: session.query,
            timestamp: new Date(session.created_at),
          },
          {
            id: `ai-${session.id}`,
            type: 'ai' as const,
            content: session.response,
            timestamp: new Date(session.created_at),
            sources: session.sources || [],
          },
        ]).flat()
        
        // Ensure proper ordering and set messages
        const orderedHistory = ensureMessageOrder(chatHistory)
        setMessages(orderedHistory)
      } else {
        // Start with a welcome message if no history
        setMessages([{
          id: 'welcome',
          type: 'ai',
          content: 'Hello! I\'m your AI research assistant. I can help you understand and analyze your research documents. Ask me anything about your papers!',
          timestamp: new Date(),
        }])
      }
    } catch (error) {
      console.error('Error loading chat history:', error)
      // Start with a welcome message if no history
      setMessages([{
        id: 'welcome',
        type: 'ai',
        content: 'Hello! I\'m your AI research assistant. I can help you understand and analyze your research documents. Ask me anything about your papers!',
        timestamp: new Date(),
      }])
    }
  }

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      type: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    }

    // Add user message immediately and ensure proper ordering
    addMessageWithOrder(userMessage)
    setInputValue('')
    setIsLoading(true)

    try {
      const response = await aiAPI.chatWithReferences(inputValue.trim())
      
      const aiMessage: ChatMessage = {
        id: `ai-${Date.now()}`,
        type: 'ai',
        content: response.data.response,
        timestamp: new Date(),
        sources: response.data.sources_data || response.data.sources || [],
      }
      
      // Add AI message to the chat and ensure proper ordering
      addMessageWithOrder(aiMessage)
      
    } catch (error: any) {
      console.error('Error sending message:', error)
      
      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        type: 'ai',
        content: error.response?.data?.detail || 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date(),
      }

      // Add error message and ensure proper ordering
      addMessageWithOrder(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">AI Research Assistant</h2>
              <div className="flex items-center space-x-2 text-sm text-gray-500">
                <div className={`w-2 h-2 rounded-full ${aiStatus?.status === 'ready' ? 'bg-green-500' : 'bg-yellow-500'}`}></div>
                <span>{aiStatus?.status || 'Checking status...'}</span>
                <span className="text-gray-400">•</span>
                <span>{messages.filter(m => m.type === 'user').length} questions asked</span>
              </div>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={loadChatHistory}
              className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
              title="Refresh chat history"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message, index) => (
            <div
              key={message.id}
              className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  message.type === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-900'
                }`}
                style={{ minHeight: 'fit-content' }}
              >
                {/* Message content */}
                <div className="whitespace-pre-wrap break-words overflow-hidden">{message.content}</div>
                
                {/* Sources */}
                {message.sources && message.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-200">
                    <div className="text-xs font-medium text-gray-600 mb-2">Sources:</div>
                    <div className="space-y-1">
                      {message.sources.map((source, sourceIndex) => (
                        <div key={sourceIndex} className="text-xs text-gray-500">
                          <span className="font-medium">
                            {source.document_id ? `Document ${source.document_id.slice(0, 8)}...` : 'Unknown Document'}
                          </span>
                          {source.chunk_id && <span> (Chunk {source.chunk_id.slice(0, 8)}...)</span>}
                          <div className="text-gray-400 mt-1">
                            {source.text_preview || source.text || 'No preview available'}
                          </div>
                          {source.similarity && (
                            <div className="text-gray-300 text-xs">
                              Relevance: {(source.similarity * 100).toFixed(1)}%
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Message metadata */}
                <div className="flex items-center justify-between mt-2">
                  <div className="text-xs opacity-70">
                    {message.timestamp.toLocaleTimeString()}
                  </div>
                  <div className="text-xs opacity-50">
                    #{index + 1}
                  </div>
                </div>
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-lg px-4 py-2">
                <div className="flex items-center space-x-2">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                    <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  </div>
                  <span className="text-sm text-gray-500">AI is analyzing your documents...</span>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-gray-200 p-4">
          <div className="flex space-x-3">
            <div className="flex-1">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask me anything about your research documents..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                rows={2}
                disabled={isLoading || aiStatus?.status !== 'ready'}
              />
            </div>
            <button
              onClick={handleSendMessage}
              disabled={!inputValue.trim() || isLoading || aiStatus?.status !== 'ready'}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
          
          {aiStatus?.status !== 'ready' && (
            <div className="mt-2 text-sm text-yellow-600">
              ⚠️ AI service is {aiStatus?.status || 'initializing'}. Please wait a moment before asking questions.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default AIChatInterface
