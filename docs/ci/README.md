# CI workflow template

`tests.yml` contains the reviewed GitHub Actions workflow for Python contract tests and compilation.

It is intentionally kept here as an **inactive template**. During initialization, GitHub rejected the push of `.github/workflows/tests.yml` because the existing OAuth credential lacks the `workflow` scope. No additional authorization was requested and the credential was not changed. The source code, real-data source plans, static dashboard, and locally verified tests can be published without activating Actions.

To enable CI later, a repository owner with appropriate workflow authorization can copy this template to `.github/workflows/tests.yml` and commit it. Until an actual Actions run is observed, no remote CI success is claimed. The initialization's 48 tests were run locally; evidence is retained in the private processing workspace.
