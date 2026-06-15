const docsSearch = document.getElementById('docs-search');
const docsSearchResults = document.getElementById('docs-search-results');
const docButtons = Array.from(document.querySelectorAll('.docs-tab-button'));
const docPanels = Array.from(document.querySelectorAll('.docs-tab-panel'));
const docLinks = Array.from(document.querySelectorAll('[data-doc-link]'));
function activeDocPanel() { return docPanels.find(panel => !panel.hidden); }
function jumpToDocTarget(tab, target) {
  activateDocTab(tab);
  if (target) history.replaceState(null, '', '#' + target);
  window.requestAnimationFrame(() => {
    const node = document.getElementById(target);
    if (node) {
      node.scrollIntoView({ block: 'start' });
    }
  });
}
function activateDocTab(key) {
  docButtons.forEach(button => button.classList.toggle('active', button.dataset.docTab === key));
  docPanels.forEach(panel => { panel.hidden = panel.dataset.docPanel !== key; });
  applyDocsFilter();
}
function renderDocsSearchResults(q) {
  if (!docsSearchResults) return;
  docsSearchResults.replaceChildren();
  docsSearchResults.hidden = !q;
  if (!q) return;
  function docSearchScore(link) {
    const label = (link.dataset.docLabel || link.textContent || '').toLowerCase();
    let score = 0;
    if (label === q) score += 200;
    if (label.includes(q)) score += 100;
    if (link.classList.contains('docs-heading-link')) score += 25;
    if ((link.dataset.docSearch || '').includes(q)) score += 1;
    return score;
  }
  const matches = docLinks.filter(link => (link.dataset.docSearch || '').includes(q))
    .sort((a, b) => docSearchScore(b) - docSearchScore(a))
    .slice(0, 12);
  if (!matches.length) {
    const empty = document.createElement('div');
    empty.className = 'docs-search-empty';
    empty.textContent = 'No local docs matches.';
    docsSearchResults.appendChild(empty);
    return;
  }
  matches.forEach(link => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'docs-search-result';
    button.dataset.docTab = link.dataset.docTab || '';
    button.dataset.docTarget = link.dataset.docTarget || '';
    button.textContent = link.dataset.docLabel || link.textContent || '';
    const meta = document.createElement('span');
    meta.textContent = (link.dataset.docTab || 'docs') + ' section';
    button.appendChild(meta);
    docsSearchResults.appendChild(button);
  });
}
function applyDocsFilter() {
  const panel = activeDocPanel();
  if (!panel) return;
  const q = (docsSearch.value || '').trim().toLowerCase();
  renderDocsSearchResults(q);
  Array.from(panel.querySelectorAll('[data-doc-page]')).forEach(page => {
    page.style.display = (!q || page.dataset.docPage.includes(q)) ? '' : 'none';
  });
}
docButtons.forEach(button => button.addEventListener('click', () => activateDocTab(button.dataset.docTab)));
document.addEventListener('click', event => {
  const link = event.target.closest('a[data-doc-target]');
  if (!link) return;
  event.preventDefault();
  jumpToDocTarget(link.dataset.docTab, link.dataset.docTarget);
});
if (docsSearchResults) docsSearchResults.addEventListener('click', event => {
  const button = event.target.closest('button[data-doc-target]');
  if (!button) return;
  jumpToDocTarget(button.dataset.docTab, button.dataset.docTarget);
});
if (docsSearch) docsSearch.addEventListener('input', applyDocsFilter);
if (docsSearch) docsSearch.addEventListener('keydown', event => {
  if (event.key !== 'Enter') return;
  const first = docsSearchResults ? docsSearchResults.querySelector('button[data-doc-target]') : null;
  if (first) jumpToDocTarget(first.dataset.docTab, first.dataset.docTarget);
});
const initialDocTab = (location.hash || '').replace('#doc-tab-', '');
if (initialDocTab && docButtons.some(button => button.dataset.docTab === initialDocTab)) activateDocTab(initialDocTab);
const initialDocTarget = (location.hash || '').replace('#', '');
const initialDocLink = initialDocTarget ? docLinks.find(link => link.dataset.docTarget === initialDocTarget) : null;
if (initialDocLink) activateDocTab(initialDocLink.dataset.docTab);
applyDocsFilter();
