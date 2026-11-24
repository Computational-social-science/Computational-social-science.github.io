"""Export the recorded Matthew Effect working manuscript and its public poster."""

import argparse
import csv
from datetime import datetime
import hashlib
from io import StringIO
from html import escape
from html.parser import HTMLParser
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from xml.etree import ElementTree

from markdown_it import MarkdownIt
from markdown_it.token import Token
import pymupdf
from context_cue_view import render_context_cue
from publish_pages import (
    EVIDENCE_FIGURES, EVIDENCE_FIGURE_PAGES, EXPERIMENT_FILES, PORTRAIT_PATH as PEOPLE_PORTRAIT_PATH,
    CONTEXT_CUE_MAX_BYTES, CONTEXT_CUE_PAGE, CONTEXT_CUE_VIEW_PAGE, INTERNAL, STATUS_CUE_MAX_BYTES, STATUS_CUE_PAGE,
    TESTIMONY_SCORES_PAGE,
    WINDOW_REPLAY_PAGE, WINDOW_SENSITIVITY_PAGE, WORD_BUDGET_PAGE, PeoplePortraits,
    approved_context_cue, approved_status_cue, context_cue_rows, status_cue_rows,
)


SITE = Path(__file__).resolve().parents[1]
MANUSCRIPT = 'docs/research/book/THE_SECRETS_OF_TERMS_MATTHEW_EFFECT_EN.md'
STATE = 'data/editorial/workbench/state.json'
POSTER = 'outputs/research-catalog/matthew-effect-credit-plate'
PORTRAIT_PLATE = 'assets/illustrations/fieser-portraits'
PORTRAIT_PATH = 'assets/fieser-portraits.jpg'
PUBLIC_HOSTS = {
    'books.google.com', 'doi.org', 'en.wikipedia.org', 'garfield.library.upenn.edu', 'github.com',
    'history.aip.org', 'repo.library.stonybrook.edu', 'wellcomecollection.org', 'www.jstor.org',
    'computational-social-science.github.io', 'sociology.columbia.edu', 'www.amacad.org',
    'kops.uni-konstanz.de', 'www.jci.org', 'pmc.ncbi.nlm.nih.gov',
    'www.columbia.edu', 'www.nobelprize.org', 'rpc.cfainstitute.org', 'www.asanet.org',
    'openlibrary.org', 'archive.org', 'bookworm-project.github.io', 'www.hathitrust.org',
    'cran.r-project.org', 'journals.plos.org', 'research.chalmers.se',
    'www.nationalacademies.org', 'www.federalreserve.gov', 'catalog.libraries.vsc.edu',
    'merton.org', 'www.nber.org', 'link.springer.com', 'www.nesacs.org', 'nesacs.org',
    'www.strevens.org', 'epub.ub.uni-muenchen.de', 'www.orgsyn.org', 'www.sciencehistory.org',
    'eusp.org', 'c250.columbia.edu', 'hollisarchives.lib.harvard.edu', 'digital.sciencehistory.org',
}
PUBLIC_SOURCE_URLS = {
    'https://huggingface.co/OpenSciLM/OpenScholar_Retriever/tree/ef4f3120d33b3ca57e12fce2b369f5982a7bb929',
    'https://huggingface.co/OpenSciLM/OpenScholar_Reranker/tree/f371d9d9a5c47d5b89dfa130d8d6fa303f27126e',
    'https://static1.squarespace.com/static/5877ca6986e6c00f05f58f84/t/60d3564b307f7864ab0773dd/'
    '1624462927039/part-2-the-science-of-collaboration.pdf#page=62',
    'https://fever.ai/2018/task.html#scoring',
    'https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems-2/',
    'https://aclanthology.org/2026.eacl-long.303/',
    'https://aclanthology.org/2026.nllp-1.22/',
    'https://aclanthology.org/2026.findings-emnlp.343/',
}
LOCAL_LINKS = {
    'index.html', 'style.css', 'reader.css',
    'assets/matthew-effect-poster.pdf', 'assets/matthew-effect-poster.svg', PORTRAIT_PATH,
    CONTEXT_CUE_PAGE, CONTEXT_CUE_VIEW_PAGE,
}
MANUSCRIPT_FIGURES = {
    f'../../../outputs/matthew-matilda/{name}.svg': f'matthew-matilda/{name}.svg'
    for name in ('english-name-usage', 'testimony-pairs')
}
CHART_VIEWS = {
    'matthew-matilda/english-name-usage.svg': ('matthew-matilda/name-usage-view.html',
                                              'Explore annual name frequencies', 'name-usage'),
    'matthew-matilda/testimony-pairs.svg': ('matthew-matilda/testimony-pairs-view.html',
                                           'Inspect each pair of summary assessments', 'testimony-pairs'),
}
POSTER_FIGURE = """<figure class="reader-figure" aria-labelledby="poster-caption">
  <a href="assets/matthew-effect-poster.svg" target="_blank" rel="noopener"
     aria-label="Open the scientific poster at full A4 size in a new tab">
    <img src="assets/matthew-effect-poster.svg" width="420" height="594" loading="lazy"
         alt="Portraits of Robert K. Merton and Harriet Zuckerman beside a balance tipping toward Merton.">
  </a>
  <figcaption id="poster-caption">The balance illustrates the influence of prior standing on scientific recognition. The portraits identify the two researchers whose roles this chapter traces. Their respective shares of credit have not been measured.</figcaption>
</figure>
"""


def digest(content):
    return hashlib.sha256(content).hexdigest()


def source(root, name, limit):
    file = (root / name).resolve(strict=True)
    if not file.is_relative_to(root):
        raise ValueError(f'Source is outside Horisma: {name}')
    with file.open('rb') as stream:
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError(f'Source size is invalid: {name}')
    return raw


def recorded_manuscript(root):
    manuscript = source(root, MANUSCRIPT, 1_048_576)
    raw_state = source(root, STATE, 32_000_000)
    state = json.loads(raw_state)
    records = state['records']
    revision = records['book:order'][-1]
    units = [records[ident][-1]['data'] for ident in revision['data']['unit_ids']]
    projection = ''.join(
        unit['text'] + (unit['separator'] or ('\n\n' if index < len(units) - 1 else ''))
        for index, unit in enumerate(units)
    ).encode()
    if (state['pending_projection'] is not None or state.get('native_handoff')
            or manuscript != projection or digest(manuscript) != state['projection_hash']):
        raise ValueError('The saved manuscript does not match the recorded editorial projection')
    return manuscript, revision, raw_state


