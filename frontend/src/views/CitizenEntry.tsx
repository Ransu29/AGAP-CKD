import { ArrowLeft, ArrowUpRight, BookOpen, CaretRight as ChevronRight, ClipboardText as ClipboardList, MapPin, Warning as TriangleAlert } from '../components/PhosphorIcons';

interface HomeProps {
  onStart: () => void;
  onLearn: () => void;
  onCare: () => void;
  onDetails: () => void;
  // next: one short line with the next step and its date, from the latest check
  summary?: { risk_level: string; next?: string } | null;
  unavailable?: boolean;
  evaluatedAt?: string | null;
}

const LEVEL_COLOR: Record<string, string> = { Low: '#22A75A', Medium: '#C99A12', High: '#D0583C' };

export function CitizenHome({ onStart, onLearn, onCare, onDetails, summary, unavailable }: HomeProps) {
  const level = summary?.risk_level;
  const scored = level === 'Low' || level === 'Medium' || level === 'High';
  const care = level === 'Doctor Referral';
  const failed = unavailable || (!!summary && !scored && !care);
  const tone = scored ? level!.toLowerCase() : failed ? 'unavailable' : 'new';
  // PRD v3 (l. 73): the model's score is never shown to citizens, only the level. The gauge marks the level's third.
  const band = level === 'Low' ? 0 : level === 'Medium' ? 1 : level === 'High' ? 2 : null;
  const levelTl: Record<string, string> = { Low: 'Mababa', Medium: 'Katamtaman', High: 'Mataas' };
  const CHANCE: Record<string, string> = { Low: 'Mababang chance', Medium: 'Katamtamang chance', High: 'Mataas na chance' };
  const segments = ['#22A75A', '#E8B92E', '#E57A5F'];
  return (
    <div className="citizen-dashboard">
      <header className="citizen-dashboard-header">
        <div className="flex items-center gap-2"><img src="/logo.svg" alt="" width={22} height={22} /><span className="font-extrabold">AGAP-CKD</span></div>
      </header>
      <h1 tabIndex={-1} className="citizen-dashboard-heading">Kalusugan ng bato</h1>
      <section aria-labelledby="citizen-summary-heading" className={`citizen-overview citizen-overview--${tone}`}>
        <div className="citizen-score-layout">
          <div>
            <p className="citizen-overview-label">{scored ? 'Ang iyong antas' : care ? 'Gabay' : failed ? 'Check-in' : 'Kidney check-in'}</p>
            <h2 id="citizen-summary-heading" className="citizen-level-word" style={scored ? { color: LEVEL_COLOR[level!] } : undefined}>
              {scored ? <span lang="en">{level}</span> : care ? 'Magpatingin sa doktor' : failed ? 'Hindi available ang resulta' : 'Wala pang check-in'}
            </h2>
            {scored && <p className="citizen-overview-sub">{CHANCE[level!]} ng kidney problems</p>}
          </div>
          <svg viewBox="0 0 144 92" className={`citizen-score-indicator ${band === null ? 'is-empty' : ''}`} role="img"
            aria-label={scored ? `Antas: ${levelTl[level!]}` : 'Wala pang antas'}>
            {Array.from({ length: 15 }, (_, i) => {
              const angle = Math.PI + i * Math.PI / 14;
              const third = Math.floor(i / 5);
              const lit = band !== null && third === band;
              return <line key={i} x1={72 + Math.cos(angle) * 34} y1={80 + Math.sin(angle) * 34}
                x2={72 + Math.cos(angle) * (52 + (i % 3) * 5)} y2={80 + Math.sin(angle) * (52 + (i % 3) * 5)}
                stroke={band === null ? 'currentColor' : segments[third]} strokeOpacity={band === null ? 0.45 : lit ? 1 : 0.18}
                strokeWidth={i % 3 === 0 ? 3.5 : 2.5} strokeLinecap="round" />;
            })}
            {band !== null && (() => {
              const angle = Math.PI + (band * 5 + 2) * Math.PI / 14;
              return <circle cx={72 + Math.cos(angle) * 22} cy={80 + Math.sin(angle) * 22} r={5} fill={segments[band]} />;
            })()}
          </svg>
        </div>
        {scored && summary?.next && <p className="citizen-overview-next">{summary.next}</p>}
        <p className="citizen-score-note">
          {scored ? 'Hindi ito diagnosis.' : care ? 'Walang risk level na ibinigay. Tingnan ang gabay.' : failed ? 'Walang risk level na ibinigay.' : 'Ilang tanong para malaman kung kailangan mong magpa-check ng kidneys.'}
        </p>
        {summary || failed ? (
          <div className="citizen-overview-actions">
            <button onClick={onDetails} className="citizen-action citizen-summary-action" aria-label={failed ? 'Balikan ang check-in' : 'Tingnan ang resulta'}>
              {failed ? 'Balikan' : 'Tingnan ang resulta'}<ArrowUpRight aria-hidden="true" size={17} />
            </button>
            {summary && <button onClick={onStart} className="citizen-retake">Ulitin ang check-in</button>}
          </div>
        ) : (
          <button onClick={onStart} className="citizen-action citizen-summary-action" aria-label="Simulan ang check-in">
            Simulan ang check-in<ArrowUpRight aria-hidden="true" size={17} />
          </button>
        )}
      </section>
      <section aria-labelledby="citizen-explore-heading">
        <h2 id="citizen-explore-heading" className="text-lg font-bold mb-3">Para sa iyo</h2>
        <div className="citizen-module-grid">
          <button onClick={onLearn} className="citizen-feature-card citizen-feature-card--learn">
            <BookOpen aria-hidden="true" size={28} /><span lang="en" className="font-bold text-xl">Learn</span>
            <span className="text-sm">Kaalaman, recipes at lifestyle</span><ChevronRight aria-hidden="true" size={18} className="citizen-feature-arrow" />
          </button>
          <button onClick={onCare} className="citizen-feature-card citizen-feature-card--care">
            <MapPin aria-hidden="true" size={28} /><span lang="en" className="font-bold text-xl">Care</span>
            <span className="text-sm">Mga pasilidad at serbisyo</span><ChevronRight aria-hidden="true" size={18} className="citizen-feature-arrow" />
          </button>
          <div className="citizen-track-preview">
            <ClipboardList aria-hidden="true" size={24} /><div><span lang="en" className="font-bold">Track</span><p className="text-sm">Lab results, food log at targets</p></div><span className="text-sm font-semibold" lang="en">Coming soon</span>
          </div>
        </div>
      </section>
    </div>
  );
}

