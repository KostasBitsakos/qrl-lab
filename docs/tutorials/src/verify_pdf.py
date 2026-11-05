"""Structural PDF check; pedagogical and technical accuracy still require review."""
from pathlib import Path
import unicodedata
from pypdf import PdfReader

root = Path(__file__).resolve().parents[3]
pdf = root / 'docs/tutorials/ml_quantum_autoscaling.pdf'
reader = PdfReader(pdf)
assert len(reader.pages) == 20, len(reader.pages)
texts = [page.extract_text() for page in reader.pages]
assert all(len(text) > 400 for text in texts), 'empty or image-only content'
expected = {0: 'Ένας ελεγκτής', 5: 'Double DQN', 6: 'LSTM', 7: 'Dinos+Transfer V.2',
            10: 'DRe-SCale', 11: 'test12', 12: 'IQM', 14: 'QC1', 15: 'QC5',
            16: 'QC7', 18: 'Έλεγχος κατανόησης', 19: 'Πηγές'}
def comparable(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value)
                   if not unicodedata.category(c).startswith('M') and not c.isspace() and c != '΄')

for index, phrase in expected.items():
    assert comparable(phrase) in comparable(texts[index]), (index + 1, phrase)
assert len(reader.outline) == 19, 'section bookmarks'
links = sum(len(page.get('/Annots', [])) for page in reader.pages)
assert links >= 10, links
assert pdf.stat().st_size > 10000
print(f'PDF checks passed: {len(reader.pages)} pages, {len(reader.outline)} bookmarks, {links} links')