def recorded_poster(root, manuscript_hash):
    raw_receipt = source(root, POSTER + '.json', 4096)
    receipt = json.loads(raw_receipt)
    if receipt['manuscript_sha256'] != manuscript_hash:
        raise ValueError('The poster receipt refers to a different manuscript revision')
    result = {}
    for extension in ('pdf', 'svg'):
        raw = source(root, f'{POSTER}.{extension}', 12_000_000)
        if digest(raw) != receipt[f'{extension}_sha256']:
            raise ValueError(f'The poster {extension.upper()} fails its receipt hash')
        result[extension] = raw
    with pymupdf.open(stream=result['pdf'], filetype='pdf') as document:
        if len(document) != 1 or any(
            abs(actual - expected * 72 / 25.4) > .1
            for actual, expected in zip((document[0].rect.width, document[0].rect.height), (210, 297), strict=True)
        ):
            raise ValueError('The poster is not a one-page portrait A4 PDF')
    svg = ElementTree.fromstring(result['svg'])
    if (svg.tag != '{http://www.w3.org/2000/svg}svg'
            or (svg.get('width'), svg.get('height')) != ('210mm', '297mm')):
        raise ValueError('The poster SVG does not declare the expected A4 canvas')
    for node in svg.iter():
        if node.tag.rsplit('}', 1)[-1].lower() in {'script', 'foreignobject', 'style'}:
            raise ValueError('An active element appears in the poster SVG')
        for key, value in node.attrib.items():
            name = key.rsplit('}', 1)[-1].lower()
            if (name.startswith('on') or name in {'href', 'src'}
                    and not value.startswith(('#', 'data:image/png;base64,', 'data:image/jpeg;base64,'))):
                raise ValueError('An active or external reference appears in the poster SVG')
    return result, raw_receipt


def recorded_portraits(root):
    receipt = json.loads(source(root, PORTRAIT_PLATE + '.json', 262_144))
    plate = source(root, PORTRAIT_PLATE + '.jpg', 12_000_000)
    if not plate.startswith(b'\xff\xd8\xff') or digest(plate) != receipt['sha256']:
        raise ValueError('The portrait plate differs from its recorded JPEG')
    return {PORTRAIT_PATH: plate}


