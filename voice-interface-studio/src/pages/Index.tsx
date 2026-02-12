import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, MessageCircle, Power, X } from "lucide-react";

import ChatPanel from "@/components/voice/ChatPanel";
import SplashScreen from "@/components/voice/SplashScreen";
import { useLivekitSession } from "@/hooks/useLivekitSession";

const BOOT_QUIPS = [
  "Acordando a IA no ódio e no café...",
  "Xingando a latência até ela tomar vergonha...",
  "Expulsando bug folgado no grito...",
  "Fingindo que essa arquitetura foi planejada...",
  "Negociando com o caos em tom passivo-agressivo...",
  "Dando bronca no deploy até ele respeitar...",
  "Empurrando dependência quebrada ladeira abaixo...",
  "Aplicando gambiarra premium com confiança suspeita...",
  "Transformando pane em feature por falta de opção...",
  "Se funcionar, genial. se não, culpa do universo...",
  "Reiniciando serviço com fé e um pouco de desespero...",
  "Sussurrando código para a máquina em tom de súplica...",
  "Aguardando milagres tecnológicos com paciência duvidosa...",
];

const Index = () => {
  const [splashPhase, setSplashPhase] = useState<"show" | "hide" | "done">(
    "show",
  );
  const [isStarting, setIsStarting] = useState(false);
  const [bootReady, setBootReady] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loadingLineIndex, setLoadingLineIndex] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [autoConnectTriggered, setAutoConnectTriggered] = useState(false);
  const splashTimerRef = useRef<number | null>(null);
  const {
    state,
    messages,
    liveCaption,
    errorMessage,
    assistantConnected,
    connect,
    disconnect,
    sendMessage,
  } = useLivekitSession();

  const isActive =
    state === "listening" || state === "speaking" || state === "thinking";
  const isConnected = state !== "idle" && state !== "error";
  const canUseChat =
    state !== "idle" && state !== "connecting" && state !== "error";

  const handleSendMessage = useCallback(
    async (content: string) => {
      await sendMessage(content);
    },
    [sendMessage],
  );

  const statusLabel = useMemo(() => {
    if (liveCaption) {
      return liveCaption;
    }
    if (state === "idle") return "Toque para conectar";
    if (state === "connecting") return "Conectando...";
    if (state === "connected") return "Conectado";
    if (state === "listening") return "Ouvindo";
    if (state === "thinking") return "Pensando";
    if (state === "speaking") return "Falando";
    return "Erro de conexao";
  }, [liveCaption, state]);

  const handleStart = useCallback(() => {
    if (isStarting || splashPhase !== "show") {
      return;
    }
    setIsStarting(true);
    setBootReady(false);
    setLoadingProgress(0);
    setLoadingLineIndex(0);
    setSplashPhase("hide");
    splashTimerRef.current = window.setTimeout(() => {
      setSplashPhase("done");
    }, 520);
  }, [isStarting, splashPhase]);

  useEffect(() => {
    return () => {
      if (splashTimerRef.current !== null) {
        window.clearTimeout(splashTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (bootReady) {
      return;
    }
    if (autoConnectTriggered) {
      return;
    }
    if (splashPhase !== "done") {
      return;
    }
    if (state !== "idle") {
      return;
    }

    setAutoConnectTriggered(true);
    void connect();
  }, [autoConnectTriggered, bootReady, connect, splashPhase, state]);

  useEffect(() => {
    if (splashPhase !== "done" || bootReady) {
      return;
    }

    const timer = window.setInterval(() => {
      setLoadingLineIndex((current) => (current + 1) % BOOT_QUIPS.length);
    }, 3600);

    return () => window.clearInterval(timer);
  }, [bootReady, splashPhase]);

  useEffect(() => {
    if (splashPhase !== "done" || bootReady) {
      return;
    }

    let target = 14;
    if (state === "connecting") {
      target = 46;
    } else if (state !== "idle") {
      target = 88;
    }
    if (assistantConnected || state === "error") {
      target = 100;
    }

    const timer = window.setInterval(() => {
      setLoadingProgress((current) => {
        if (current >= target) {
          return current;
        }
        const step =
          target === 100 ? 4 : Math.max(0.9, (target - current) * 0.08);
        return Math.min(target, current + step);
      });
    }, 70);

    return () => window.clearInterval(timer);
  }, [assistantConnected, bootReady, splashPhase, state]);

  useEffect(() => {
    if (splashPhase !== "done" || bootReady) {
      return;
    }
    if (!(assistantConnected || state === "error")) {
      return;
    }
    if (loadingProgress < 100) {
      return;
    }

    const timer = window.setTimeout(() => {
      setBootReady(true);
    }, 260);

    return () => window.clearTimeout(timer);
  }, [assistantConnected, bootReady, loadingProgress, splashPhase, state]);

  if (splashPhase !== "done") {
    return (
      <SplashScreen
        exiting={splashPhase === "hide"}
        onStart={handleStart}
        startDisabled={isStarting}
      />
    );
  }

  if (!bootReady) {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center bg-black text-white">
        <div className="splash-noise" />
        <div className="splash-scanlines" />
        <div className="relative z-20 w-[84vw] max-w-[560px]">
          <div className="mb-4 flex items-end justify-between">
            <span className="font-mono text-xs uppercase tracking-[0.2em] text-white/45">
              Carregando
            </span>
            <span className="font-mono text-2xl font-semibold tracking-[0.08em] text-white/82">
              {Math.round(loadingProgress)}%
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-white/12">
            <div
              className="h-full rounded-full bg-white transition-[width] duration-200 ease-out"
              style={{ width: `${Math.round(loadingProgress)}%` }}
            />
          </div>
          <p className="mt-6 text-center font-mono text-xs uppercase tracking-[0.14em] text-white/58 md:text-sm">
            {BOOT_QUIPS[loadingLineIndex]}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 flex flex-col items-center justify-center bg-black text-white select-none">
      <div className="relative flex items-center justify-center">
        <div
          className={`relative w-40 h-40 md:w-44 md:h-44 rounded-full flex items-center justify-center border transition-all duration-500 ${
            isActive
              ? "bg-white/10 border-white/35 shadow-[0_0_56px_rgba(255,255,255,0.3)]"
              : state === "error"
                ? "bg-white/8 border-white/28"
                : "bg-white/5 border-white/20"
          }`}
        >
          <div className="flex h-8 items-end gap-1">
            {[0, 0.15, 0.3, 0.15, 0].map((delay, index) => (
              <div
                key={index}
                className={`w-[5px] rounded-full transition-all duration-300 ${
                  isActive
                    ? "bg-white"
                    : state === "error"
                      ? "bg-white/55"
                      : "bg-white/32"
                }`}
                style={{
                  height: isActive ? undefined : "8px",
                  animation: isActive
                    ? `bar-wave 1s ease-in-out ${delay}s infinite`
                    : "none",
                }}
              />
            ))}
          </div>
        </div>
      </div>

      <p
        className={`mt-12 max-w-[84vw] text-lg md:text-2xl tracking-[0.24em] uppercase text-center transition-colors duration-500 ${
          isActive ? "text-white/92" : "text-white/58"
        }`}
      >
        {statusLabel}
      </p>
      {state === "error" && errorMessage && (
        <p className="mt-4 max-w-[88vw] whitespace-pre-line text-center text-sm md:text-base text-white/80 leading-relaxed">
          {errorMessage}
        </p>
      )}

      <button
        onClick={() => {
          if (isConnected) {
            void disconnect();
            return;
          }
          void connect();
        }}
        disabled={state === "connecting"}
        className={`absolute right-7 top-7 inline-flex h-10 items-center justify-center gap-2 rounded-full border px-4 text-sm tracking-[0.08em] uppercase transition-all disabled:opacity-60 ${
          isConnected
            ? "border-white/55 bg-white/10 text-white hover:bg-white/16"
            : "border-white/35 text-white/80 hover:border-white/55 hover:text-white"
        }`}
      >
        {state === "connecting" ? (
          <>
            <LoaderCircle className="h-4 w-4 animate-spin" />
            <span>Conectando</span>
          </>
        ) : (
          <>
            <Power className="h-4 w-4" />
            <span>{isConnected ? "Encerrar" : "Conectar"}</span>
          </>
        )}
      </button>

      <button
        onClick={() => setChatOpen((value) => !value)}
        className={`absolute bottom-10 right-8 flex h-14 w-14 items-center justify-center rounded-full transition-all duration-300 ${
          chatOpen
            ? "border border-white bg-white text-black"
            : "border border-white/35 text-white/78 hover:text-white hover:border-white/70"
        }`}
      >
        {chatOpen ? (
          <X className="w-6 h-6" />
        ) : (
          <MessageCircle className="w-6 h-6" />
        )}
      </button>

      <div
        className={`absolute bottom-0 left-0 right-0 transition-transform duration-500 ease-out ${
          chatOpen ? "translate-y-0" : "translate-y-full"
        }`}
      >
        <div className="h-[60vh] rounded-t-3xl border-t border-white/22 bg-black/96 backdrop-blur-2xl flex flex-col overflow-hidden">
          <div className="flex justify-center pt-3 pb-1">
            <div className="h-1.5 w-12 rounded-full bg-white/25" />
          </div>
          <ChatPanel
            messages={messages}
            onSendMessage={(message) => void handleSendMessage(message)}
            disabled={!canUseChat}
          />
        </div>
      </div>
    </div>
  );
};

export default Index;
