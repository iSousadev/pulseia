interface SplashScreenProps {
  exiting?: boolean;
  onStart?: () => void;
  startDisabled?: boolean;
}

const SplashScreen = ({
  exiting = false,
  onStart,
  startDisabled = false,
}: SplashScreenProps) => {
  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-black transition-opacity duration-500 ${
        exiting ? "opacity-0" : "opacity-100"
      }`}
    >
      <div className="splash-noise" />
      <div className="splash-scanlines" />
      <div className="splash-fade pointer-events-none absolute left-1/2 top-1/2 z-10 h-[480px] w-[480px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/5 blur-[120px]" />

      <main className="relative z-20 flex flex-col items-center justify-center animate-splash-float">
        <div className="splash-fade-up splash-delay-1 group relative cursor-default">
          <div className="splash-beta-glow pointer-events-none absolute -inset-1 rounded-lg opacity-65 blur-lg transition-opacity duration-500" />
          <div className="relative rounded-[20px] border border-amber-200/70 bg-amber-400 px-5 py-1.5">
            <span className="text-xs font-extrabold uppercase tracking-[0.2em] text-black md:text-sm">
              Beta
            </span>
          </div>
        </div>

        <h1 className="splash-fade-up splash-delay-2 relative mt-8 select-none text-center font-black tracking-[0.2em]">
          <span className="splash-metallic text-6xl md:text-8xl lg:text-9xl">
            PULSE
          </span>
          <span className="splash-metallic ml-4 text-6xl md:ml-8 md:text-8xl lg:text-9xl">
            AI
          </span>
          <div className="absolute -bottom-8 left-1/2 h-1 w-3/4 -translate-x-1/2 rounded-full bg-gradient-to-r from-transparent via-white/20 to-transparent blur-sm" />
        </h1>

        <div className="splash-fade-up splash-delay-3 mt-12 flex items-center gap-3 font-mono text-xs uppercase tracking-widest text-gray-400/70 md:text-sm">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
          </span>
          Seu assistente de voz AI pessoal
        </div>

        <button
          onClick={onStart}
          disabled={startDisabled}
          className="splash-fade-up splash-delay-4 mt-10 inline-flex h-11 items-center justify-center rounded-full border border-white/35 bg-white/10 px-8 text-xs font-semibold uppercase tracking-[0.16em] text-white transition-all hover:border-white/60 hover:bg-white/16 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {startDisabled ? "Iniciando..." : "Comecar"}
        </button>
      </main>

      <nav className="splash-fade splash-delay-2 absolute left-0 top-0 z-30 flex w-full items-center justify-between p-8 opacity-40 transition-opacity duration-300 hover:opacity-100">
        <div className="font-mono text-xs tracking-widest text-gray-400">
          Ver 1.0.0
        </div>
        <div className="flex gap-6">
          <a
            className="font-mono text-xs uppercase tracking-widest text-gray-400 transition-colors hover:text-white"
            href="#"
          >
            Login
          </a>
          <a
            className="font-mono text-xs uppercase tracking-widest text-gray-400 transition-colors hover:text-white"
            href="#"
          >
            Request Access
          </a>
        </div>
      </nav>

      <footer className="splash-fade splash-delay-5 absolute bottom-6 z-30 w-full text-center">
        <p className="mx-auto inline-flex items-center rounded-full border border-white/20 bg-black/55 px-4 py-1 text-[10px] uppercase tracking-[0.2em] text-white/70 backdrop-blur-sm">
          <a
            className="pointer-events-auto transition-colors hover:text-white"
            href="https://github.com/iSousadev"
            target="_blank"
            rel="noreferrer"
          >
            iSousadev ✌🏼
          </a>
        </p>
      </footer>
    </div>
  );
};

export default SplashScreen;
