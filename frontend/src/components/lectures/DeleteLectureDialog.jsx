import { useState } from "react";
import Modal from "../ui/Modal";
import Button from "../ui/Button";
import Alert from "../ui/Alert";
import { deleteLecture } from "../../services/lectures";

export default function DeleteLectureDialog({ lecture, onClose, onDeleted }) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(null);

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await deleteLecture(lecture.id);
      onDeleted(lecture);
    } catch (failure) {
      setError(failure.status === 404 ? "This lecture no longer exists." : failure.message);
      setDeleting(false);
    }
  }

  return (
    <Modal
      title="Delete this lecture?"
      description={`"${lecture.title}" and its media will be permanently deleted. This can't be undone.`}
      onClose={onClose}
      busy={deleting}
      actions={
        <>
          <Button variant="secondary" onClick={onClose} disabled={deleting}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleDelete} disabled={deleting} aria-busy={deleting}>
            {deleting ? "Deleting…" : "Delete Lecture"}
          </Button>
        </>
      }
    >
      {error && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <Alert tone="error">{error}</Alert>
        </div>
      )}
    </Modal>
  );
}
