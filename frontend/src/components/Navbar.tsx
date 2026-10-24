export default function Navbar() {
  return (
    <header className="border-b border-zinc-800 bg-zinc-950">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4">
        <h1 className="text-lg font-semibold tracking-tight text-white">
          Maya — AI Fraud Engine
        </h1>
        <div className="flex items-center gap-2 text-emerald-400">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
          </span>
          <span className="text-sm font-medium">System Online</span>
        </div>
      </div>
    </header>
  );
}
