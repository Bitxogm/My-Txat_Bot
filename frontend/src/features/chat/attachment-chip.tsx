import { FileTextIcon, LoaderCircleIcon, XIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface AttachmentChipProps {
  filename: string;
  sizeBytes: number;
  uploading?: boolean;
  truncated?: boolean;
  onRemove?: () => void;
  /** Thumbnail of an image attachment. */
  previewUrl?: string | null;
  className?: string;
}

/** A file name as a small pill: in the composer (removable) and on sent messages. */
export function AttachmentChip({
  filename,
  sizeBytes,
  uploading = false,
  truncated = false,
  onRemove,
  previewUrl = null,
  className,
}: AttachmentChipProps) {
  const detail = uploading
    ? 'subiendo…'
    : truncated
      ? `${formatSize(sizeBytes)} · recortado`
      : formatSize(sizeBytes);
  return (
    <span
      className={cn(
        'bg-background text-foreground inline-flex max-w-64 items-center gap-1.5 rounded-lg border px-2 py-1 text-xs',
        className,
      )}
      title={truncated ? `${filename}: el modelo solo recibió una parte del texto` : filename}
    >
      {uploading ? (
        <LoaderCircleIcon className="size-3.5 shrink-0 animate-spin" aria-hidden />
      ) : previewUrl ? (
        <img
          src={previewUrl}
          alt=""
          className="size-6 shrink-0 rounded-sm object-cover"
          loading="lazy"
        />
      ) : (
        <FileTextIcon className="size-3.5 shrink-0" aria-hidden />
      )}
      <span className="truncate">{filename}</span>
      <span className="text-muted-foreground shrink-0">{detail}</span>
      {onRemove && !uploading && (
        <button
          type="button"
          onClick={onRemove}
          className="text-muted-foreground hover:text-foreground -mr-0.5 rounded-sm"
          aria-label={`Quitar ${filename}`}
        >
          <XIcon className="size-3.5" />
        </button>
      )}
    </span>
  );
}
