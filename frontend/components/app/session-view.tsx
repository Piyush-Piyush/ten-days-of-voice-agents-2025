'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { ReceivedChatMessage, RoomAudioRenderer, useRoomContext } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { ChatTranscript } from '@/components/app/chat-transcript';
import { PreConnectMessage } from '@/components/app/preconnect-message';
import { TileLayout } from '@/components/app/tile-layout';
import {
  AgentControlBar,
  type ControlBarControls,
} from '@/components/livekit/agent-control-bar/agent-control-bar';
import { cn } from '@/lib/utils';
import { ScrollArea } from '../livekit/scroll-area/scroll-area';

const MotionBottom = motion.create('div');

const BOTTOM_VIEW_MOTION_PROPS = {
  variants: {
    visible: { opacity: 1, translateY: '0%' },
    hidden: { opacity: 0, translateY: '100%' },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: { duration: 0.3, delay: 0.5, ease: 'easeOut' },
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

interface SessionViewProps {
  appConfig: AppConfig;
  messages: ReceivedChatMessage[];
  pushMessage: (text: string, origin: 'local' | 'remote') => void;
  restartStory: () => void;
}

export const SessionView = ({
  appConfig,
  messages,
  pushMessage,
  restartStory,
  ...props
}: React.ComponentProps<'section'> & SessionViewProps) => {
  const room = useRoomContext();
  const [chatOpen, setChatOpen] = useState(true);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const controls: ControlBarControls = {
    leave: true,
    microphone: true,
    chat: appConfig.supportsChatInput,
    camera: appConfig.supportsVideoInput,
    screenShare: appConfig.supportsVideoInput,
  };

  // AUTO-SCROLL when new messages arrive
  useEffect(() => {
    if (!scrollAreaRef.current) return;
    scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
  }, [messages]);

  // Track the last processed segment to avoid immediate duplicates
  const lastProcessedSegmentRef = useRef<{ id: string; text: string } | null>(null);
  const pushMessageRef = useRef(pushMessage);

  // Keep pushMessage ref updated - CRITICAL
  useEffect(() => {
    console.log('📌 Updating pushMessage ref');
    pushMessageRef.current = pushMessage;
  }, [pushMessage]);

  // LISTEN TO LIVEKIT EVENTS
  useEffect(() => {
    if (!room) return;

    console.log('🎧 Setting up LiveKit event listeners');

    // Handle transcriptions (both user and agent speech)
    const handleTranscription = (segments: any, participant?: any) => {
      if (!Array.isArray(segments)) return;

      segments.forEach((segment: any) => {
        const { id, text, final: isFinal } = segment;
        
        if (!text || !id) return;

        // Only process FINAL transcriptions
        if (isFinal) {
          const participantId = participant?.identity || participant?.sid || 'unknown';
          const localId = room.localParticipant?.identity || room.localParticipant?.sid;
          
          console.log(`📝 FINAL Transcription: participant="${participantId}", local="${localId}"`);
          console.log(`   Text: "${text.substring(0, 80)}..."`);

          // Check if this is a duplicate of the last message
          const isDuplicate = 
            lastProcessedSegmentRef.current?.id === id &&
            lastProcessedSegmentRef.current?.text === text;

          if (!isDuplicate) {
            // Determine if this is from local participant (you) or remote (agent)
            // Agent participant IDs usually start with "agent-"
            const isAgent = participantId.startsWith('agent-');
            const origin = isAgent ? 'remote' : 'local';
            
            console.log(`${isAgent ? '🤖 Agent' : '✅ User'} said (origin: ${origin}):`, text.substring(0, 60));
            console.log('📞 Calling pushMessageRef.current with:', { origin, textLength: text.length });
            
            try {
              pushMessageRef.current(text, origin);
              console.log('✅ pushMessage called successfully');
            } catch (error) {
              console.error('❌ Error calling pushMessage:', error);
            }
            
            lastProcessedSegmentRef.current = { id, text };
          } else {
            console.log('⏭️ Skipping duplicate segment');
          }
        }
      });
    };

    // Handle agent responses
    const handleChatMessage = (payload: any) => {
      const text = payload?.message || payload?.text;
      if (text) {
        console.log('🤖 Agent said:', text);
        pushMessageRef.current(text, 'remote');
      }
    };

    // Handle data channel (alternative agent response method)
    const handleDataReceived = (data: Uint8Array, participant: any) => {
      try {
        const decoded = new TextDecoder().decode(data);
        const parsed = JSON.parse(decoded);
        
        // Check if it's an agent message
        if (parsed.type === 'agent_message' || parsed.message) {
          const text = parsed.message || parsed.text;
          if (text) {
            console.log('🤖 Agent said (data):', text);
            pushMessageRef.current(text, 'remote');
          }
        }
      } catch (e) {
        // Not JSON or not a message, ignore
      }
    };

    // Register listeners
    room.on('transcriptionReceived', handleTranscription);
    room.on('chatMessageReceived', handleChatMessage);
    room.on('dataReceived', handleDataReceived);

    console.log('✅ Listeners registered');

    return () => {
      room.off('transcriptionReceived', handleTranscription);
      room.off('chatMessageReceived', handleChatMessage);
      room.off('dataReceived', handleDataReceived);
      console.log('🧹 Cleaned up listeners');
    };
  }, [room]); // ONLY room in dependencies

  return (
    <section className="bg-background relative z-10 h-full w-full overflow-hidden" {...props}>
      {/* Chat Transcript */}
      <div className="pointer-events-auto fixed inset-0 flex flex-col z-[100]" style={{ pointerEvents: 'none' }}>
        <div 
          className="flex-1 overflow-y-auto px-4 pt-4 pb-2 md:px-6" 
          ref={scrollAreaRef}
          style={{ pointerEvents: 'auto' }}
        >
          {/* Transcript Box */}
          <div className="mx-auto max-w-2xl p-4 bg-black/80 rounded" style={{ position: 'relative', zIndex: 200 }}>
            <div className="text-white font-mono text-sm space-y-3">
              {messages.length === 0 ? (
                <div className="text-gray-400 text-center">Start speaking...</div>
              ) : (
                messages.map((msg, i) => (
                  <div key={i} className={msg.from?.isLocal ? 'text-blue-400' : 'text-green-400'}>
                    <strong>{msg.from?.isLocal ? 'You' : 'Agent'}:</strong> {msg.message}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Audio output for agent */}
      <RoomAudioRenderer />

      {/* Tile Layout - LOWER Z-INDEX */}
      <div style={{ position: 'relative', zIndex: 1 }}>
        <TileLayout chatOpen={chatOpen} />
      </div>

      {/* Bottom controls */}
      <MotionBottom
        {...BOTTOM_VIEW_MOTION_PROPS}
        className="fixed inset-x-3 bottom-0 z-50 md:inset-x-12"
      >
        {appConfig.isPreConnectBufferEnabled && (
          <PreConnectMessage messages={messages} className="pb-4" />
        )}

        {/* Restart Story */}
        <div className="mb-2 flex justify-center">
          <button
            onClick={restartStory}
            className="rounded bg-red-600 px-4 py-2 text-white shadow hover:bg-red-700"
          >
            Restart Story
          </button>
        </div>

        <div className="bg-background relative mx-auto max-w-2xl pb-3 md:pb-12">
          <Fade bottom className="absolute inset-x-0 top-0 h-4 -translate-y-full" />
          <AgentControlBar controls={controls} onChatOpenChange={setChatOpen} />
        </div>
      </MotionBottom>
    </section>
  );
};