import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { CitizenSelect } from '../components/CitizenSelect';
const options = [{ value: 'female', label: 'Babae' }, { value: 'male', label: 'Lalaki' }, { value: 'intersex', label: 'Intersex' }, { value: 'prefer_not_to_say', label: 'Prefer not to say' }];
describe('in-app citizen select', () => {
  it('starts empty with an accessible combobox and no native select', () => {
    const html = renderToStaticMarkup(<CitizenSelect id="sex" label="Kasarian" value="" options={options} onChange={() => {}} />);
    expect(html).toContain('role="combobox"'); expect(html).toContain('Pumili ng sagot');
    expect(html).toContain('aria-expanded="false"'); expect(html).not.toContain('<select');
  });
  it('shows an explicitly selected inclusive answer without changing its value', () => {
    const html = renderToStaticMarkup(<CitizenSelect id="sex" label="Kasarian" value="intersex" options={options} onChange={() => {}} />);
    expect(html).toContain('Intersex'); expect(html).not.toContain('Pumili ng sagot');
  });
});
