import { ChatMessage } from '@/types/voice-assistant';
import { Send } from 'lucide-react';
import { useState } from 'react';

interface ChatPanelProps {
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  disabled?: boolean;
}

const ChatPanel = ({ messages, onSendMessage, disabled }: ChatPanelProps) => {
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim() || disabled) return;
    onSendMessage(input.trim());
    setInput('');
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-thin">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[84%] px-5 py-3 rounded-2xl text-base md:text-lg leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-white text-black rounded-br-md border border-white/70 shadow-[0_0_18px_rgba(255,255,255,0.18)]'
                  : 'bg-black text-white rounded-bl-md border border-white/28'
              }`}
            >
              {msg.content}
              <div
                className={`mt-2 text-xs ${
                  msg.role === 'user' ? 'text-black/62' : 'text-white/52'
                }`}
              >
                {msg.timestamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Input */}
      <div className="border-t border-white/18 p-4">
        <div className="flex items-center gap-3 rounded-2xl border border-white/24 bg-black/90 px-4 py-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Digite uma mensagem..."
            disabled={disabled}
            className="flex-1 bg-transparent py-2 text-base md:text-lg text-white placeholder:text-white/45 focus:outline-none disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={disabled || !input.trim()}
            className="flex h-11 w-11 items-center justify-center rounded-xl bg-white text-black hover:bg-white/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
