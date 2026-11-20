import { Toaster } from '@/components/ui/sonner';

export default function App() {
  return (
    <>
      <main className="flex min-h-svh items-center justify-center">
        <h1 className="font-heading text-2xl font-semibold">Txat_bot</h1>
      </main>
      <Toaster richColors closeButton />
    </>
  );
}
