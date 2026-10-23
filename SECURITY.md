# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting a vulnerability

Report a vulnerability privately through
[GitHub Security Advisories](https://github.com/pinjun99/Systematic_Review/security/advisories/new).

Describe what you found, how to reproduce it, and which version you tested. Do
not open a public issue for an unfixed vulnerability. Do not include access
tokens, patient information, copyrighted full texts, or search exports in the
report.

This is a single-maintainer research project, so please allow several days for
a reply. The repository does not run a hosted service. A report may be a
documentation problem or a way the local tools could mishandle a review
workspace.

## Data that should stay out of git

Search exports, PDFs, and SQLite databases from a real review can contain
licensed text or personal data. `.gitignore` is meant to keep `.env*`, `*.pdf`,
`*.sqlite`, and `*.ris` files out of commits. If you find credentials or
personal data already in the history, report that privately as well.

## Scope

In scope: the skills, validators, tests, and documentation in this repository,
including ways they might leak data from a review workspace or accept a forged
approval record.

Out of scope: bibliographic databases, publisher websites, and the models used
to run the skills. Do not test systems you do not have permission to test.
