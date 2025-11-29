'use client';

import { useRef, useState, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useRoomContext } from '@livekit/components-react';
import type { ReceivedChatMessage } from '@livekit/components-react';

import { useSession } from '@/components/app/session-provider';
import { SessionView } from '@/components/app/session-view';
import { WelcomeView } from '@/components/app/welcome-view';

const MotionWelcomeView = motion.create(WelcomeView);
const MotionSessionView = motion.create(SessionView);

const VIEW_MOTION_PROPS = {
  variants: {
    visible: { opacity: 1 },
    hidden: { opacity: 0 },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: { duration: 0.5, ease: 'linear' },
};

export function ViewController() {
  const room = useRoomContext();
  const isSessionActiveRef = useRef(false);
  const { appConfig, isSessionActive, startSession } = useSession();

  // Chat state
  const [messages, setMessages] = useState<ReceivedChatMessage[]>([]);

  // Helper to add messages - STABLE with useCallback
  const pushMessage = useCallback((text: string, origin: 'local' | 'remote') => {
    if (!text || text.trim() === '') {
      console.warn('⚠️ Empty message, ignoring');
      return;
    }

    const newMessage: ReceivedChatMessage = {
      id: crypto.randomUUID(),
      timestamp: Date.now(),
      from: { isLocal: origin === 'local' },
      message: text,
    };
    
    console.log(`💬 Adding message [${origin}]:`, text.substring(0, 60) + '...');
    
    setMessages((prev) => [...prev, newMessage]);
  }, []);

  // Clear messages when session ends
  useEffect(() => {
    if (!isSessionActive) {
      console.log('🧹 Session ended, clearing messages');
      setMessages([]);
    }
  }, [isSessionActive]);

  // Restart button handler
  const restartStory = useCallback(() => {
    console.log('🔄 Restarting story');
    setMessages([]);
    
    try {
      room.localParticipant?.publishData(
        JSON.stringify({ type: 'restart' }),
        { reliable: true }
      );
    } catch (e) {
      console.warn('Restart signal failed:', e);
    }
  }, [room]);

  // Keep local ref updated
  isSessionActiveRef.current = isSessionActive;

  // Disconnect after animation completes
  const handleAnimationComplete = () => {
    if (!isSessionActiveRef.current && room.state !== 'disconnected') {
      room.disconnect();
    }
  };

  return (
    <AnimatePresence mode="wait">
      {/* Welcome screen */}
      {!isSessionActive && (
        <MotionWelcomeView
          key="welcome"
          {...VIEW_MOTION_PROPS}
          startButtonText={appConfig.startButtonText}
          onStartCall={startSession}
        />
      )}

      {/* Session view */}
      {isSessionActive && (
        <MotionSessionView
          key="session-view"
          {...VIEW_MOTION_PROPS}
          appConfig={appConfig}
          onAnimationComplete={handleAnimationComplete}
          messages={messages}
          pushMessage={pushMessage}
          restartStory={restartStory}
        />
      )}
    </AnimatePresence>
  );
}