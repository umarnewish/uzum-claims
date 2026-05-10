// Shared shell behaviors: mobile hamburger that toggles vendex's sidebar-open
// class. Imported by every page so the side nav is reachable on small screens.
const app = document.getElementById('app-page');
if (app) {
  // Hamburger button (vendex CSS shows it via @media max-width:768px).
  const btn = document.createElement('button');
  btn.id = 'btn-menu-toggle';
  btn.className = 'btn-menu-toggle';
  btn.setAttribute('aria-label', 'Открыть меню');
  btn.innerHTML = `
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
    </svg>`;

  // Click-away overlay
  const ov = document.createElement('div');
  ov.id = 'sidebar-overlay';
  ov.className = 'sidebar-overlay';

  app.prepend(ov);
  document.body.prepend(btn);

  const toggle = (open) => {
    const want = open === undefined ? !app.classList.contains('sidebar-open') : open;
    app.classList.toggle('sidebar-open', want);
  };
  btn.addEventListener('click', () => toggle());
  ov.addEventListener('click', () => toggle(false));

  // Auto-close after picking a sidebar link
  app.querySelectorAll('.sidebar a, .sidebar-link').forEach((a) =>
    a.addEventListener('click', () => toggle(false))
  );
}
