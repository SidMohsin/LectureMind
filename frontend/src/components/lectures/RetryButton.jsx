import { useState } from "react";
import Button from "../ui/Button";
import { RefreshIcon } from "../ui/icons";
import { useToast } from "../ui/Toast";
import { retryProcessing } from "../../services/ingestion";

/** Re-queues a failed lecture. Only rendered when the failure is retryable. */
export default function RetryButton({ lecture, onRetried, variant = "destructive", className = "" }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function handleRetry() {
    setBusy(true);
    try {
      await retryProcessing(lecture.id);
      toast.show(`Processing restarted for "${lecture.title}".`);
      onRetried?.();
    } catch (error) {
      toast.show(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button variant={variant} onClick={handleRetry} disabled={busy} aria-busy={busy} className={className}>
      <RefreshIcon size={15} />
      {busy ? "Retrying…" : "Retry Processing"}
    </Button>
  );
}
