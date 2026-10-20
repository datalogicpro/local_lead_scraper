# Changelog

All notable changes to this project are listed here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-20

### Added

- A web page: try the made-up sample data or upload your own file, run it again to see leads updated instead of duplicated, compare the data before and after cleaning, and download the leads as a CSV file. The page never calls Google.
- Type hints on all the code, checked with mypy.
- Tests with 100% coverage, Ruff, pip-audit, and pre-commit.
- GitHub Actions for the checks and tests, and Dependabot.
- An MIT license.

### Changed

- Dependencies are managed with uv in `pyproject.toml` and `uv.lock`, in place of `requirements.txt`. pandas was removed, since nothing used it.
- Values in a reply that are not text, such as a number where a name should be, now count as missing instead of stopping the run.
- The sample file is found next to the script, so the scraper works from any folder.
- The scraper returns an exit code of 1 when it can't get data, and always closes the database.
