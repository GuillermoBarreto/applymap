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

Requirements: Python 3.9+, `pyyaml`, `pytest` (for tests).

## Usage

1. Create your profile (kept outside the repo so personal details never get committed):

```bash
applymap init-profile        # writes ~/.applymap/profile.yaml — edit it with your real details
```

2. Save a job posting to a text file, then analyze it:

```bash
applymap analyze posting.txt
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
```

4. AI features (optional, need an API key):

```bash
export APPLYMAP_API_KEY="sk-..."                    # OpenAI-compatible key
export APPLYMAP_API_BASE="https://api.openai.com/v1" # or any compatible endpoint
export APPLYMAP_MODEL="gpt-4o-mini"                  # optional, this is the default

applymap analyze posting.txt --ai                   # adds an AI gap analysis
applymap cover-letter posting.txt --company "Acme" --role "Backend Engineer" -o letter.md
```

The offline analysis (scores, matched/missing skills, ranking) always works
with no key and no network. Only `cover-letter` and `--ai` call the API.

## Roadmap

- [ ] PDF/DOCX resume parsing so the profile builds itself
- [ ] `track` command: log applications and follow-up dates
- [ ] Skill-gap study plans generated from missing skills
- [ ] Web UI for side-by-side posting comparison
- [ ] Batch mode: score every posting in a folder, export CSV
