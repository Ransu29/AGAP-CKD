import React, { useState, useEffect } from 'react';
import { Smartphone, MessageSquare, Tablet, BarChart2, Shield } from 'lucide-react';
import { CitizenView } from './views/CitizenView';
import { FieldWorkerView } from './views/FieldWorkerView';
import { SmsView } from './views/SmsView';
import { AnalystView } from './views/AnalystView';

// PRD v3 has three views (citizen, field health worker, analyst) and three citizen channels (app, SMS,
// field tablet). The earlier coordinator worklist (allocation design) is outside PRD v3 and was removed.
type Channel = 'citizen' | 'sms' | 'field' | 'analyst';

export default function App() {
  const [channel, setChannel] = useState<Channel>('citizen');
  const [meta, setMeta] = useState<{ status: string; run_id: string } | null>(null);

  useEffect(() => {
    fetch('/api/meta')
      .then((res) => res.json())
      .then((data) => setMeta(data))
      .catch((err) => console.warn('Backend meta ping:', err));
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-[#F3F8F4] text-[#1B2A22] font-['Nunito',sans-serif]">
      {/* Main Navigation Header */}
      <header className="bg-white border-b border-[#DCE7DF]/80 sticky top-0 z-40 shadow-sm">
        <div className="max-w-[1360px] mx-auto px-4 sm:px-6 flex flex-col lg:flex-row justify-between items-center py-3.5 gap-4">
          <div className="flex items-center gap-3.5">
            <img src="/logo.svg" alt="" className="w-10 h-10 shrink-0" />
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-lg text-[#1B2A22] tracking-tight">AGAP-CKD</span>
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-extrabold bg-[#DDF1E4] text-[#17573A] whitespace-nowrap">
                  Province of Laguna · PJDSC 2026
                </span>
              </div>
              <p className="text-xs text-[#5C6E63] font-semibold">
                Kidney risk check for Laguna
              </p>
            </div>
          </div>

          {/* Channel switcher: citizen app, SMS, field tablet, analyst */}
          <nav className="flex items-center gap-1 bg-[#F3F8F4] p-1.5 rounded-full border border-[#DCE7DF] overflow-x-auto max-w-full">
            <button
              onClick={() => setChannel('citizen')}
              className={`flex items-center gap-2 px-3.5 sm:px-4 py-2 rounded-full text-xs font-extrabold whitespace-nowrap transition ${
                channel === 'citizen'
                  ? 'bg-[#1B2A22] text-white shadow-sm'
                  : 'text-[#3E5046] hover:text-[#1B2A22]'
              }`}
            >
              <Smartphone className="w-3.5 h-3.5 shrink-0" />
              <span>Citizen App</span>
            </button>

            <button
              onClick={() => setChannel('sms')}
              className={`flex items-center gap-2 px-3.5 sm:px-4 py-2 rounded-full text-xs font-extrabold whitespace-nowrap transition ${
                channel === 'sms'
                  ? 'bg-[#1B2A22] text-white shadow-sm'
                  : 'text-[#3E5046] hover:text-[#1B2A22]'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5 shrink-0" />
              <span>SMS</span>
            </button>

            <button
              onClick={() => setChannel('field')}
              className={`flex items-center gap-2 px-3.5 sm:px-4 py-2 rounded-full text-xs font-extrabold whitespace-nowrap transition ${
                channel === 'field'
                  ? 'bg-[#1B2A22] text-white shadow-sm'
                  : 'text-[#3E5046] hover:text-[#1B2A22]'
              }`}
            >
              <Tablet className="w-3.5 h-3.5 shrink-0" />
              <span>Field Worker</span>
            </button>

            <button
              onClick={() => setChannel('analyst')}
              className={`flex items-center gap-2 px-3.5 sm:px-4 py-2 rounded-full text-xs font-extrabold whitespace-nowrap transition ${
                channel === 'analyst'
                  ? 'bg-[#1B2A22] text-white shadow-sm'
                  : 'text-[#3E5046] hover:text-[#1B2A22]'
              }`}
            >
              <BarChart2 className="w-3.5 h-3.5 shrink-0" />
              <span>Analyst & Climate</span>
            </button>
          </nav>
        </div>
      </header>

      {/* Main View Area */}
      <main className="flex-1">
        {channel === 'citizen' && <CitizenView />}
        {channel === 'field' && <FieldWorkerView />}
        {channel === 'sms' && <SmsView />}
        {channel === 'analyst' && <AnalystView />}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-[#DCE7DF] py-4 px-6 text-center text-xs text-[#5C6E63]">
        <div className="flex items-center justify-center gap-2 font-bold text-[#17573A]">
          <Shield className="w-4 h-4 text-[#22A75A]" />
          <span>AGAP-CKD · Accessible, Geospatial, Awareness-focused, and Population-level CKD Risk Assessment</span>
        </div>
      </footer>
    </div>
  );
}
