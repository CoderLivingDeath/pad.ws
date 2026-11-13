# CI conventions

## Commit messages

The repository uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(optional scope): <subject>
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
The first line is limited to 100 characters.

Enable the local hook once per clone:

```bash
git config core.hooksPath .githooks
```

CI runs `commitlint` on every pull request and also validates the pull request title, because squash merges use that title as the commit message.

## Workflows

- `actionlint` validates every workflow.
- Every `uses:` entry must be pinned to a full 40-character commit SHA with the release in a comment:

  ```yaml
  uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
  ```

- Local actions (`./...`) are allowed. Docker references (`docker://...`) must be pinned by digest.
- The pin check runs in CI and locally:

  ```bash
  ./scripts/check-actions-pinned.sh
  ```

To update an action, resolve the new tag to its commit SHA and update both the SHA and the comment:

```bash
git ls-remote https://github.com/actions/checkout 'refs/tags/v4.4.0' 'refs/tags/v4.4.0^{}'
```

The lint workflow lives in `.github/workflows/lint.yml`.
