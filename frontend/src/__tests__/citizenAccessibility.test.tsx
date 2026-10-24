import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { CitizenView } from '../views/CitizenView';

describe('citizen accessibility baseline', () => {
  it('identifies the citizen language and region without changing the app shell', () => {
    const html = renderToStaticMarkup(<CitizenView />);
    expect(html).toContain('lang="fil"');
    expect(html).toContain('aria-label="AGAP-CKD para sa mamamayan"');
    expect(html).toContain('citizen-view');
  });
  it('renders one focusable screen heading and an announcement region', () => {
    const html = renderToStaticMarkup(<CitizenView />);
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    expect(html).toMatch(/<h1[^>]*tabindex="-1"/);
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('aria-label="Simulan ang check-in"');
  });
});
