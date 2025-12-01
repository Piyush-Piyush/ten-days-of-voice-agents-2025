'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import type { AppConfig } from '@/app-config';
import { ChatTranscript } from '@/components/app/chat-transcript';
import { PreConnectMessage } from '@/components/app/preconnect-message';
import { TileLayout } from '@/components/app/tile-layout';
import {
  AgentControlBar,
  type ControlBarControls,
} from '@/components/livekit/agent-control-bar/agent-control-bar';
import { useChatMessages } from '@/hooks/useChatMessages';
import { useConnectionTimeout } from '@/hooks/useConnectionTimout';
import { useDebugMode } from '@/hooks/useDebug';
import { cn } from '@/lib/utils';
import { ScrollArea } from '../livekit/scroll-area/scroll-area';

const MotionBottom = motion.create('div');

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';
const BOTTOM_VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
      translateY: '0%',
    },
    hidden: {
      opacity: 0,
      translateY: '100%',
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.3,
    delay: 0.5,
    ease: 'easeOut',
  },
};

interface FadeProps {
  top?: boolean;
  bottom?: boolean;
  className?: string;
}

export function Fade({ top = false, bottom = false, className }: FadeProps) {
  return (
    <div
      className={cn(
        'from-background pointer-events-none h-4 bg-linear-to-b to-transparent',
        top && 'bg-linear-to-b',
        bottom && 'bg-linear-to-t',
        className
      )}
    />
  );
}

// Helper to detect game state from messages
function detectGamePhase(messages: any[]): {
  currentRound: number;
  phase: 'intro' | 'scenario' | 'performing' | 'feedback' | 'done';
  totalRounds: number;
} {
  let currentRound = 0;
  let phase: 'intro' | 'scenario' | 'performing' | 'feedback' | 'done' = 'intro';
  const totalRounds = 3;

  const transcriptText = messages
    .map(m => m.message?.toLowerCase() || '')
    .join(' ');

  // Count how many times "Round" appears in host messages
  const roundMatches = transcriptText.match(/round \d/gi);
  if (roundMatches) {
    currentRound = roundMatches.length;
  }

  // Detect phase
  if (transcriptText.includes('welcome') || transcriptText.includes('improv battle')) {
    phase = 'intro';
  }
  if (currentRound > 0 && currentRound <= totalRounds) {
    const lastMessage = messages[messages.length - 1]?.message?.toLowerCase() || '';
    if (lastMessage.includes('round')) {
      phase = 'scenario';
    } else if (messages[messages.length - 1]?.from?.isLocal) {
      phase = 'performing';
    } else {
      phase = 'feedback';
    }
  }
  if (transcriptText.includes('that wraps') || transcriptText.includes('closing') || currentRound > totalRounds) {
    phase = 'done';
  }

  return { currentRound: Math.min(currentRound, totalRounds), phase, totalRounds };
}

interface SessionViewProps {
  appConfig: AppConfig;
}

export const SessionView = ({
  appConfig,
  ...props
}: React.ComponentProps<'section'> & SessionViewProps) => {
  useConnectionTimeout(200_000);
  useDebugMode({ enabled: IN_DEVELOPMENT });

  const messages = useChatMessages();
  const [chatOpen, setChatOpen] = useState(true); // Start with chat open for improv
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const controls: ControlBarControls = {
    leave: true,
    microphone: true,
    chat: false, // Disable text chat for voice-only improv
    camera: false,
    screenShare: false,
  };

  const gameState = detectGamePhase(messages);

  useEffect(() => {
    const lastMessage = messages.at(-1);
    const lastMessageIsLocal = lastMessage?.from?.isLocal === true;

    if (scrollAreaRef.current && lastMessageIsLocal) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
    }
  }, [messages]);

  // Game status indicator
  const getStatusText = () => {
    if (gameState.phase === 'intro') return '🎭 Welcome to Improv Battle!';
    if (gameState.phase === 'scenario') return `🎬 Round ${gameState.currentRound} of ${gameState.totalRounds}`;
    if (gameState.phase === 'performing') return `🎤 You're on! Round ${gameState.currentRound}`;
    if (gameState.phase === 'feedback') return `💭 Host is reacting...`;
    if (gameState.phase === 'done') return '🎉 Show Complete!';
    return 'Improv Battle';
  };

  const getStatusColor = () => {
    if (gameState.phase === 'performing') return 'text-red-500';
    if (gameState.phase === 'scenario') return 'text-blue-500';
    if (gameState.phase === 'feedback') return 'text-yellow-500';
    if (gameState.phase === 'done') return 'text-green-500';
    return 'text-primary';
  };

  return (
    <section className="bg-background relative z-10 h-full w-full overflow-hidden" {...props}>
      {/* Game Status Header */}
      <div className="fixed top-0 left-0 right-0 z-50 bg-background/95 backdrop-blur-sm border-b border-input">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={cn('font-bold text-lg', getStatusColor())}>
              {getStatusText()}
            </span>
          </div>
          <div className="flex gap-1">
            {Array.from({ length: gameState.totalRounds }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  'w-2 h-2 rounded-full',
                  i < gameState.currentRound ? 'bg-primary' : 'bg-muted'
                )}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Chat Transcript */}
      <div
        className={cn(
          'fixed inset-0 grid grid-cols-1 grid-rows-1 pt-16',
          !chatOpen && 'pointer-events-none'
        )}
      >
        <Fade top className="absolute inset-x-4 top-16 h-20" />
        <ScrollArea ref={scrollAreaRef} className="px-4 pt-24 pb-[150px] md:px-6 md:pb-[180px]">
          <ChatTranscript
            hidden={!chatOpen}
            messages={messages}
            className="mx-auto max-w-2xl space-y-3 transition-opacity duration-300 ease-out"
          />
          
          {/* Performance tips */}
          {gameState.phase === 'performing' && (
            <div className="mx-auto max-w-2xl mt-4 p-4 bg-primary/10 rounded-lg border border-primary/20">
              <p className="text-sm text-muted-foreground text-center">
                💡 Say <span className="font-semibold text-foreground">"end scene"</span> when you're done
              </p>
            </div>
          )}
        </ScrollArea>
      </div>

      {/* Tile Layout */}
      <TileLayout chatOpen={chatOpen} />

      {/* Bottom Controls */}
      <MotionBottom
        {...BOTTOM_VIEW_MOTION_PROPS}
        className="fixed inset-x-3 bottom-0 z-50 md:inset-x-12"
      >
        {appConfig.isPreConnectBufferEnabled && (
          <PreConnectMessage messages={messages} className="pb-4" />
        )}
        <div className="bg-background relative mx-auto max-w-2xl pb-3 md:pb-12">
          <Fade bottom className="absolute inset-x-0 top-0 h-4 -translate-y-full" />
          
          {/* Improv tips based on phase */}
          <div className="mb-3 px-2">
            {gameState.phase === 'scenario' && (
              <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3 text-center">
                <p className="text-sm text-blue-600 dark:text-blue-400 font-medium">
                  🎬 Listen to the scenario, then start your improv!
                </p>
              </div>
            )}
            {gameState.phase === 'performing' && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-center animate-pulse">
                <p className="text-sm text-red-600 dark:text-red-400 font-medium">
                  🎤 LIVE - You're performing now!
                </p>
              </div>
            )}
          </div>

          <AgentControlBar controls={controls} onChatOpenChange={setChatOpen} />
        </div>
      </MotionBottom>
    </section>
  );
};