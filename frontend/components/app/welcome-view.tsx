'use client';

import { useState } from 'react';
import { Button } from '@/components/livekit/button';

function ImprovBattleImage() {
  return (
    <svg
      width="80"
      height="80"
      viewBox="0 0 80 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="mb-6 size-20 text-primary"
    >
      {/* Stage spotlight */}
      <circle cx="40" cy="25" r="15" fill="currentColor" opacity="0.2" />
      
      {/* Microphone stand and body */}
      <path
        d="M40 15C37.2386 15 35 17.2386 35 20V30C35 32.7614 37.2386 35 40 35C42.7614 35 45 32.7614 45 30V20C45 17.2386 42.7614 15 40 15Z"
        fill="currentColor"
      />
      
      {/* Microphone base and connector */}
      <path
        d="M30 28C30.5523 28 31 28.4477 31 29V30C31 35.5228 35.4772 40 41 40C46.5228 40 51 35.5228 51 30V29C51 28.4477 51.4477 28 52 28C52.5523 28 53 28.4477 53 29V30C53 36.2868 48.3281 41.4347 42.5 42.2011V50H47C47.5523 50 48 50.4477 48 51C48 51.5523 47.5523 52 47 52H33C32.4477 52 32 51.5523 32 51C32 50.4477 32.4477 50 33 50H37.5V42.2011C31.6719 41.4347 27 36.2868 27 30V29C27 28.4477 27.4477 28 28 28H30Z"
        fill="currentColor"
      />
      
      {/* Comedy mask (smiling) */}
      <circle cx="25" cy="60" r="3" fill="currentColor" opacity="0.6" />
      <path
        d="M20 60C20 57 22 55 25 55C28 55 30 57 30 60"
        stroke="currentColor"
        strokeWidth="2"
        fill="none"
        opacity="0.6"
      />
      
      {/* Drama mask (frowning) */}
      <circle cx="55" cy="60" r="3" fill="currentColor" opacity="0.6" />
      <path
        d="M50 60C50 63 52 65 55 65C58 65 60 63 60 60"
        stroke="currentColor"
        strokeWidth="2"
        fill="none"
        opacity="0.6"
      />
    </svg>
  );
}

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: (playerName: string) => void;
}

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  const [playerName, setPlayerName] = useState('');
  const [isStarting, setIsStarting] = useState(false);

  const handleStart = () => {
    const name = playerName.trim() || 'Player';
    setIsStarting(true);
    onStartCall(name);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleStart();
    }
  };

  return (
    <div ref={ref} className="h-full w-full flex items-center justify-center">
      <section className="bg-background flex flex-col items-center justify-center text-center px-4 max-w-3xl">
        <ImprovBattleImage />

        <h1 className="text-foreground text-4xl md:text-5xl font-bold mb-3 tracking-tight">
          🎭 Improv Battle
        </h1>

        <p className="text-muted-foreground max-w-prose pt-2 pb-6 leading-6 font-medium text-pretty">
          Step into the spotlight! Your AI host will give you wild improv scenarios.
          <br />
          Act them out and get real, honest feedback on your performance.
        </p>

        {/* Name Input */}
        <div className="w-full max-w-md space-y-4">
          <div className="space-y-2">
            <label 
              htmlFor="player-name" 
              className="text-foreground text-sm font-medium block text-left"
            >
              Your Name (Optional)
            </label>
            <input
              id="player-name"
              type="text"
              placeholder="Enter your name..."
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={isStarting}
              className="w-full px-4 py-3 rounded-lg border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              maxLength={30}
              autoComplete="off"
            />
          </div>

          <Button 
            variant="primary" 
            size="lg" 
            onClick={handleStart}
            disabled={isStarting}
            className="w-full font-mono text-base"
          >
            {isStarting ? 'Starting...' : startButtonText}
          </Button>
        </div>

        {/* Game Info */}
        <div className="mt-8 max-w-md space-y-2 text-sm text-muted-foreground">
          <p className="font-semibold text-foreground text-base mb-3">How it works:</p>
          <div className="bg-muted/50 rounded-lg p-4 text-left space-y-2">
            <div className="flex items-start gap-2">
              <span className="text-primary font-bold">1.</span>
              <span>You'll get 3 improv scenarios</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-primary font-bold">2.</span>
              <span>Act out each scene using your voice</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-primary font-bold">3.</span>
              <span>The host will react and give you feedback</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-primary font-bold">4.</span>
              <span>Say <strong className="text-foreground">"end scene"</strong> when you're done with each scenario</span>
            </div>
          </div>
        </div>
      </section>

      <div className="fixed bottom-5 left-0 flex w-full items-center justify-center px-4">
        <p className="text-muted-foreground max-w-prose pt-1 text-xs leading-5 font-normal text-pretty md:text-sm text-center">
          Powered by LiveKit Voice AI •{' '}
          <a
            target="_blank"
            rel="noopener noreferrer"
            href="https://docs.livekit.io/agents/start/voice-ai/"
            className="underline hover:text-foreground transition-colors"
          >
            Learn more
          </a>
        </p>
      </div>
    </div>
  );
};