import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import "./Modal.css";

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * Accessible dialog for focused decisions (e.g. destructive confirmations).
 * Traps focus, closes on Escape / backdrop click unless `busy`, and restores
 * focus to the element that opened it.
 */
export default function Modal({ title, description, children, actions, onClose, busy = false }) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef(null);

  useEffect(() => {
    const opener = document.activeElement;
    const dialog = dialogRef.current;
    dialog.querySelector(FOCUSABLE)?.focus();

    function handleKeyDown(event) {
      if (event.key === "Escape" && !busy) {
        event.stopPropagation();
        onClose();
      }
      if (event.key === "Tab") {
        const items = [...dialog.querySelectorAll(FOCUSABLE)];
        if (items.length === 0) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    dialog.addEventListener("keydown", handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      dialog.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, [onClose, busy]);

  return createPortal(
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
      >
        <h2 id={titleId} className="modal__title">
          {title}
        </h2>
        {description && (
          <p id={descriptionId} className="modal__description">
            {description}
          </p>
        )}
        {children}
        {actions && <div className="modal__actions">{actions}</div>}
      </div>
    </div>,
    document.body
  );
}