def recorded_people(root):
    directory = 'outputs/people/'
    receipt = json.loads(source(root, directory + 'edition.json', 262_144))['artifacts']
    page = source(root, directory + 'people.html', 1_048_576)
    paths = PeoplePortraits(page.decode('utf-8')).paths | {'people.html'}
    if set(receipt) != paths:
        raise ValueError('The people edition differs from the approved list of public files')
    files = {}
    for name in sorted(paths):
        raw = page if name == 'people.html' else source(root, directory + name, 12_000_000)
        if digest(raw) != receipt[name]['sha256']:
            raise ValueError(f'The people edition failed its receipt check: {name}')
        if name.endswith('.webp') and not (raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'):
            raise ValueError(f'Expected a WebP portrait: {name}')
        files[name] = raw
    PublicMarkup(page.decode('utf-8'), local_links=LOCAL_LINKS | paths | {'manuscript.html'})
    return files


def public_source_notes(notes):
    paragraph = re.compile(r'(?m)^([1-9]\d*)\. +([^\n]+)')
    entries = {}
    for match in paragraph.finditer(notes):
        number = int(match[1])
        if number in entries:
            raise ValueError(f'Duplicate manuscript source note: {number}')
        text = match[2]
        text = re.sub(r'; supplied PDF index \d+', '', text)
        text = re.sub(r'; current case node `[^`]+`', '', text)
        text = re.sub(r' The empirical passage is current case node .*?\.(?=\s|$)', '', text)
        text = re.sub(r' Event records `[^`]+`.*?\.(?=\s|$)', '', text)
        text = re.sub(r', PDF page \d+ \(zero-based index \d+\)', '', text)
        if '131st AAAS Annual Meeting Montreal, Canada' in text and '436–439' in text:
            text += ' [Read the October notice](https://www.jstor.org/stable/1714302).'
        if '131st AAAS Annual Meeting.' in text and '1331–1369' in text:
            text += ' [Read the December programme](https://doi.org/10.1126/science.146.3649.1331).'
        entries[number] = text
    remaining = paragraph.sub('', notes).strip()
    if remaining and not remaining.startswith('The source/report conclusions above are a research draft'):
        raise ValueError('Unrecognized text outside the manuscript source notes')
    if not entries:
        raise ValueError('No numbered manuscript source notes')
    return entries


def testimony_scores(root, receipt, charts):
    trial = 'data/research/replication/ex04-review-scope/origin-testimony/'

    def bound_input(filename):
        path = trial + filename
        raw = source(root, path, 262144)
        if digest(raw) != receipt['recipe'].get(path):
            raise ValueError(f'Unverified testimony figure input: {filename}')
        return raw

    sources = bound_input('sources.json')
    for passage in json.loads(sources)['sources']:
        link = urlsplit(passage['url'])
        if link.scheme != 'https' or link.netloc not in PUBLIC_HOSTS:
            raise ValueError('Unapproved testimony source URL')
    return charts.testimony_csv(bound_input('scores.json'), sources, receipt['pairs'])


def word_budget_scores(root):
    directory = 'data/research/replication/ex04-review-scope/origin-testimony/word-budget/'
    seal = json.loads(source(root, directory + 'seal.json', 32768))
    if seal['model'] != 'gpt-6-luna' or not seal['files'] or any(
        digest(source(root, path, 262144)) != expected for path, expected in seal['files'].items()
    ):
        raise ValueError('Word-budget trial inputs differ from the frozen design')
    results = json.loads(source(root, directory + 'results.json', 16384))
    fields = ('block', 'budget_words', 'delivered', 'scientific_elite', 'interviewing_an_ultra_elite',
              'both_titles', 'word_count', 'within_limit')
    rows = results['rows']
    design = [(block, budget) for block in range(1, 5) for budget in (65, 100)]
    if (results['assigned_per_budget'] != 4
            or [(row['block'], row['budget_words']) for row in rows] != design
            or sorted((row['block'], row['budget']) for row in seal['prompts']) != design):
        raise ValueError('Word-budget rows do not cover the assigned pairs')
    for row in rows:
        if set(row) != set(fields) or any(type(row[key]) is not int or row[key] not in (0, 1)
                                        for key in fields[2:6]):
            raise ValueError('Word-budget rows do not match the public scoring schema')
        count, budget = row['word_count'], row['budget_words']
        if (row['both_titles'] != row['scientific_elite'] * row['interviewing_an_ultra_elite']
                or type(count) is not int or count < 0
                or (row['delivered'] and (count == 0 or type(row['within_limit']) is not int
                                         or row['within_limit'] != int(count <= budget)))
                or (not row['delivered'] and (count or row['scientific_elite'] or row['interviewing_an_ultra_elite']
                                              or row['within_limit'] is not None))):
            raise ValueError('Inconsistent word-budget score')
    buffer = StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    data = source(root, directory + 'word-budget-scores.csv', 8192)
    if data != buffer.getvalue().encode():
        raise ValueError('Word-budget CSV differs from the scored trial')
    return data


def status_cue_scores(root):
    directory = 'data/research/replication/ex04-review-scope/status-cue/'

    def read(name, limit=32_768):
        return source(root, directory + name, limit)

    seal = read('seal.json')
    frozen = json.loads(seal)['inputs']
    if (json.loads(read('attempt.json'))['seal_sha256'] != digest(seal)
            or frozen['model'] != 'gpt-6-luna' or not frozen['files']
            or any(digest(source(root, path, 262_144)) != expected for path, expected in frozen['files'].items())):
        raise ValueError('Status-cue inputs differ from the frozen attempt')

    data = read(Path(STATUS_CUE_PAGE).name, STATUS_CUE_MAX_BYTES)
    rows = status_cue_rows(data)
    scores = json.loads(read('scores.json'))
    assessment = read('assessment.json')
    if scores['public_csv_sha256'] != digest(data) or scores['assessment_sha256'] != digest(assessment):
        raise ValueError('Status-cue scores or assessment differ from the scoring receipt')

    ratings = json.loads(assessment)['scores']
    key = json.loads(read('key.json'))
    records = [json.loads(line) for line in read('runs.jsonl', 262_144).splitlines()]
    if len(records) != len(rows) or sorted(key.values()) != list(range(len(rows))):
        raise ValueError('Status-cue journal or key does not cover the assigned runs')
    labels = {index: ident for ident, index in key.items()}
    if set(ratings) != {labels[i] for i, run in enumerate(records) if run['state'] == 'DELIVERED'}:
        raise ValueError('Status-cue assessment does not cover exactly the delivered runs')
    order = ('neutral', 'correct_cued', 'wrong_cued')
    assigned = {}
    for i, (slot, run) in enumerate(zip(frozen['assignments'], records, strict=True)):
        if (run['replicate'], run['source_id'], run['arm'], run['prompt_sha256']) != (
            i, slot['vignette'], slot['condition'], digest(slot['prompt'].encode()),
        ) or run['prompt_sha256'] != slot['prompt_sha256']:
            raise ValueError('Status-cue journal does not match the assigned prompts')
        assigned[slot['block'], slot['condition']] = (slot, run, labels[i])
    if [(row['block'], row['condition']) for row in rows] != sorted(
        assigned, key=lambda item: (item[0], order.index(item[1])),
    ):
        raise ValueError('Status-cue CSV does not match the assigned blocks')

    for row in rows:
        slot, run, ident = assigned[row['block'], row['condition']]
        if (any(row[field] != slot[field] for field in ('vignette', 'target_alias', 'prompt'))
                or row['delivery'] != run['state']):
            raise ValueError('Status-cue assignment or delivery differs from the retained run')
        if row['delivery'] == 'TECHNICAL_FAILURE':
            continue
        answer = run['text']
        audit = run['audit']
        if (audit['model'] != frozen['model'] or audit['prompt_sha256'] != slot['prompt_sha256']
                or audit['answer_sha256'] != digest(answer.encode()) or row['answer'] != answer):
            raise ValueError('Status-cue answer differs from the retained audit')
        actor = ratings[ident]['actor']
        category = {'A': 'SOLE_FOIL', 'B': 'SOLE_FOIL', slot['target_alias']: 'SOLE_CORRECT',
                    'BOTH': 'JOINT', 'UNRESOLVED': 'UNRESOLVED', 'ABSENT': 'ABSENT'}.get(actor)
        if category != row['response_category']:
            raise ValueError('Status-cue category differs from the independently assessed actor')
    approved_status_cue(data)
    return data


def context_cue_scores(root):
    directory = 'data/research/replication/ex04-review-scope/context-cue/'

    def read(name, limit=131_072):
        return source(root, directory + name, limit)

    data = read(Path(CONTEXT_CUE_PAGE).name, CONTEXT_CUE_MAX_BYTES)
    rows = context_cue_rows(data)
    approved_context_cue(data)
    assessment = read('assessment.json')
    receipt = json.loads(read('scores.json'))
    if receipt['public_csv_sha256'] != digest(data) or receipt['assessment_sha256'] != digest(assessment):
        raise ValueError('Context-cue CSV or assessment does not match its scoring receipt')
    seal = read('seal.json')
    frozen = json.loads(seal)['inputs']
    if (json.loads(read('attempt.json'))['seal_sha256'] != digest(seal)
            or frozen['model'] != 'gpt-6-luna' or not frozen['files']
            or any(digest(source(root, path, 262_144)) != expected for path, expected in frozen['files'].items())):
        raise ValueError('Context-cue inputs differ from the frozen attempt')
    records = [json.loads(line) for line in read('runs.jsonl', 262_144).splitlines()]
    by_id = {run['source_id']: run for run in records}
    delivered = {ident for ident, run in by_id.items() if run['state'] == 'DELIVERED'}
    mask_key = json.loads(read('mask-key.json'))
    ratings = json.loads(assessment)
    if (len(records) != len(rows) or set(by_id) != {r['slot_id'] for r in rows}
            or len(mask_key) != len(delivered) or set(mask_key.values()) != delivered
            or set(ratings['scores']) != set(mask_key)
            or ratings['packet_sha256'] != digest(read('masked.json'))):
        raise ValueError('Context-cue journal or grading does not cover the assigned and delivered slots')
    labels = {ident: label for label, ident in mask_key.items()}
    threads, ambient = set(), set()
    for row, slot in zip(rows, frozen['slots'], strict=True):
        run = by_id[row['slot_id']]
        prompt_hash = digest(row['prompt'].encode())
        if (any(row[field] != slot[field] for field in (
                'slot_id', 'block', 'vignette', 'evidence', 'cue', 'marked_actor', 'gold_actor', 'prompt',
             )) or row['delivery'] != run['state'] or run['arm'] != slot['cue']
                or run['replicate'] != slot['position']
                or prompt_hash != slot['prompt_sha256'] or prompt_hash != run['prompt_sha256']):
            raise ValueError('Context-cue assignment or delivery differs from the retained run')
        thread = run.get('run', {}).get('thread_id')
        if thread:
            if thread in threads:
                raise ValueError('A context-cue native thread was reused')
            threads.add(thread)
        if row['delivery'] == 'TECHNICAL_FAILURE':
            if not run.get('error'):
                raise ValueError('A context-cue technical failure lacks a retained reason')
            continue
        audit = run['audit']
        if (not thread or row['answer'] != run['text'] or audit['model'] != frozen['model']
                or audit['prompt_sha256'] != prompt_hash or audit['answer_sha256'] != digest(row['answer'].encode())
                or any("call" in kind or ("tool" in kind and kind != "additional_tools")
                       for kind in audit['response_item_types'])):
            raise ValueError('Context-cue answer or native verification differs from the retained audit')
        ambient.add(audit['ambient_sha256'])
        grade = ratings['scores'][labels[row['slot_id']]]
        if (row['action_status'] != grade['action_status'] or row['attribution'] != grade['attribution']
                or row['endorsed_actors'] != '+'.join(sorted(grade['endorsed_actors']))
                or row['explicit_uncertainty'] != str(int(grade['explicit_uncertainty']))):
            raise ValueError('Context-cue grading fields differ from the independent assessment')
    if len(ambient) > 1:
        raise ValueError('Context-cue sessions have inconsistent native ambient instructions')
    return data


def window_sensitivity(root, annual_path, annual):
    directory = 'data/research/replication/matthew-matilda/window-sensitivity/'
    script_path = 'scripts/research_matthew_window_sensitivity.py'
    receipt = json.loads(source(root, directory + 'receipt.json', 8192))
    data = source(root, directory + 'widths.csv', 32768)
    script = source(root, script_path, 16384)
    if (receipt['execution'] != 'PASS' or receipt['annual_sha256'] != digest(annual)
            or receipt['table_sha256'] != digest(data) or receipt['script_sha256'] != digest(script)
            or INTERNAL.search(script)):
        raise ValueError('The window analysis differs from its verified inputs or uses a private path')
    reader = csv.DictReader(StringIO(data.decode('utf-8')))
    rows = list(reader)
    if (receipt['rows'] != 15 or receipt['columns'] != 21 or len(reader.fieldnames or ()) != 21
            or [int(row['width_years']) for row in rows] != list(range(1, 16))):
        raise ValueError('Window sensitivity must show the complete 1–15-year sweep')
    replay = subprocess.run((sys.executable, '-I', '-B', str(root / script_path), str(root / annual_path)),
                            capture_output=True, timeout=10, check=True)
    if (replay.stdout != data or replay.stderr or source(root, script_path, 16384) != script
            or source(root, annual_path, 1_000_000) != annual):
        raise ValueError('Independent offline window replay differs from the verified table')
    return {WINDOW_SENSITIVITY_PAGE: data, WINDOW_REPLAY_PAGE: script}


def evidence_figures(root, directory, charts):
    result = {}
    for stem, files in EVIDENCE_FIGURES.items():
        receipt = json.loads(source(root, f'{directory}{stem}-figure.json', 262144))
        if not receipt['recipe']:
            raise ValueError(f'{stem} figure receipt has no input hashes')
        for name, expected in receipt['recipe'].items():
            if digest(source(root, name, 12_000_000)) != expected:
                raise ValueError(f'{stem} figure input has changed: {name}')
        for name in files:
            raw = source(root, directory + name, 12_000_000)
            if digest(raw) != receipt['artifacts'][name]['sha256']:
                raise ValueError(f'{stem} figure failed its receipt check: {name}')
            result[f'matthew-matilda/{name}'] = raw
        if stem == 'testimony-pairs':
            result[TESTIMONY_SCORES_PAGE] = testimony_scores(root, receipt, charts)
    return result


def experiment_figures(root, charts):
    directory = 'outputs/matthew-matilda/'
    receipt = json.loads(source(root, directory + 'figure-verification.json', 262144))
    for name, expected in receipt['recipe'].items():
        if digest(source(root, name, 12_000_000)) != expected:
            raise ValueError(f'Experiment inputs have changed since the figures were produced: {name}')
    result = {}
    for name in EXPERIMENT_FILES:
        raw = source(root, directory + name, 12_000_000)
        if digest(raw) != receipt['artifacts'][name]['sha256']:
            raise ValueError(f'Experiment figure failed its receipt check: {name}')
        if name.endswith('.html'):
            raw = raw.replace(b'\r\n', b'\n')
        if name == 'explorer.html':
            raw = raw.replace(b'href="REPORT.md"', b'href="report.html"')
        result[f'matthew-matilda/{name}'] = raw
    annual_path = 'data/research/replication/matthew-matilda/annual.csv'
    annual = source(root, annual_path, 1_000_000)
    if digest(annual) != receipt['recipe'][annual_path]:
        raise ValueError('Annual frequencies do not match the illustrated data')
    result['matthew-matilda/annual.csv'] = annual
    result[WORD_BUDGET_PAGE] = word_budget_scores(root)
    result[STATUS_CUE_PAGE] = status_cue_scores(root)
    context_data = context_cue_scores(root)
    result[CONTEXT_CUE_PAGE] = context_data
    context_view = render_context_cue(context_data).encode('utf-8')
    PublicMarkup(context_view.decode('utf-8'), local_links={
        '../style.css', '../reader.css', 'context-cue-scores.csv',
        '../manuscript.html#when-can-context-identify-the-researcher',
    })
    result[CONTEXT_CUE_VIEW_PAGE] = context_view
    result.update(window_sensitivity(root, annual_path, annual))
    report = source(root, directory + 'REPORT.md', 262144).decode('utf-8')
    result['matthew-matilda/report.html'] = public_experiment_report(report)
    query_path = 'data/research/replication/scientist-fame/query-annual.csv'
    queries = source(root, query_path, 1_000_000)
    if digest(queries) != receipt['recipe'][query_path]:
        raise ValueError('Alias observations differ from those verified in the explorer')
    result['matthew-matilda/name-queries.csv'] = queries.replace(b'\r\n', b'\n')
    panel = json.loads(source(root, 'data/research/replication/fame-witness-panel/panel.v1.json', 524288))
    columns = ('year', 'person', 'state', 'words', 'declared_pages', 'unreadable_pages',
               'u_resolved_count', 'u_candidate_count', 'u_per_billion_lower', 'u_per_billion_upper',
               'b_qualified_works', 'b_possible_works', 'b_readable_works', 'b_coverage_lower', 'b_coverage_upper')
    panel_csv = StringIO(newline='')
    writer = csv.DictWriter(panel_csv, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    for row in panel['annual']:
        writer.writerow({key: row[key] for key in columns})
    result['matthew-matilda/witness-panel.csv'] = panel_csv.getvalue().encode()
    result.update(pilot_tables(root))
    result.update(evidence_figures(root, directory, charts))
    interactive = charts.render_charts(annual, result[TESTIMONY_SCORES_PAGE])
    if {f'matthew-matilda/{name}' for name in interactive} != {view[0] for view in CHART_VIEWS.values()}:
        raise ValueError('Unexpected interactive manuscript outputs')
    result.update({f'matthew-matilda/{name}': raw for name, raw in interactive.items()})
    protocol = source(root, 'docs/research/SCIENTIFIC_FAME_PROTOCOL_EN.md', 262144).decode('utf-8')
    result['matthew-matilda/method.html'] = experiment_reader(
        protocol, 'Scientific visibility and historical credit · Measurement protocol')
    framework = source(root, 'docs/research/HISTORICAL_FAME_VALIDATION_EN.md', 262144).decode('utf-8')
    decision = json.loads(source(root, 'data/research/replication/fame-validation/gates.json', 262144))
    contract = source(root, 'spec/extensions/scientific_fame_validation.json', 262144)
    if (decision['spec']['sha256'] != digest(contract) or
            set(decision['gates']) != set(json.loads(contract)['gates']) or len(decision['gates']) != 6):
        raise ValueError('The six scientific decisions differ from the reviewed contract')
    cohorts = decision['gates']['entity']['metrics']['paired_challenges']
    for cohort, label in (('institutions', 'Institutional sources'), ('books', 'Book excerpts')):
        methods = cohorts[cohort]['methods']
        cells = [f"{m['tp']} / {m['fp']} / {m['fn']} · {m['f1']:.3f}" for m in (methods[k] for k in ('M0', 'M1', 'M2'))]
        if not any(row.startswith('| ' + label) and row.endswith(' | '.join(cells) + ' |')
                   for row in framework.splitlines()):
            raise ValueError(f'Published {label} table differs from its replayed gate evidence')
    diagnostic = decision['gates']['entity']['metrics']['post_unblinding_replay']
    for cohort, label in (('institutional', 'institutional'), ('book-transfer', 'book')):
        m = diagnostic[cohort]
        finding = f"{m['tp']} correct, {m['fp']} false and {m['fn']} missed (F1 {m['f1']:.3f})"
        if f'The {label} result became {finding}' not in framework:
            raise ValueError(f'Published {label} diagnostic differs from its replayed counts')
    status = ['## Matthew Effect evidence', '', f"Highest supported stage: **{decision['stage']['highest_qualified']}**. "
              + decision['operational']['scope'] + '.', '', '| Dimension | Current decision | Evidence |',
              '|---|---|---|']
    for key, gate in decision['gates'].items():
        status.append(f"| {key.capitalize()} | {gate['state'].capitalize()} | {gate['reason']} |")
    result['historical-fame.html'] = experiment_reader(
        framework + '\n' + '\n'.join(status) + '\n', 'Validating historical fame', independent=True)
    return result


def pilot_tables(root):
    directory = 'data/research/replication/fame-validation/'
    sample = source(root, directory + 'frame/sample.json', 4_000_000)
    access = json.loads(source(root, directory + 'access/results.json', 4_000_000))
    checked = json.loads(source(root, directory + 'results.json', 524288))
    if digest(sample) != access['sample_sha256'] or digest(sample) != checked['book_feasibility']['original_sample_sha256']:
        raise ValueError('The catalog sample and access audit refer to different editions')
    coverage = StringIO(newline='')
    writer = csv.writer(coverage, lineterminator='\n')
    writer.writerow(('catalog_year', 'work_id', 'edition_id', 'LCC_classes', 'index_inclusion_probability',
                     'archive_check', 'work_year_review', 'raw_scan_word_tokens', 'registered_search_candidates'))
    for frame, row in zip(json.loads(sample)['rows'], access['rows'], strict=True):
        if (frame['work_id'], frame['edition_id']) != (row['work_id'], row['edition_id']):
            raise ValueError('The accessed edition does not match its catalog row')
        writer.writerow((frame['year'], frame['work_id'], frame['edition_id'], ' '.join(frame['discipline']),
                         frame['inclusion_probability'], row['status'],
                         checked['edition_review']['work_year_decisions'].get(frame['edition_id']), row['word_count'],
                         None if row['matches'] is None else sum(row['matches'].values())))
    subcorpora = source(root, directory + 'english-subcorpora.json', 131072)
    if digest(subcorpora) != checked['subcorpus_source_sha256']:
        raise ValueError('The English subcorpus receipt changed')
    series = StringIO(newline='')
    writer = csv.writer(series, lineterminator='\n')
    writer.writerow(('corpus', 'query', 'year', 'status', 'annual_fraction'))
    for corpus, record in json.loads(subcorpora).items():
        if digest(record['raw'].encode()) != record['response_sha256']:
            raise ValueError('The raw Google response has changed')
        values = {item['ngram']: item['timeseries'] for item in json.loads(record['raw'])}
        for query in checked['name_frequency'][corpus]['1959-1963']:
            for year in range(1959, 1974):
                value = values[query][year-1959] if query in values else None
                status = 'missing_series' if value is None else 'returned_zero' if value == 0 else 'returned_positive'
                writer.writerow((corpus, query, year, status, value))
    readable = source(root, directory + 'readable/coverage.csv', 524288)
    review = json.loads(source(root, directory + 'readable/summary.json', 524288))
    if digest(readable) != review['coverage_csv_sha256']:
        raise ValueError('The readable-edition table differs from the reviewed observations')
    return {'matthew-matilda/book-access.csv': coverage.getvalue().encode(),
            'matthew-matilda/readable-editions.csv': readable,
            'matthew-matilda/english-subcorpora.csv': series.getvalue().encode()}


def public_experiment_report(report):
    # This reader edition covers the paired-name experiment. Other nominations
    # and pointers into the private working archive belong to the local report.
    body, separator, _ = report.partition('## What the other three experiments recover')
    if not separator or not body.startswith('# Can the name histories'):
        raise ValueError('Review the changed experiment report structure before export')
    body = re.sub(r'\[Annual observations\]\([^)]*\)', '[Annual observations (CSV)](annual.csv)', body)
    body = re.sub(r'\[[^\]\n]+\]\((?:<\.\./[^>\n]+>|\.\./[^)\n]+)\)', '', body)
    body = re.sub(r'(?:[ \t]*·[ \t]*)+(?=\n|$)', '', body)
    body = re.sub(r'(?m)^[ \t]*·[ \t]*', '', body)
    body = re.sub(r' · (?: · )+', ' · ', body)
    return experiment_reader(body, 'Name histories and research credit · Replication report')


def experiment_reader(body, title, *, independent=False):
    if independent:
        for link in EVIDENCE_FIGURE_PAGES:
            body = body.replace(f'](../../outputs/{link})', f']({link})')
    markdown = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = markdown.parse(body)
    if independent:
        headings = set()
        for index, token in enumerate(tokens):
            if token.type == 'heading_open' and token.tag in ('h2', 'h3'):
                ident = re.sub(r'[^a-z0-9]+', '-', tokens[index + 1].content.lower()).strip('-')
                if not ident or ident in headings:
                    raise ValueError('Independent methods sections need distinct linkable headings')
                headings.add(ident)
                token.attrSet('id', ident)
    article = markdown.renderer.render(tokens, markdown.options, {})
    article = article.replace('<table>', '<div class="table-wrap" tabindex="0"><table>').replace('</table>', '</table></div>')
    assets = '' if independent else '../'
    navigation = ('<a href="manuscript.html">Matthew Effect manuscript</a> · '
                  '<a href="matthew-matilda/method.html">Case measurement protocol</a> · '
                  '<a href="matthew-matilda/readable-editions.csv" download>Edition-level observations</a>'
                  if independent else '''<a href="../manuscript.html">Working manuscript</a>
 · <a href="report.html">Replication report</a> · <a href="method.html">Measurement protocol</a>
 · <a href="../historical-fame.html">Scientific validation</a>
 · <a href="explorer.html">Data explorer</a> · <a href="annual.csv" download>Annual name data</a>
 · <a href="name-rules.html">Compare name rules</a>
 · <a href="name-queries.csv" download>Alias queries</a> · <a href="witness-panel.csv" download>Sampled-page results</a>''')
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="{assets}style.css"><link rel="stylesheet" href="{assets}reader.css"></head>
<body><main class="shell reader replication-report"><nav aria-label="Research outputs">{navigation}</nav>
<article class="reader-text">{article}</article></main></body></html>"""
    PublicMarkup(page, local_links={'../reader.css', '../style.css', '../manuscript.html', '../historical-fame.html',
                                    'style.css', 'reader.css', 'manuscript.html', 'matthew-matilda/method.html',
                                    'matthew-matilda/readable-editions.csv',
                                    'explorer.html', 'figures-a4.pdf', 'annual.csv', 'report.html', 'method.html',
                                    'name-queries.csv', 'witness-panel.csv', 'name-rules.html', *EVIDENCE_FIGURE_PAGES})
    return page.encode('utf-8')


class PublicMarkup(HTMLParser):
    """Keep local links limited to the static portfolio, plus approved public sites."""

    def __init__(self, markup, local_links=LOCAL_LINKS, public_hosts=PUBLIC_HOSTS):
        super().__init__()
        self.local_links = local_links
        self.public_hosts = public_hosts
        self.anchors = set()
        self.targets = set()
        self.feed(markup)
        if missing := self.targets - self.anchors:
            raise ValueError(f'Missing anchors in the public reader: {sorted(missing)}')

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == 'id':
                if value in self.anchors:
                    raise ValueError(f'Duplicate reader anchor: {value}')
                self.anchors.add(value)
            if key not in {'href', 'src'}:
                continue
            if value in self.local_links:
                continue
            if value.startswith('#'):
                self.targets.add(value[1:])
                continue
            if tag == 'a' and key == 'href' and value in PUBLIC_SOURCE_URLS:
                continue
            url = urlsplit(value)
            if url.scheme != 'https' or url.netloc not in self.public_hosts:
                raise ValueError(f'An unapproved link appears in the public reader: {value}')


def contents_links(headings):
    sections = []
    for level, ident, title in headings:
        link = f'<a href="#{ident}">{escape(title)}</a>'
        if level == 'h3' and sections:
            sections[-1][1].append(link)
        else:
            sections.append((link, []))
    items = []
    for link, children in sections:
        sublist = '<ul>' + ''.join(f'<li>{child}</li>' for child in children) + '</ul>' if children else ''
        items.append(f'<li>{link}{sublist}</li>')
    items.append('<li><a href="#sources">Sources and evidence notes</a></li>')
    return '<ul>' + '\n'.join(items) + '</ul>'


def manuscript_caption(tokens, index, kind):
    if index + 2 >= len(tokens) or tokens[index].type != 'paragraph_open':
        return None
    inline = tokens[index + 1]
    if kind == 'Portraits' and inline.content.startswith('**Portraits.'):
        return 'fieser-portraits-caption', inline.children
    match = re.match(rf'^\*\*{kind} ([1-9]\d*)\.', inline.content)
    if match:
        return f'{kind.lower()}-{match[1]}-caption', inline.children


def render_person_card(markdown, tokens, index, portraits):
    heading = tokens[index]
    if heading.type != 'heading_open' or heading.tag != 'h4':
        return None
    blocks = tokens[index + 3:index + 15]
    if len(blocks) < 3 or blocks[0].type != 'paragraph_open':
        return None
    images = blocks[1].children or []
    prefix = '../../../outputs/people/'
    if (len(images) != 1 or images[0].type != 'image'
            or not (images[0].attrGet('src') or '').startswith(prefix)):
        return None
    image = images[0]
    path = image.attrGet('src').removeprefix(prefix)
    title = tokens[index + 1].content
    if not PEOPLE_PORTRAIT_PATH.fullmatch(path) or path not in portraits:
        raise ValueError(f'Scientist card portrait fails the people edition receipt: {title}')
    ident = Path(path).stem
    heading_id = heading.attrGet('id')
    if ident == heading_id:
        heading_id = f'{ident}-name'
    paragraphs = ('paragraph_open', 'inline', 'paragraph_close')
    if tuple(token.type for token in blocks) != paragraphs * 4 or not image.content.strip():
        raise ValueError(f'Scientist card must have a portrait and three field paragraphs: {ident}')
    fields = []
    for position, label in zip((4, 7, 10), ('Identity', 'Contribution', 'Sources'), strict=True):
        content = blocks[position].content
        prefix = f'**{label}.** '
        if not content.startswith(prefix) or not content[len(prefix):].strip():
            raise ValueError(f'Scientist card is missing {label.lower()}: {ident}')
        raw = content[len(prefix):]
        if label == 'Sources' and not any(t.type == 'link_open' for t in blocks[position].children):
            raise ValueError(f'Scientist card requires a source link: {ident}')
        fields.append(f'<div class="scientist-field"><dt>{label}</dt>'
                      f'<dd>{markdown.renderInline(raw)}</dd></div>')
    image.attrSet('src', path)
    image.attrSet('loading', 'lazy')
    image_markup = markdown.renderer.renderInline(images, markdown.options, {})
    html = (f'<article class="scientist-card" id="{ident}" aria-labelledby="{heading_id}">'
            f'<h4 id="{heading_id}">{escape(title)}</h4>{image_markup}'
            f'<dl>{"".join(fields)}</dl></article>\n')
    return html, index + 15


def render_manuscript_article(markdown, tokens, portraits):
    article = []
    targets = set()
    for index, token in enumerate(tokens):
        if token.type == 'paragraph_open':
            caption = manuscript_caption(tokens, index, 'Figure') or manuscript_caption(tokens, index, 'Table')
            if caption:
                targets.add(caption[0].removesuffix('-caption'))
    def append_markup(content):
        html = Token('html_block', '', 0)
        html.content = content
        article.append(html)

    index = 0
    cards_open = False
    while index < len(tokens):
        card = render_person_card(markdown, tokens, index, portraits)
        if card:
            if not cards_open:
                append_markup('<div class="scientist-cards">\n')
                cards_open = True
            markup, index = card
            append_markup(markup)
            continue
        if cards_open:
            append_markup('</div>\n')
            cards_open = False
        current = tokens[index]
        if current.type == 'paragraph_open':
            inline = tokens[index + 1]
            children = inline.children or []
            if len(children) == 1 and children[0].type == 'image':
                image = children[0]
                source_path = image.attrGet('src')
                portrait = source_path == f'../../../{PORTRAIT_PLATE}.jpg'
                public_path = PORTRAIT_PATH if portrait else MANUSCRIPT_FIGURES.get(source_path)
                if public_path:
                    caption = manuscript_caption(tokens, index + 3, 'Portraits' if portrait else 'Figure')
                    if not caption or not image.content.strip():
                        raise ValueError(f'Missing manuscript figure caption or alternative text: {public_path}')
                    ident, caption_tokens = caption
                    description = markdown.renderer.renderInline(caption_tokens, markdown.options, {})
                    image.attrSet('src', public_path)
                    image.attrSet('loading', 'lazy')
                    image_markup = markdown.renderer.renderInline(children, markdown.options, {})
                    stem = public_path.removesuffix('.svg')
                    downloads = ''
                    if not portrait:
                        formats = ' · '.join(f'<a href="{stem}.{ext}" download>{ext.upper()}</a>'
                                             for ext in ('svg', 'png', 'jpg'))
                        downloads = (f'<div class="figure-downloads" role="group" aria-label="Download figure">'
                                     f'{formats}</div>')
                    chart = CHART_VIEWS.get(public_path)
                    interactive = ''
                    static_class = 'research-figure-image'
                    if chart:
                        view_path, view_title, view_kind = chart
                        interactive = (f'<iframe class="manuscript-chart {view_kind}" src="{view_path}"'
                                       f' title="{view_title}" loading="lazy" sandbox="allow-scripts"'
                                       f' aria-describedby="{ident}"></iframe>')
                        static_class += ' print-chart'
                    target = ident.removesuffix('-caption')
                    append_markup(f'<figure class="reader-figure research-figure" id="{target}" aria-labelledby="{ident}">'
                                  f'{interactive}<a class="{static_class}" href="{public_path}" '
                                  f'aria-label="Open full-size image" aria-describedby="{ident}">{image_markup}</a>'
                                  f'<figcaption id="{ident}">{description}</figcaption>'
                                  f'{downloads}</figure>\n')
                    index += 6
                    continue
        caption = manuscript_caption(tokens, index, 'Table')
        if caption and index + 3 < len(tokens) and tokens[index + 3].type == 'table_open':
            ident, caption_tokens = caption
            label = markdown.renderer.renderInline(caption_tokens, markdown.options, {})
            target = ident.removesuffix('-caption')
            append_markup(f'<div class="table-wrap manuscript-table" tabindex="0" role="region" '
                          f'id="{target}" aria-labelledby="{ident}"><table><caption id="{ident}">{label}</caption>\n')
            index += 4
            continue
        if current.type == 'table_open':
            append_markup('<div class="table-wrap" tabindex="0" role="region" '
                          'aria-label="Evidence table"><table>\n')
        elif current.type == 'table_close':
            append_markup('</table></div>\n')
        else:
            if current.type == 'inline' and index and tokens[index - 1].type == 'paragraph_open':
                link_figure_mentions(current, targets)
            article.append(current)
        index += 1
    if cards_open:
        append_markup('</div>\n')
    return markdown.renderer.render(article, markdown.options, {})


def link_figure_mentions(inline, targets):
    result = []
    nested = 0
    for child in inline.children or []:
        if child.type != 'text' or nested:
            result.append(child)
            nested += child.nesting
            continue
        cursor = 0
        for match in re.finditer(r'\b(Figure|Table) ([1-9]\d*)\b', child.content):
            label = match[0]
            anchor = f'{match[1].lower()}-{match[2]}'
            if anchor in targets:
                before = Token('text', '', 0, content=child.content[cursor:match.start()])
                link = Token('link_open', 'a', 1)
                link.attrSet('href', f'#{anchor}')
                result.extend((before, link, Token('text', '', 0, content=label), Token('link_close', 'a', -1)))
                cursor = match.end()
        result.append(Token('text', '', 0, content=child.content[cursor:]))
    inline.children = result


def horisma_module(root, module_name):
    helper = (root / f'src/horisma_p0/{module_name}.py').resolve(strict=True)
    if not helper.is_relative_to(root):
        raise ValueError('A manuscript renderer is outside Horisma')
    spec = spec_from_file_location(f'horisma_{module_name}', helper)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(manuscript, revision_date, portraits=frozenset(), *, horisma_root=None):
    empty, metadata, body = manuscript.decode('utf-8').split('---\n', 2)
    if empty or 'title: "The Secrets of Terms"' not in metadata or 'subtitle: "The Matthew Effect"' not in metadata:
        raise ValueError('Unexpected manuscript title or front matter')
    body, notes = body.split('## Sources and evidence notes\n', 1)
    notes = public_source_notes(notes)
    def cite(match):
        identifiers = [int(value) for value in match[1].split(',')]
        if any(ident not in notes for ident in identifiers):
            raise ValueError('A manuscript citation has no matching source note')
        return ' '.join(f'[{ident}](#source-{ident})' for ident in identifiers)

    body = re.sub(r'\[([1-9]\d*(?:\s*,\s*[1-9]\d*)*)\](?!\()', cite, body)
    markdown = MarkdownIt('commonmark', {'html': False}).enable('table')
    if horisma_root is not None:
        horisma_module(horisma_root, 'manuscript_math').install_mathml(markdown, horisma_root)
    tokens = markdown.parse(body)
    navigation = []
    figure_position = len(tokens)
    for index, current in enumerate(tokens):
        if current.type == 'heading_open':
            title = tokens[index + 1].content
            ident = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            current.attrSet('id', ident)
            if current.tag == 'h1':
                current.tag = tokens[index + 2].tag = 'h2'
            if current.tag in {'h2', 'h3'}:
                navigation.append((current.tag, ident, title))
            if ident == 'one-byline-more-than-one-contribution':
                figure_position = index + 3
                if figure_position < len(tokens) and tokens[figure_position].type == 'paragraph_open':
                    figure_position += 3
    figure = Token('html_block', '', 0)
    figure.content = POSTER_FIGURE
    tokens.insert(figure_position, figure)
    article = render_manuscript_article(markdown, tokens, portraits)
    sources = ''.join(
        f'<li id="source-{number}" value="{number}">{markdown.renderInline(text)}</li>\n'
        for number, text in notes.items()
    )
    links = contents_links(navigation)
    markup = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="The Horisma working manuscript on naming, scientific recognition and the Matthew Effect.">
  <title>The Matthew Effect · Horisma working manuscript</title>
  <link rel="stylesheet" href="style.css">
  <link rel="stylesheet" href="reader.css">
</head>
<body class="manuscript-edition">
  <a class="skip-link" href="#manuscript">Skip to the manuscript</a>
  <header class="masthead">
    <div class="shell masthead-inner">
      <a class="wordmark" href="index.html" aria-label="Computational social science research portfolio home">Computational social science</a>
      <nav aria-label="Site"><a href="index.html">Research portfolio</a><a href="#sources">Sources</a></nav>
    </div>
  </header>
  <main id="manuscript" class="shell reader">
    <header class="reader-heading">
      <p class="project-name">Horisma · The Secrets of Terms</p>
      <h1>The Matthew Effect</h1>
      <p class="subtitle">Recognition and credit in science</p>
      <p class="reader-edition">Working manuscript · <time datetime="{revision_date.isoformat()}">{revision_date.day} {revision_date:%B %Y}</time></p>
      <div class="reader-assets">
        <a href="assets/matthew-effect-poster.svg">A4 poster (SVG)</a>
        <a href="assets/matthew-effect-poster.pdf" download>Download poster (PDF)</a>
      </div>
    </header>
    <div class="reader-grid">
      <nav class="reader-contents" aria-label="Manuscript contents">
        <h2>Contents</h2>
        {links}
      </nav>
      <article class="reader-text" aria-label="The Matthew Effect working manuscript">
        {article}
        <section class="reader-sources" id="sources" aria-labelledby="sources-heading">
          <h2 id="sources-heading">Sources and evidence notes</h2>
          <ol>{sources}</ol>
        </section>
      </article>
    </div>
  </main>
  <footer class="site-footer">
    <div class="shell footer-inner">
      <a href="index.html">Research portfolio</a><a href="https://github.com/Computational-social-science">GitHub profile</a>
    </div>
  </footer>
</body>
</html>
"""
    figure_downloads = {f'{path.removesuffix(".svg")}.{ext}'
                        for path in MANUSCRIPT_FIGURES.values() for ext in ('svg', 'png', 'jpg')}
    PublicMarkup(markup, local_links=LOCAL_LINKS | figure_downloads | portraits |
                 {item[0] for item in CHART_VIEWS.values()})
    if re.search(r'<code>(?:passage:|evt-)|127\.0\.0\.1|localhost|file://|(?<![\w:])[A-Z]:[/\\]|scientific_acceptance|\bdata/(?:editorial|intake)\b',
                 markup, re.IGNORECASE):
        raise ValueError('Internal material appears in the public manuscript')
    return ('\n'.join(line.rstrip() for line in markup.splitlines()) + '\n').encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('horisma', type=Path, help='Horisma workspace root')
    args = parser.parse_args()
    root = args.horisma.resolve(strict=True)
    manuscript, revision, state = recorded_manuscript(root)
    posters, receipt = recorded_poster(root, digest(manuscript))
    revision_date = datetime.fromisoformat(revision['recorded_at']).date()
    people = recorded_people(root)
    portraits = {name for name in people if PEOPLE_PORTRAIT_PATH.fullmatch(name)}
    files = {'.nojekyll': b'', 'manuscript.html': render(manuscript, revision_date, portraits, horisma_root=root)}
    files.update({f'assets/matthew-effect-poster.{ext}': raw for ext, raw in posters.items()})
    files.update(experiment_figures(root, horisma_module(root, 'manuscript_charts')))
    if f'../../../{PORTRAIT_PLATE}.jpg'.encode() in manuscript:
        files.update(recorded_portraits(root))
    files.update(people)
    targets = {name: SITE / name for name in files}
    if any(not target.resolve().is_relative_to(SITE) for target in targets.values()):
        raise ValueError('An export target resolves outside the portfolio')
    if (source(root, STATE, 32_000_000) != state
            or source(root, MANUSCRIPT, 1_048_576) != manuscript
            or source(root, POSTER + '.json', 4096) != receipt):
        raise ValueError('The source changed during validation. Run the exporter again.')
    for name, path in targets.items():
        raw = files[name]
        if not path.exists() or path.read_bytes() != raw:
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                pending = Path(stream.name)
                stream.write(raw)
            try:
                pending.replace(path)
            finally:
                pending.unlink(missing_ok=True)
    print(json.dumps({'manuscript_sha256': digest(manuscript), 'editorial_revision': revision['revision'],
                      'files': {name: digest(raw) for name, raw in files.items()}}, indent=2))


if __name__ == '__main__':
    main()