export function CitizenConsent({ onAccept, onDecline }: { onAccept: () => void; onDecline: () => void }) {
  return (
    <div className="flex-1 p-5 space-y-6">
      <button onClick={onDecline} aria-label="Bumalik sa edukasyon" className="w-11 h-11 flex items-center justify-center rounded-full bg-white">
        <ArrowLeft aria-hidden="true" className="w-4 h-4" />
      </button>
      <h1 tabIndex={-1} className="text-[28px] leading-tight font-bold">Bago ka sumagot</h1>
      <div className="space-y-4 text-base">
        <p>Prototype ito, hindi serbisyong medikal. <strong>Kathang-isip na sagot lamang ang gamitin sa demo.</strong></p>
        <p>Sa huling hakbang, kapag pinili mong ipadala, ipapadala ang mga suportadong sagot sa evaluation service ng prototype para makabuo ng output. Kasama rito ang edad, kasarian, bayan, at mga sagot tungkol sa kalusugan.</p>
        <p>Hindi hinihingi ang pangalan o contact number. Hindi pa nakumpirma ang kumpletong patakaran sa retention, pagbabahagi, at paggamit sa totoong operasyon. Huwag gumamit ng tunay na personal na health information dito.</p>
        <p>Maaari kang bumalik sa edukasyon nang hindi sumasagot. Walang diagnosis na ibinibigay ang check-in.</p>
      </div>
      <div className="space-y-2">
        <button onClick={onAccept} className="citizen-action w-full py-4 px-4 rounded-full font-bold">Nauunawaan ko, magpatuloy</button>
        <button onClick={onDecline} className="w-full py-3 px-4 font-bold text-[#17573A] underline underline-offset-4">Hindi muna — bumalik sa edukasyon</button>
      </div>
    </div>
  );
}
