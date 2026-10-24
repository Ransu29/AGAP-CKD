import React, { useEffect, useRef, useState } from 'react';
import { Send } from 'lucide-react';
import { MSG, SMS_LIMIT, initialState, reply, resultMessages, type SmsState, type Step, type Town } from '../riskCheck/smsFlow';
import type { RiskCheckResult } from '../riskCheck/content';

// PRD v3 SMS channel, simulated: the same questions, model and guideline floor as the app (ADR 0003).
// Every finished check is scored by /api/risk-check/evaluate with channel "sms". No real messages are sent.
// The resident types every reply (numbers, town, height/weight, and CHECK, STOP, HELP, BACK, TULOY, DONE).
// Switching to another tab and back starts a new phone.

interface Bubble {
  id: number;
  from: 'agap' | 'resident';
  text: string;
}

const ERROR_TEXT = 'Pasensya, hindi ma-check ngayon. I-text ang TULOY mamaya para ituloy.';

export function SmsView() {
  const [towns, setTowns] = useState<Town[]>([]);
  const [state, setState] = useState<SmsState>(initialState());
  const [bubbles, setBubbles] = useState<Bubble[]>([{ id: 0, from: 'agap', text: MSG.start }]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch('/api/risk-check/municipalities')
      .then((res) => res.json())
      .then((data: Town[]) => setTowns(data))
      .catch(() => setTowns([]));
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [bubbles, busy]);

  useEffect(() => {
    if (!busy) inputRef.current?.focus();
  }, [busy]);

  const add = (from: Bubble['from'], text: string) =>
    setBubbles((list) => [...list, { id: nextId.current++, from, text }]);

  // AGAP replies arrive one by one, as separate SMS.
  const deliver = async (texts: string[]) => {
    for (const text of texts) {
      await new Promise((resolve) => setTimeout(resolve, 450));
      add('agap', text);
    }
  };

  const apply = async (step: Step) => {
    setState(step.state);
    setBusy(true);
    await deliver(step.out);
    if (step.request) {
      try {
        const res = await fetch('/api/risk-check/evaluate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(step.request),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const result: RiskCheckResult = await res.json();
        const done = resultMessages(step.state, result);
        setState(done.state);
        await deliver(done.out);
      } catch {
        await deliver([ERROR_TEXT]);
      }
    }
    setBusy(false);
  };

  const send = (text: string) => {
    const value = text.trim();
    if (!value || busy) return;
    add('resident', value);
    setDraft('');
    void apply(reply(state, value, towns));
  };

  return (
    <div className="px-4 py-8 flex justify-center">
      <div className="w-[380px] rounded-[44px] bg-[#1B2A22] p-3 shadow-[0_20px_50px_rgba(27,42,34,0.25)]">
        <div className="rounded-[34px] bg-[#F3F8F4] overflow-hidden flex flex-col h-[720px]">
          <div className="bg-[#17573A] text-white px-5 py-4 flex items-center gap-3">
            <img src="/logo.svg" alt="" className="w-9 h-9 shrink-0" />
            <div>
              <p className="font-extrabold leading-tight">AGAP-CKD</p>
              <p className="text-[11px] text-[#DDF1E4] font-semibold">SMS kidney check · simulated</p>
            </div>
          </div>

          <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3" aria-live="polite">
            {bubbles.map((b) => (
              <div key={b.id} className={`flex flex-col ${b.from === 'agap' ? 'items-start' : 'items-end'}`}>
                <div
                  className={`max-w-[85%] px-3.5 py-2.5 text-[14px] leading-snug whitespace-pre-wrap ${
                    b.from === 'agap'
                      ? 'bg-white border border-[#DCE7DF] text-[#1B2A22] rounded-2xl rounded-bl-md'
                      : 'bg-[#22A75A] text-white font-semibold rounded-2xl rounded-br-md'
                  }`}
                >
                  {b.text}
                </div>
                {b.from === 'agap' && (
                  <span className={`mt-1 text-[10px] font-bold ${b.text.length <= SMS_LIMIT ? 'text-[#5C6E63]' : 'text-[#B3261E]'}`}>
                    {b.text.length}/{SMS_LIMIT} · 1 SMS
                  </span>
                )}
              </div>
            ))}
            {busy && (
              <div className="flex items-start">
                <div className="bg-white border border-[#DCE7DF] rounded-2xl rounded-bl-md px-3.5 py-2.5 text-[#5C6E63] text-sm">…</div>
              </div>
            )}
          </div>

          <form
            className="border-t border-[#DCE7DF] bg-white px-3 py-4 flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              send(draft);
            }}
          >
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Mag-text…"
              aria-label="Message"
              className="flex-1 rounded-full border border-[#DCE7DF] bg-[#F3F8F4] px-4 py-2.5 text-sm outline-none focus:border-[#22A75A]"
            />
            <button type="submit" disabled={busy || !draft.trim()} aria-label="Send"
              className="w-10 h-10 rounded-full bg-[#22A75A] text-white flex items-center justify-center disabled:opacity-50">
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
