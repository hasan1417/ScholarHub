import React from 'react'

interface ConfirmationModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message?: string
  description?: string
  confirmText?: string
  confirmLabel?: string
  cancelText?: string
  cancelLabel?: string
  confirmButtonColor?: 'red' | 'blue' | 'green' | 'yellow'
  confirmTone?: 'danger' | 'primary' | 'success' | 'warning' | 'default'
  icon?: 'warning' | 'info' | 'error' | 'success'
  isSubmitting?: boolean
}

const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  description,
  confirmText,
  confirmLabel,
  cancelText,
  cancelLabel,
  confirmButtonColor = 'red',
  confirmTone,
  icon = 'warning',
  isSubmitting = false,
}) => {
  if (!isOpen) return null

  const bodyCopy = description ?? message ?? 'Are you sure?'

  const resolvedConfirmText = confirmLabel ?? confirmText ?? 'Confirm'
  const resolvedCancelText = cancelLabel ?? cancelText ?? 'Cancel'

  const getIcon = () => {
    switch (icon) {
      case 'warning':
        return (
          <svg className="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
        )
      case 'error':
        return (
          <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        )
      case 'info':
        return (
          <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        )
      case 'success':
        return (
          <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        )
      default:
        return null
    }
  }

  const getConfirmButtonColor = () => {
    const toneMap: Record<string, typeof confirmButtonColor> = {
      danger: 'red',
      primary: 'blue',
      success: 'green',
      warning: 'yellow',
      default: 'blue',
    }
    const tone = confirmTone ? toneMap[confirmTone] ?? confirmButtonColor : confirmButtonColor

    switch (tone) {
      case 'red':
        return 'bg-red-600 hover:bg-red-700 focus:ring-red-500'
      case 'blue':
        return 'bg-blue-600 hover:bg-blue-700 focus:ring-blue-500'
      case 'green':
        return 'bg-green-600 hover:bg-green-700 focus:ring-green-500'
      case 'yellow':
        return 'bg-yellow-600 hover:bg-yellow-700 focus:ring-yellow-500'
      default:
        return 'bg-red-600 hover:bg-red-700 focus:ring-red-500'
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            {getIcon()}
            <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
          </div>
        </div>

        <div className="px-6 py-4">
          <p className="text-gray-600 mb-6">{bodyCopy}</p>
          
          <div className="flex justify-end space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500"
            >
              {resolvedCancelText}
            </button>
            <button
              onClick={onConfirm}
              disabled={isSubmitting}
              className={`px-4 py-2 text-white rounded-md transition-colors focus:outline-none focus:ring-2 ${getConfirmButtonColor()} ${
                isSubmitting ? 'opacity-70 cursor-not-allowed' : ''
              }`}
            >
              {resolvedConfirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ConfirmationModal
