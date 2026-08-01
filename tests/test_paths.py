from kili_examples import paths


def test_project_root_is_the_repository_root():
    """PROJECT_ROOT resolves from the package, not from the CWD."""
    assert (paths.PROJECT_ROOT / "pyproject.toml").is_file()


def test_data_directories_exist():
    """The standard data layout ships with the template."""
    expected = {
        paths.RAW_DIR: "raw",
        paths.INTERIM_DIR: "interim",
        paths.PROCESSED_DIR: "processed",
        paths.EXTERNAL_DIR: "external",
    }
    for directory, name in expected.items():
        assert directory == paths.DATA_DIR / name
        assert directory.is_dir()


def test_models_and_reports_directories_exist():
    """Model artifacts and reports have a home too."""
    assert paths.MODELS_DIR.is_dir()
    assert paths.FIGURES_DIR == paths.REPORTS_DIR / "figures"
    assert paths.FIGURES_DIR.is_dir()
