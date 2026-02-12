import { Link, useLocation } from "react-router-dom";
import { useEffect, useMemo } from "react";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  const pageLabel = useMemo(() => {
    if (location.pathname === "/login") return "LOGIN";
    if (location.pathname === "/request-access") return "REQUEST ACCESS";
    return "PAGE";
  }, [location.pathname]);

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-black text-white">
      <div className="splash-noise" />
      <div className="splash-scanlines" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[420px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/5 blur-[100px]" />

      <div className="relative z-10 mx-auto flex w-full max-w-2xl flex-col items-center px-6 text-center">
        <span className="rounded-full border border-amber-200/60 bg-amber-400 px-4 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-black">
          Indisponivel
        </span>
        <h1 className="mt-8 text-6xl font-black tracking-[0.2em] md:text-7xl">404</h1>
        <p className="mt-4 font-mono text-sm uppercase tracking-[0.18em] text-gray-400">{pageLabel} nao esta disponivel no momento</p>

        <div className="mt-10 flex items-center gap-4">
          <Link
            to="/"
            className="inline-flex h-11 items-center justify-center rounded-full border border-white/40 bg-white/10 px-7 text-xs font-semibold uppercase tracking-[0.16em] text-white transition-all hover:border-white/70 hover:bg-white/20"
          >
            Voltar para inicio
          </Link>
        </div>
      </div>
    </div>
  );
};

export default NotFound;
