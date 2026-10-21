# applymap

A CLI that scores job postings against your skills, ranks which ones are
worth your time, and drafts tailored cover letters with an LLM — honestly.

## Why

Applying to jobs means reading dozens of postings and guessing which ones
fit. applymap does the tedious part: it extracts the tech skills a posting
asks for, compares them against *your* profile, and shows a fit score plus
the exact gaps. Optional AI features draft a cover letter from your real
experience — the prompt is built to never invent jobs, metrics, or skills
you don't have.

## Install

```bash
pip install .
# or, editable for development:
pip install -e ".[dev]"   # dev extras not required; tests need pytest + pyyaml
```

Requirements: Python 3.10+, `pyyaml`, `pytest` (for tests).

## Usage

1. Create your profile (kept outside the repo so personal details never get committed):

```bash
applymap init-profile        # writes ~/.applymap/profile.yaml — edit it with your real details
applymap check-profile       # validate it: warns about gaps the matcher needs
```

2. Save a job posting to a text file, then analyze it:

```bash
applymap analyze posting.txt
applymap analyze posting.txt --json   # machine-readable report for scripting
```

Example output:

```
Fit score: 71/100

Matched skills:
  + python
  + sql
  + docker

Missing skills:
  - kubernetes
```

3. Rank several postings at once:

```bash
applymap rank posting-a.txt posting-b.txt posting-c.txt
applymap rank posting-*.txt --csv ranking.csv   # also save to a spreadsheet
applymap rank posting-*.txt --min-score 60      # hide postings below 60/100
applymap rank posting-*.txt --json              # machine-readable ranking for scripting
```

Postings that tie on fit score are ordered by how often the matched
skills appear in the posting text — a posting that mentions Python five
times ranks above one that mentions it once.

4. Track the jobs you apply to:

```bash
applymap track posting-a.txt --company "Acme" --role "Backend Engineer"
```

`track` records the date, company, role, fit score, and status
(`interested`/`applied`/`interview`/`offer`/`rejected`) in
`~/.applymap/applications.json` — one JSON list you can open in any editor.
Set `APPLYMAP_DATA_DIR` to move it elsewhere. When a posting contains no
recognizable tech skills, `track` warns you instead of silently logging a
meaningless 0/100.

List what you've applied to (newest first), optionally filtered by status:

```bash
applymap applications
applymap applications --status interview
applymap applications --json   # machine-readable records for scripting
```

Move an application through the pipeline as it progresses:

```bash
applymap update-status --company "Acme" --role "Backend Engineer" --status interview
```

Get a quick summary of your pipeline — total tracked, counts by status,
average fit score, the best-fit application, and the applied → interview →
offer conversion funnel:

```bash
applymap stats
```

Find applications that have been waiting too long for a response:

```bash
applymap followup            # 'applied' 30+ days with no status change
applymap followup --days 14  # flag anything waiting 2 weeks or more
```

Export the whole log to a spreadsheet:

```bash
applymap export --csv applications.csv
applymap export --csv applications.json --format json   # for scripts
```

5. AI features (optional, need an API key):

```bash
export APPLYMAP_API_KEY="sk-..."                    # OpenAI-compatible key
export APPLYMAP_API_BASE="https://api.openai.com/v1" # or any compatible endpoint
export APPLYMAP_MODEL="gpt-4o-mini"                  # optional, this is the default

applymap analyze posting.txt --ai                   # adds an AI gap analysis
applymap cover-letter posting.txt --company "Acme" --role "Backend Engineer" -o letter.md
```

The offline analysis (scores, matched/missing skills, ranking) always works
with no key and no network. Only `cover-letter` and `--ai` call the API.

Skill aliases: the matcher treats common alternate names as the same skill
— `k8s` counts as `kubernetes`, `js` as `javascript`, `postgres` as
`postgresql`, and so on — on both the profile and the posting side, so
equivalent wording never costs you points. Hyphenated spellings are
covered too: `REST-API` counts as `rest`, `CI-CD` as `ci/cd`,
`machine-learning` as `machine learning`. Fused JS-ecosystem spellings
also resolve: `NodeJS` counts as `node`, `ReactJS` as `react`,
`VueJS` as `vue`.

## Roadmap

- [ ] PDF/DOCX resume parsing so the profile builds itself
- [x] `track` command: log applications and follow-up dates
- [x] `applications` command: view tracked applications, filter by status
- [x] Skill-gap study plans generated from missing skills (via `analyze --ai`)
- [ ] Web UI for side-by-side posting comparison
- [x] Batch mode: score several postings, export CSV (`rank --csv`)
