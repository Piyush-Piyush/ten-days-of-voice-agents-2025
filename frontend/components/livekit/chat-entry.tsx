import * as React from 'react';
import { cn } from '@/lib/utils';

export interface ChatEntryProps extends React.HTMLAttributes<HTMLLIElement> {
  /** The locale to use for the timestamp. */
  locale: string;
  /** The timestamp of the message. */
  timestamp: number;
  /** The message to display. */
  message: string;
  /** The origin of the message. */
  messageOrigin: 'local' | 'remote';
  /** The sender's name. */
  name?: string;
  /** Whether the message has been edited. */
  hasBeenEdited?: boolean;
}

export const ChatEntry = ({
  name,
  locale,
  timestamp,
  message,
  messageOrigin,
  hasBeenEdited = false,
  className,
  ...props
}: ChatEntryProps) => {
  const time = new Date(timestamp);
  const title = time.toLocaleTimeString(locale, { timeStyle: 'full' });

  return (
    <li
      title={title}
      data-lk-message-origin={messageOrigin}
      className={cn('group flex w-full flex-col gap-1 mb-6', className)}
      style={{ position: 'relative', zIndex: 10 }}
      {...props}
    >
      <header
        className={cn(
          'flex items-center gap-2 text-sm mb-1',
          messageOrigin === 'local' ? 'flex-row-reverse text-right' : 'text-left'
        )}
      >
        {name && (
          <strong 
            className="font-semibold"
            style={{ 
              color: messageOrigin === 'local' ? '#60a5fa' : '#4ade80',
              opacity: 1
            }}
          >
            {name}
          </strong>
        )}
        <span 
          className="font-mono text-xs opacity-50 group-hover:opacity-100 transition-opacity"
          style={{ color: '#9ca3af' }}
        >
          {hasBeenEdited && '*'}
          {time.toLocaleTimeString(locale, { timeStyle: 'short' })}
        </span>
      </header>
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-4 py-3 shadow-lg',
          messageOrigin === 'local' ? 'ml-auto' : 'mr-auto'
        )}
        style={{
          backgroundColor: messageOrigin === 'local' ? '#2563eb' : '#374151',
          color: '#ffffff',
          opacity: 1,
          display: 'block',
          position: 'relative',
          zIndex: 10,
        }}
      >
        <span style={{ color: '#ffffff', opacity: 1 }}>
          {message}
        </span>
      </div>
    </li>
  );
};