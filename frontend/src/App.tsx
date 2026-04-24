export default function App() {
  return (
    <main className="min-h-screen bg-gray-50 p-8 text-gray-900" dir="rtl" lang="he">
      <header className="mx-auto max-w-3xl">
        <h1 className="text-3xl font-bold tracking-tight">Receptra</h1>
        <p className="mt-2 text-sm text-gray-600">
          Foundation skeleton — Phase 1. Live Hebrew transcript + grounded suggestions land in Phase
          6.
        </p>
      </header>
      <section className="mx-auto mt-8 max-w-3xl rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">Status</h2>
        <ul className="mt-2 list-inside list-disc text-sm text-gray-700">
          <li>
            Backend: <code className="rounded bg-gray-100 px-1">GET /healthz</code>
          </li>
          <li>Frontend: Vite dev server on port 5173</li>
          <li>Next phase: Hebrew streaming STT (Phase 2)</li>
        </ul>
      </section>
    </main>
  )
}
