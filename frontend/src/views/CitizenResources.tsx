import { useEffect, useState } from 'react';
import { CitizenSelect } from '../components/CitizenSelect';
import { ArrowLeft, BookOpen, Image as ImageIcon, MapPin, ArrowCounterClockwise as RotateCcw, Leaf } from '../components/PhosphorIcons';

export function CitizenPageHeader({ title, subtitle, onBack }: { title: string; subtitle: string; onBack: () => void }) {
  return <header className="space-y-4">
    <button onClick={onBack} className="citizen-page-back" aria-label="Bumalik sa dashboard"><ArrowLeft aria-hidden="true" size={19} /><span>Dashboard</span></button>
    <div><h1 tabIndex={-1} className="text-[28px] font-bold" lang="en">{title}</h1><p className="text-base text-[#46584D] mt-1">{subtitle}</p></div>
  </header>;
}

export function CitizenLearn({ onBack }: { onBack: () => void }) {
  const [category, setCategory] = useState('basics');
  return <div className="citizen-resource-page">
    <CitizenPageHeader title="Learn" subtitle="Kilalanin ang iyong kidney health." onBack={onBack} />
    <div role="tablist" aria-label="Mga paksa" className="citizen-resource-tabs">
      {[['basics', 'Kaalaman'], ['recipes', 'Recipes'], ['lifestyle', 'Lifestyle']].map(([key, label], i, tabs) =>
        <button key={key} id={`learn-tab-${key}`} role="tab" aria-selected={category === key}
          aria-controls="learn-panel" tabIndex={category === key ? 0 : -1}
          onClick={() => setCategory(key)} onKeyDown={e => {
            let next = i;
            if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
            else if (e.key === 'ArrowLeft') next = (i + tabs.length - 1) % tabs.length;
            else if (e.key === 'Home') next = 0;
            else if (e.key === 'End') next = tabs.length - 1;
            else return;
            e.preventDefault(); setCategory(tabs[next][0]);
            document.getElementById(`learn-tab-${tabs[next][0]}`)?.focus();
          }}>{label}</button>)}
    </div>
    <section id="learn-panel" role="tabpanel" aria-labelledby={`learn-tab-${category}`} tabIndex={0} className="space-y-5">
      {category === 'basics' ? <>
        <div className="flex items-center gap-2 text-[#17573A]"><BookOpen aria-hidden="true" size={20} /><h2 className="text-xl font-bold">Magsimula rito</h2></div>
        <details className="citizen-learning-topic" open><summary>Ano ang check-in?</summary><p>Mga tanong tungkol sa impormasyong ibinabahagi mo. Hindi ito blood test, urine test, o diagnosis. Hindi nito makukumpirma kung mayroon kang CKD.</p></details>
        <details className="citizen-learning-topic"><summary>Paano basahin ang isang resulta?</summary><p>Ang output ng prototype ay may limitasyon. Hindi ito kapalit ng pagsusuri ng health professional. Maaaring hindi makapagbigay ng resulta ang demo para sa ilang sagot.</p></details>
      </> : <>
        <div className="space-y-2"><h2 className="text-xl font-bold">{category === 'recipes' ? 'Kidney-friendly recipes' : 'Lifestyle resources'}</h2>
          <p className="text-base text-[#46584D]">{category === 'recipes' ? 'Inihahanda pa ang mga recipe para sa content review. Hindi lahat ng recipe ay angkop sa bawat kondisyon.' : 'Inihahanda pa ang mga gabay para sa content review.'}</p></div>
        <div className="grid grid-cols-2 gap-3">
          {(category === 'recipes' ? ['Mga almusal', 'Mga pangunahing putahe'] : ['Pagkain sa araw-araw', 'Mga pang-araw-araw na gawi']).map(title => <article key={title} className="citizen-editorial-preview">
            <div className="citizen-image-placeholder" aria-hidden="true"><ImageIcon size={25} strokeWidth={1.5} /><span>Larawan</span></div>
            <div className="p-3 space-y-2"><h3 className="font-bold text-base leading-snug">{title}</h3><p className="text-sm text-[#46584D]">Content na susuriin</p></div>
          </article>)}
        </div>
        <p className="text-sm text-[#46584D] flex items-center gap-2">{category === 'recipes' ? <Leaf aria-hidden="true" size={17} /> : <Leaf aria-hidden="true" size={17} />}Preview lamang; wala pang personalized na gabay.</p>
      </>}
    </section>
  </div>;
}

