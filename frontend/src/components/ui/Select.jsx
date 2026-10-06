import { useEffect, useId, useRef, useState } from "react";
import "./Select.css";

/**
 * Styled dropdown (WAI-ARIA "select-only combobox").
 *
 * Same contract as a native <select>: `value`, `options: [{ value, label }]` and
 * `onChange({ target: { value } })`, so callers don't change. The open list is our
 * own element, so it matches the design system on every browser (a native list
 * can't be styled). Keyboard: Enter/Space/Alt+ArrowDown open; arrows, Home/End and
 * type-ahead move; Enter selects; Escape/Tab close.
 */
export default function Select({
  label,
  id,
  options,
  value,
  onChange,
  className = "",
  hideLabel = false,
  prefix,
  size = "md",
  placement = "auto",
  disabled = false,
}) {
  const generated = useId();
  const baseId = id || `select-${generated}`;
  const labelId = `${baseId}-label`;
  const listId = `${baseId}-list`;
  const [open, setOpen] = useState(false);
  const [openUp, setOpenUp] = useState(placement === "up");
  const selectedIndex = Math.max(0, options.findIndex((option) => String(option.value) === String(value ?? "")));
  const [active, setActive] = useState(selectedIndex);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const listRef = useRef(null);
  const typed = useRef({ text: "", at: 0 });

  const selected = options[selectedIndex];

  useEffect(() => {
    if (!open) return undefined;
    function onPointer(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [open]);

  // Keep the highlighted option visible by scrolling the list only - never the page.
  useEffect(() => {
    const list = listRef.current;
    const item = open ? list?.querySelector(`[data-index="${active}"]`) : null;
    if (!list || !item) return;
    if (item.offsetTop < list.scrollTop) list.scrollTop = item.offsetTop;
    else if (item.offsetTop + item.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTop = item.offsetTop + item.offsetHeight - list.clientHeight;
    }
  }, [open, active]);

  function openList() {
    if (disabled) return;
    if (placement === "auto") {
      // Open upwards when the list wouldn't fit below, instead of pushing the page.
      const rect = triggerRef.current?.getBoundingClientRect();
      const needed = Math.min(280, options.length * 38 + 10);
      const below = rect ? window.innerHeight - rect.bottom - 8 : needed;
      setOpenUp(Boolean(rect) && below < needed && rect.top > below);
    }
    setActive(selectedIndex);
    setOpen(true);
  }

  function choose(index) {
    const option = options[index];
    setOpen(false);
    triggerRef.current?.focus();
    if (option && String(option.value) !== String(value ?? "")) onChange?.({ target: { value: option.value } });
  }

  function typeAhead(key) {
    const now = Date.now();
    typed.current = { text: (now - typed.current.at < 600 ? typed.current.text : "") + key.toLowerCase(), at: now };
    const start = open ? active : selectedIndex;
    const ordered = [...options.keys()].map((offset) => (start + 1 + offset) % options.length);
    const match = ordered.find((index) => String(options[index].label).toLowerCase().startsWith(typed.current.text));
    if (match === undefined) return;
    if (open) setActive(match);
    else choose(match);
  }

  function onKeyDown(event) {
    const { key } = event;
    if (!open) {
      if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(key)) {
        event.preventDefault();
        openList();
      } else if (key.length === 1 && /\S/.test(key)) {
        typeAhead(key);
      }
      return;
    }
    if (key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(options.length - 1, index + 1));
    } else if (key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(0, index - 1));
    } else if (key === "Home") {
      event.preventDefault();
      setActive(0);
    } else if (key === "End") {
      event.preventDefault();
      setActive(options.length - 1);
    } else if (key === "Enter" || key === " ") {
      event.preventDefault();
      choose(active);
    } else if (key === "Escape") {
      event.preventDefault();
      setOpen(false);
    } else if (key === "Tab") {
      setOpen(false);
    } else if (key.length === 1 && /\S/.test(key)) {
      typeAhead(key);
    }
  }

  return (
    <div className={`select-field select-field--${size} select-field--${openUp ? "up" : "down"} ${className}`.trim()} ref={rootRef}>
      {label && (
        <span id={labelId} className={hideLabel ? "visually-hidden" : "select-field__label"}>
          {label}
        </span>
      )}
      <button
        ref={triggerRef}
        id={baseId}
        type="button"
        role="combobox"
        className={`select-field__control ${open ? "is-open" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-labelledby={label ? labelId : undefined}
        aria-activedescendant={open ? `${baseId}-opt-${active}` : undefined}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
      >
        {prefix && <span className="select-field__prefix">{prefix}</span>}
        <span className="select-field__value">{selected?.label}</span>
        <svg className="select-field__chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <ul ref={listRef} id={listId} role="listbox" className="select-field__list" aria-labelledby={label ? labelId : undefined} tabIndex={-1}>
          {options.map((option, index) => {
            const isSelected = index === selectedIndex;
            return (
              <li
                key={String(option.value)}
                id={`${baseId}-opt-${index}`}
                data-index={index}
                role="option"
                aria-selected={isSelected}
                className={`select-field__option ${index === active ? "is-active" : ""} ${isSelected ? "is-selected" : ""}`}
                onMouseEnter={() => setActive(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(index)}
              >
                <span title={String(option.label)}>{option.label}</span>
                {isSelected && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                    <path d="M5 12l5 5L20 7" />
                  </svg>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
