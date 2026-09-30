import { useEffect, useRef, useState } from "react";
import { MoreIcon, TrashIcon } from "../ui/icons";
import "./LectureMenu.css";

/** The "⋮" actions menu on a lecture. Every item performs a real action. */
export default function LectureMenu({ lecture, onDelete }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function handlePointer(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    }
    function handleKey(event) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  return (
    <div className="lecture-menu" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="lecture-menu__trigger"
        aria-label={`More actions for ${lecture.title}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <MoreIcon size={18} />
      </button>
      {open && (
        <div className="lecture-menu__list" role="menu">
          <button
            type="button"
            role="menuitem"
            className="lecture-menu__item lecture-menu__item--danger"
            onClick={() => {
              setOpen(false);
              onDelete(lecture);
            }}
          >
            <TrashIcon size={14} />
            Delete lecture
          </button>
        </div>
      )}
    </div>
  );
}
