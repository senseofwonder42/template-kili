# Notebooks

## Naming convention

```
NN-initials-short-description.ipynb
```

* `NN` — a two-digit ordering number (`00`, `01`, ... ), so the folder reads
  in the order the analysis happened.
* `initials` — the author's initials, so it is obvious who to ask.
* `short-description` — a few words in kebab-case.

Examples: `01-af-explore-raw-sales.ipynb`, `02-af-baseline-model.ipynb`.

## Rules

* Notebooks are for exploration. Once code is reused, move it into
  `src/` and import it from the notebook.
* Outputs are stripped on commit by the `nbstripout` pre-commit hook, so only
  the code is versioned. Re-run the notebook to see the results again.
* Never read or write data with relative paths: import the directories from
  the `paths` module instead.
