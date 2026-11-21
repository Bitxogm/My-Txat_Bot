import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  attachmentContentUrl,
  deleteAttachment,
  isAbortError,
  listAttachments,
  uploadAttachment,
  type Attachment,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

/** Same limit as the backend (MAX_ATTACHMENTS_PER_MESSAGE). */
export const MAX_ATTACHMENTS = 5;

/** Extensions the backend accepts (domain/attachment.py); the server still checks the content. */
export const ACCEPTED_EXTENSIONS = [
  '.pdf',
  '.png',
  '.jpg',
  '.jpeg',
  '.gif',
  '.webp',
  '.txt',
  '.md',
  '.log',
  '.csv',
  '.tsv',
  '.json',
  '.xml',
  '.yaml',
  '.yml',
  '.toml',
  '.ini',
  '.conf',
  '.cfg',
  '.html',
  '.htm',
  '.css',
  '.js',
  '.ts',
  '.py',
  '.sh',
  '.ps1',
  '.php',
  '.sql',
  '.c',
  '.h',
  '.go',
  '.rs',
  '.java',
  '.rb',
  '.nmap',
  '.gnmap',
  '.nse',
  '.rules',
  '.yar',
  '.yara',
  '.eml',
  '.example',
];

export interface PendingFile {
  key: string;
  filename: string;
  size_bytes: number;
  /** null while uploading. */
  attachment: Attachment | null;
  /** Thumbnail address for an uploaded image; null otherwise. */
  previewUrl: string | null;
}

export interface UseAttachments {
  files: PendingFile[];
  ready: Attachment[];
  isUploading: boolean;
  /** Uploads to `conversationId` (created by the caller first if needed). */
  add: (conversationId: string, files: File[]) => Promise<void>;
  remove: (conversationId: string, key: string) => Promise<void>;
  /** Shows the files of `conversationId` not sent yet (null: none, e.g. a new chat). */
  load: (conversationId: string | null) => Promise<void>;
  /** Clears the list after its files were sent. */
  clear: () => void;
}

function previewOf(conversationId: string, attachment: Attachment): string | null {
  return attachment.kind === 'image' ? attachmentContentUrl(conversationId, attachment.id) : null;
}

function fromServer(conversationId: string, attachment: Attachment): PendingFile {
  return {
    key: attachment.id,
    filename: attachment.filename,
    size_bytes: attachment.size_bytes,
    attachment,
    previewUrl: previewOf(conversationId, attachment),
  };
}

export function useAttachments(): UseAttachments {
  const [files, setFiles] = useState<PendingFile[]>([]);
  // Uploads and loads belong to one conversation: switching aborts them.
  const scopeRef = useRef(new AbortController());
  const nextKey = useRef(0);
  const countRef = useRef(0);
  const filesRef = useRef<PendingFile[]>([]);

  useEffect(() => {
    filesRef.current = files;
    countRef.current = files.length;
  }, [files]);

  useEffect(() => {
    // A fresh scope on every mount: StrictMode unmounts and remounts once in development.
    scopeRef.current = new AbortController();
    return () => scopeRef.current.abort();
  }, []);

  const newScope = useCallback(() => {
    scopeRef.current.abort();
    scopeRef.current = new AbortController();
    return scopeRef.current.signal;
  }, []);

  const clear = useCallback(() => {
    newScope();
    countRef.current = 0;
    setFiles([]);
  }, [newScope]);

  const load = useCallback(
    async (conversationId: string | null) => {
      const signal = newScope();
      countRef.current = 0;
      setFiles([]);
      if (!conversationId) return;
      try {
        const { attachments } = await listAttachments(conversationId, signal);
        if (signal.aborted) return;
        const pending = attachments
          .filter((a) => !a.sent)
          .map((a) => fromServer(conversationId, a));
        countRef.current = pending.length;
        setFiles(pending);
      } catch (error) {
        if (!isAbortError(error)) notifyError(error);
      }
    },
    [newScope],
  );

  const add = useCallback(async (conversationId: string, selected: File[]) => {
    const room = MAX_ATTACHMENTS - countRef.current;
    if (selected.length > room) {
      toast.error(`Como máximo ${MAX_ATTACHMENTS} ficheros por mensaje.`);
    }
    const accepted = selected.slice(0, Math.max(room, 0));
    if (accepted.length === 0) return;
    countRef.current += accepted.length;
    const signal = scopeRef.current.signal;
    const placeholders = accepted.map((file) => ({
      key: `u${nextKey.current++}`,
      filename: file.name,
      size_bytes: file.size,
      attachment: null,
      previewUrl: null,
    }));
    setFiles((prev) => [...prev, ...placeholders]);

    await Promise.all(
      accepted.map(async (file, index) => {
        const { key } = placeholders[index];
        try {
          const attachment = await uploadAttachment(conversationId, file, signal);
          if (signal.aborted) return;
          setFiles((prev) =>
            prev.map((f) =>
              f.key === key
                ? {
                    ...f,
                    filename: attachment.filename,
                    size_bytes: attachment.size_bytes,
                    attachment,
                    previewUrl: previewOf(conversationId, attachment),
                  }
                : f,
            ),
          );
        } catch (error) {
          if (isAbortError(error) || signal.aborted) return;
          countRef.current -= 1;
          setFiles((prev) => prev.filter((f) => f.key !== key));
          notifyError(error);
        }
      }),
    );
  }, []);

  const remove = useCallback(async (conversationId: string, key: string) => {
    const target = filesRef.current.find((f) => f.key === key);
    if (!target?.attachment) return; // still uploading: the chip has no remove button yet
    countRef.current -= 1;
    setFiles((prev) => prev.filter((f) => f.key !== key));
    try {
      await deleteAttachment(conversationId, target.attachment.id);
    } catch (error) {
      notifyError(error);
    }
  }, []);

  const ready = files.flatMap((f) => (f.attachment ? [f.attachment] : []));
  return {
    files,
    ready,
    isUploading: files.some((f) => f.attachment === null),
    add,
    remove,
    load,
    clear,
  };
}
