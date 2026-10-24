import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { CitizenView } from '../views/CitizenView';
import { CitizenConsent, CitizenHome } from '../views/CitizenEntry';
const noop = () => {};
describe('education-first citizen entry', () => {
  it('starts unassessed with optional education and no health form', () => {
    const html = renderToStaticMarkup(<CitizenView />);
    expect(html).toContain('Wala pang check-in');
    expect(html).toContain('aria-label="Simulan ang check-in"');
    expect(html).toContain('Learn');
    expect(html).toContain('Care');
    expect(html).toContain('Track');
    expect(html).toContain('Coming soon');
    expect(html).not.toContain('<input');
    expect(html).not.toContain('9:41');
    expect(html).not.toContain('Totals lang');
    expect(html).not.toContain('RA 10173');
    expect(html).not.toContain('Prototype');
    expect(html).not.toContain('Demo lamang');
    expect(html).not.toContain('Kathang-isip');
  });
  it('explains submission and offers a non-participation path before questions', () => {
    const html = renderToStaticMarkup(<CitizenConsent onAccept={noop} onDecline={noop} />);
    expect(html).toContain('ipapadala');
    expect(html).toContain('Kathang-isip');
    expect(html).toContain('Nauunawaan ko, magpatuloy');
    expect(html).toContain('Hindi muna');
    expect(html).not.toContain('<input');
    expect(html).not.toContain('anonymous');
  });
});

describe('dashboard summary states', () => {
  const actions = { onStart: noop, onLearn: noop, onCare: noop, onDetails: noop };
  it('shows the current scored level and no invented date or tracking measurements', () => {
    const html = renderToStaticMarkup(<CitizenHome {...actions} summary={{ risk_level: 'Medium' }} />);
    expect(html).toContain('Medium');
    expect(html).not.toContain('Wala pang check-in');
    expect(html).toContain('Hindi ito diagnosis');
    expect(html).not.toContain('Larawan');
    expect(html).not.toContain('Naipakita noong');
    expect(html).not.toContain('120/80');
  });
  it('keeps unavailable and clinician-care outputs distinct from Low', () => {
    for (const summary of [{ risk_level: 'Doctor Referral' }, { risk_level: 'unexpected' }]) {
      const html = renderToStaticMarkup(<CitizenHome {...actions} summary={summary} />);
      expect(html).not.toMatch(/>Low</);
      expect(html).not.toContain('Wala pang check-in');
    }
    const html = renderToStaticMarkup(<CitizenHome {...actions} unavailable />);
    expect(html).toContain('Hindi available');
    expect(html).not.toMatch(/>Low</);
  });
});

describe('no numeric score (PRD v3 l. 73)', () => {
  const actions = { onStart: noop, onLearn: noop, onCare: noop, onDetails: noop };
  it('shows the level in words and never a score', () => {
    for (const risk_level of ['Low', 'Medium', 'High']) {
      const html = renderToStaticMarkup(<CitizenHome {...actions} summary={{ risk_level }} />);
      expect(html).toContain(risk_level);
      expect(html).toContain('Antas:');
      expect(html).not.toContain('/100');
      expect(html).not.toMatch(/model score|numeric score|\d+\s*\/\s*100/i);
      expect(html).toContain('Hindi ito diagnosis');
    }
  });
  it('shows one next-step line after a check, without the old clutter', () => {
    const html = renderToStaticMarkup(<CitizenHome {...actions} summary={{ risk_level: 'High', next: 'Magpa-blood at urine test agad · Next kidney test: Okt 2027' }} />);
    expect(html).toContain('Next kidney test: Okt 2027');
    expect(html).toContain('Tingnan ang resulta');
    expect(html).toContain('Ulitin ang check-in');
    expect(html).not.toContain('Naipakita noong');
    expect(html).not.toContain('porsiyento');
  });
  it('gives clinician-care routes no level', () => {
    const html = renderToStaticMarkup(<CitizenHome {...actions} summary={{ risk_level: 'Doctor Referral' }} />);
    expect(html).toContain('Walang risk level');
    expect(html).not.toMatch(/>(Low|Medium|High)</);
  });
});
