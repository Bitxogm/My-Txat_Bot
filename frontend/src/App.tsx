import { Toaster } from '@/components/ui/sonner';
import { ChatPage } from '@/features/chat/chat-page';

export default function App() {
  return (
    <>
      <ChatPage />
      <Toaster richColors closeButton />
    </>
  );
}
