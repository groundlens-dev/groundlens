## Summary

<!-- What does this PR do? Link to related issues with "Closes #123" if applicable. -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)
- [ ] Test improvement

## Changes

<!-- Bullet list of specific changes. -->

-

## Testing

<!-- How was this tested? Include test commands and any manual verification steps. -->

```bash
pytest tests/
ruff check src/ tests/
mypy src/groundlens/
```

## Checklist

- [ ] Tests pass locally (`pytest`)
- [ ] Linting passes (`ruff check src/ tests/`)
- [ ] Type checking passes (`mypy src/groundlens/`)
- [ ] New code has tests
- [ ] New public API has docstrings (Google style)
- [ ] CHANGELOG.md updated (for user-facing changes)
- [ ] No secrets or credentials in the diff
