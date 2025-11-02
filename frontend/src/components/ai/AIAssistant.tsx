import React, { useState, useEffect, useRef } from 'react';
import { Plus, X, Trash2, MessageSquare, Settings, FileText } from 'lucide-react';
import { aiAPI } from '../../services/api';
import { usePapers } from '../../contexts/PapersContext';

interface ChatSession {
  id: string;
  name: string;
  messages: Message[];
  isActive: boolean;
  createdAt: Date;
  paperId?: string;  // Optional: link to specific research paper
  paperTitle?: string; // Optional: paper title for context
  type: 'general' | 'paper'; // Type of conversation
}

interface AIAssistantProps {
  isOpen: boolean;
  onClose: () => void;
}

interface Message {
  id: string;
  type: 'user' | 'ai';
  content: string;
  timestamp: Date;
  sources?: any[];
}

const AIAssistant: React.FC<AIAssistantProps> = ({ isOpen, onClose }) => {
  const { papers } = usePapers();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showPaperSelector, setShowPaperSelector] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [sessions]);



  const createNewSession = () => {
    const newSession: ChatSession = {
      id: `session-${Date.now()}`,
      name: `New Chat ${sessions.length + 1}`,
      messages: [],
      isActive: true,
      createdAt: new Date(),
      type: 'general'
    };

    setSessions(prev => [...prev, newSession]);
    setCurrentSessionId(newSession.id);
    setInputValue('');
  };

  const createPaperSession = (paper: any) => {
    const newSession: ChatSession = {
      id: `paper-${paper.id}-${Date.now()}`,
      name: `📄 ${paper.title}`,
      messages: [],
      isActive: true,
      createdAt: new Date(),
      type: 'paper',
      paperId: paper.id,
      paperTitle: paper.title
    };

    setSessions(prev => [...prev, newSession]);
    setCurrentSessionId(newSession.id);
    setInputValue('');
    setShowPaperSelector(false);
  };

  const deleteSession = (sessionId: string) => {
    setSessions(prev => prev.filter(session => session.id !== sessionId));
    
    if (currentSessionId === sessionId) {
      const remainingSessions = sessions.filter(session => session.id !== sessionId);
      if (remainingSessions.length > 0) {
        setCurrentSessionId(remainingSessions[0].id);
      } else {
        setCurrentSessionId(null);
      }
    }
  };

  const clearAllSessions = () => {
    setSessions([]);
    setCurrentSessionId(null);
    setInputValue('');
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading || !currentSessionId) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      type: 'user',
      content: inputValue.trim(),
      timestamp: new Date()
    };

    // Add user message to current session
    setSessions(prev => prev.map(session => 
      session.id === currentSessionId 
        ? { ...session, messages: [...session.messages, userMessage] }
        : session
    ));

    setInputValue('');
    setIsLoading(true);

    try {
      // Add paper context for paper-specific sessions
      let query = inputValue.trim();
      if (currentSession?.type === 'paper' && currentSession.paperTitle) {
        query = `[Paper: ${currentSession.paperTitle}] ${inputValue.trim()}`;
      }
      
      const response = await aiAPI.chatWithReferences(
        query,
        currentSession?.type === 'paper' ? currentSession.paperId : undefined
      );
      
      if (response.data.response) {
        const aiMessage: Message = {
          id: `ai-${Date.now()}`,
          type: 'ai',
          content: response.data.response,
          timestamp: new Date(),
          sources: response.data.sources_data || response.data.sources || []
        };

        // Add AI message to current session
        setSessions(prev => prev.map(session => 
          session.id === currentSessionId 
            ? { ...session, messages: [...session.messages, aiMessage] }
            : session
        ));
      }
    } catch (error: any) {
      console.error('Error sending message:', error);
      // Gracefully handle "no documents" 400 from backend
      const isNoDocs = error?.response?.status === 400 && (
        typeof error?.response?.data?.detail === 'string'
          ? error.response.data.detail.toLowerCase().includes('no documents')
          : true
      )
      const fallbackText = isNoDocs
        ? 'I can’t find any processed documents to answer from. Upload a document or process an existing one, then try again.'
        : 'Sorry, I encountered an error. Please try again.'

      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        type: 'ai',
        content: fallbackText,
        timestamp: new Date()
      };

      setSessions(prev => prev.map(session => 
        session.id === currentSessionId 
          ? { ...session, messages: [...session.messages, errorMessage] }
          : session
      ));
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const currentSession = sessions.find(session => session.id === currentSessionId);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-6xl h-[90vh] flex flex-col">
      {/* Header */}
              <div className="flex items-center justify-between p-4 border-b bg-gray-50 rounded-t-lg">
          <div className="flex items-center space-x-3">
            <MessageSquare className="h-6 w-6 text-blue-600" />
            <h2 className="text-xl font-semibold text-gray-900">AI Assistant</h2>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              title="Settings"
            >
              <Settings className="h-4 w-4" />
            </button>
            <button
              onClick={() => setShowPaperSelector(true)}
              className="flex items-center space-x-2 px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
            >
              <FileText className="h-4 w-4" />
              <span>Paper Chat</span>
            </button>
            <button
              onClick={createNewSession}
              className="flex items-center space-x-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              <span>New Chat</span>
            </button>
            <button
              onClick={onClose}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="p-4 border-b bg-gray-50">
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-gray-900">Chat Management</h3>
            <button
              onClick={clearAllSessions}
              className="flex items-center space-x-2 px-3 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              <Trash2 className="h-4 w-4" />
              <span>Clear All Chats</span>
            </button>
          </div>
        </div>
      )}

      {/* Paper Selector Modal */}
      {showPaperSelector && (
        <div className="p-4 border-b bg-gray-50">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium text-gray-900">Select Research Paper for Chat</h3>
            <button
              onClick={() => setShowPaperSelector(false)}
              className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-40 overflow-y-auto">
            {papers.map((paper) => (
              <button
                key={paper.id}
                onClick={() => createPaperSession(paper)}
                className="text-left p-3 border border-gray-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-colors"
              >
                <div className="font-medium text-sm text-gray-900 truncate">{paper.title}</div>
                <div className="text-xs text-gray-500 mt-1">
                  {paper.paper_type} • {new Date(paper.created_at).toLocaleDateString()}
                </div>
              </button>
            ))}
            {papers.length === 0 && (
              <div className="text-sm text-gray-500 col-span-2 text-center py-4">
                No research papers found. Create a paper first to start paper-specific conversations.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Session Tabs */}
      {sessions.length > 0 && (
        <div className="flex border-b overflow-x-auto">
          {sessions.map((session) => (
            <div
              key={session.id}
              onClick={() => setCurrentSessionId(session.id)}
              className={`flex items-center space-x-2 px-4 py-2 border-r border-gray-200 whitespace-nowrap transition-colors cursor-pointer ${
                currentSessionId === session.id
                  ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {session.type === 'paper' && (
                <FileText className="h-3 w-3 text-green-600 flex-shrink-0" />
              )}
              <span className="truncate max-w-32">{session.name}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession(session.id);
                }}
                className="ml-2 p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                title="Delete session"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Chat Area */}
      <div className="flex-1 flex flex-col">
        {!currentSession ? (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <MessageSquare className="h-16 w-16 mx-auto mb-4 text-gray-300" />
              <p className="text-lg font-medium">No active chat session</p>
              <p className="text-sm">Create a new chat to get started</p>
              <button
                onClick={createNewSession}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Start New Chat
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {currentSession.messages.length === 0 ? (
                <div className="text-center text-gray-500 py-8">
                  <MessageSquare className="h-12 w-12 mx-auto mb-3 text-gray-300" />
                  <p className="text-lg font-medium">Start a new conversation</p>
                  <p className="text-sm">Ask me anything about your documents</p>
                </div>
              ) : (
                currentSession.messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg p-3 ${
                        message.type === 'user'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-900'
                      }`}
                    >
                      <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      {message.sources && message.sources.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-gray-200">
                          <p className="text-xs text-gray-500 mb-1">Sources:</p>
                          {message.sources.map((source, index) => (
                            <div key={index} className="text-xs text-gray-600">
                              • {source.title || source.filename}
                            </div>
                          ))}
                        </div>
                      )}
                      <p className="text-xs opacity-70 mt-2">
                        {message.timestamp.toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                ))
              )}
              
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-lg p-3">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                    </div>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t bg-gray-50">
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Type your message..."
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={isLoading}
                />
                <button
                  onClick={handleSendMessage}
                  disabled={!inputValue.trim() || isLoading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Send
                </button>
              </div>
            </div>
          </>
        )}
      </div>
      </div>
    </div>
  );
};

export default AIAssistant;