interface FacilityRecord {
  name: string;
  type: string;
  municipality: string;
  kidney_tests: string;
  verification: string;
}

export function CitizenCare({ onBack }: { onBack: () => void }) {
  const [records, setRecords] = useState<FacilityRecord[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'failed'>('loading');
  const [town, setTown] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setStatus('loading');
    // PhilHealth YAKAP-accredited hospitals and health centers (same list as the check-in result and the tablet).
    fetch('/api/risk-check/facilities', { signal: controller.signal })
      .then(async res => { if (!res.ok) throw new Error('Facilities unavailable'); return res.json(); })
      .then(data => {
        const rows = data?.facilities;
        if (!Array.isArray(rows) || rows.some(row => !row || typeof row.name !== 'string')) throw new Error('Invalid facility list');
        if (controller.signal.aborted) return;
        // Unnamed simulation rows cannot serve as a citizen facility directory.
        setRecords(rows.filter((row: FacilityRecord) => row.name.trim()));
        setStatus('ready');
      }).catch(() => { if (!controller.signal.aborted) setStatus('failed'); });
    return () => controller.abort();
  }, [attempt]);
  const towns = [...new Set(records.flatMap(row => typeof row.municipality === 'string' ? [row.municipality] : []))].sort();
  const shown = records.filter(row => !town || row.municipality === town);
  return <div className="citizen-resource-page">
    <CitizenPageHeader title="Care" subtitle="Mga ospital at health center na PhilHealth YAKAP-accredited." onBack={onBack} />
    <p className="citizen-care-note">Hindi pa verified ang listahan. Tumawag muna para kumpirmahin ang pasilidad at kung kaya nila ang blood at urine test para sa kidneys.</p>
    {status === 'ready' && towns.length > 0 && <CitizenSelect id="care-town" label="Bayan o lungsod" value={town}
      options={[{ value: '', label: 'Lahat ng nasa talaan' }, ...towns.map(name => ({ value: name, label: name.replace('City of ', '').replace(' City', '') }))]} onChange={setTown} />}
    <div aria-live="polite" aria-busy={status === 'loading'}>
      {status === 'loading' && <p className="py-5">Kinukuha ang talaan ng mga pasilidad…</p>}
      {status === 'failed' && <div className="space-y-4 py-4"><h2 className="font-bold text-xl">Hindi makuha ang talaan</h2><p>Subukan muli kapag available ang serbisyo.</p><button className="citizen-action citizen-summary-action" onClick={() => setAttempt(n => n + 1)}><RotateCcw aria-hidden="true" size={18} />Subukan muli</button></div>}
      {status === 'ready' && shown.length === 0 && <div className="py-5 space-y-2"><h2 className="font-bold text-xl">Wala pang pasilidad na maipapakita</h2><p>Kulang pa ang detalye sa talaan ng prototype. Hindi nito ibig sabihin na walang serbisyo sa inyong lugar.</p></div>}
      {status === 'ready' && <ul className="space-y-4">{shown.map((row, i) => <li key={`${row.name}-${i}`} className="citizen-facility-row">
        <MapPin aria-hidden="true" size={21} className="shrink-0 text-[#17573A]" />
        <div className="min-w-0 space-y-1"><h2 className="font-bold text-lg">{row.name}</h2>
          <p className="text-base">{row.type === 'Hospital' ? 'Ospital' : 'Health center'} · {row.municipality.replace('City of ', '').replace(' City', '')}</p>
          <p className="text-sm text-[#46584D]">Kidney tests: hindi pa alam · Hindi pa verified, tumawag muna. Address at contact: hindi pa nakumpirma.</p>
        </div>
      </li>)}</ul>}
    </div>
  </div>;
}
