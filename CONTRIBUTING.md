# Contributing to Berlinale Ticket Buyer

Thanks for your interest in contributing! This project welcomes contributions of all kinds.

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/Rswcf/berlinale-ticket-buyer/issues) to avoid duplicates
2. Open a new issue with:
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots or error logs if applicable
   - Your OS and Python version

### Suggesting Features

Open an issue with the `enhancement` label describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

### Submitting Code

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Test manually (create a task, trigger a grab, verify UI)
5. Commit with a clear message
6. Push and open a Pull Request

### What We're Looking For

- Bug fixes
- UI/UX improvements
- Support for additional ticketing platforms
- Performance optimizations
- Documentation improvements
- Translations

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer
pip install -r requirements.txt
playwright install chromium
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Project Structure

- `app/` — Backend (FastAPI, Playwright automation, scheduling)
- `static/` — Frontend (vanilla JS single-page app)
- `data/` — Runtime data (git-ignored)
- `docs/` — Translated READMEs

## Code Style

- Python 3.9+ with `from __future__ import annotations`
- Pydantic v2 for data models
- Async/await throughout
- No test suite yet — test manually

## Questions?

Open a [Discussion](https://github.com/Rswcf/berlinale-ticket-buyer/discussions) or an issue.
