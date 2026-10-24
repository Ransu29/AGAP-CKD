import { useEffect, useRef, useState } from 'react';
import { CaretDown, Check } from './PhosphorIcons';

interface Props {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  placeholder?: string;
}

export function CitizenSelect({ id, label, value, options, onChange, placeholder = 'Pumili ng sagot' }: Props) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef({ text: '', time: 0 });
  const selected = options.findIndex(option => option.value === value);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  useEffect(() => {
    if (open) document.getElementById(`${id}-option-${active}`)?.scrollIntoView({ block: 'nearest' });
  }, [open, active, id]);
  function choose(index: number) {
    const option = options[index];
    if (!option) return;
    onChange(option.value); setOpen(false); trigger.current?.focus();
  }
  return <div ref={root} className="citizen-select" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  }}>
    <span id={`${id}-label`} className="block text-sm font-bold text-[#5C6E63] mb-2">{label}</span>
    <button id={id} ref={trigger} type="button" role="combobox" aria-haspopup="listbox"
      aria-labelledby={`${id}-label ${id}-value`} aria-expanded={open}
      aria-controls={open ? `${id}-list` : undefined}
      aria-activedescendant={open && options[active] ? `${id}-option-${active}` : undefined}
      className="citizen-select-trigger" onClick={() => { setActive(Math.max(0, selected)); setOpen(!open); }}
      onKeyDown={event => {
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          if (!open) { setOpen(true); setActive(event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : selected >= 0 ? selected : event.key === 'ArrowUp' ? options.length - 1 : 0); }
          else if (event.key === 'Home') setActive(0);
          else if (event.key === 'End') setActive(options.length - 1);
          else setActive(index => (index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % Math.max(1, options.length));
        } else if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault(); if (open) choose(active); else { setActive(Math.max(0, selected)); setOpen(true); }
        } else if (event.key === 'Escape') { event.preventDefault(); setOpen(false); }
        else if (event.key === 'Tab') setOpen(false);
        else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          event.preventDefault();
          const now = Date.now();
          search.current = { text: (now - search.current.time < 600 ? search.current.text : '') + event.key.toLowerCase(), time: now };
          const index = options.findIndex(option => option.label.toLowerCase().startsWith(search.current.text));
          if (index >= 0) { setActive(index); setOpen(true); }
        }
      }}>
      <span id={`${id}-value`} className={selected < 0 ? 'text-[#5C6E63]' : ''}>{options[selected]?.label || placeholder}</span>
      <CaretDown aria-hidden="true" size={19} className={open ? 'rotate-180' : ''} />
    </button>
    {open && <ul id={`${id}-list`} role="listbox" aria-labelledby={`${id}-label`} className="citizen-select-menu">
      {options.map((option, index) => <li key={option.value} id={`${id}-option-${index}`} role="option"
        aria-selected={value === option.value} className={`citizen-select-option ${index === active ? 'is-active' : ''}`}
        onPointerMove={() => setActive(index)} onPointerDown={event => event.preventDefault()} onClick={() => choose(index)}>
        <span>{option.label}</span>{value === option.value && <Check aria-hidden="true" size={18} />}
      </li>)}
      {options.length === 0 && <li className="p-3 text-sm">Walang pagpipilian.</li>}
    </ul>}
  </div>;
}
