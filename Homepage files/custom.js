function addLogoText() {
  const logoEl = document.querySelector('.information-widget-logo');
  if (logoEl && !logoEl.querySelector('.logo-text')) {
    const span = document.createElement('span');
    span.className = 'logo-text';
    span.textContent = 'Home Lab';
    logoEl.insertBefore(span, logoEl.firstChild);
  }
}

addLogoText();
const observer = new MutationObserver(addLogoText);
observer.observe(document.body, { childList: true, subtree: true });
