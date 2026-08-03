# English

## Releasing `blackbone`

Releases are managed by Release Please from conventional commits merged into
`main`. Use `fix:` for a patch release, `feat:` for a minor release, and a
`BREAKING CHANGE:` footer (or `feat!:`) for a major release.

Release Please maintains a release pull request containing the version bump and
`CHANGELOG.md` update. Merging that pull request creates a `vX.Y.Z` GitHub
release, builds the Python distributions, and publishes them to PyPI as
`blackbone`.

Version tracking starts at `0.0.0`; the first feature release will be `0.1.0`.

## Bilingual release notes

Release Please owns the canonical English `CHANGELOG.md`. After it creates or
updates a release pull request, OpenRouter generates semantically equivalent
English and Polish descriptions and commits the versioned Polish entry to
`CHANGELOG.pl.md` on the release branch. The same process updates the GitHub
Release notes after a release is created.

Configure these GitHub settings:

- Repository secret `OPENROUTER_API_KEY`: an OpenRouter API key with an
  appropriate spending limit.
- Optional repository variable `OPENROUTER_MODEL`: the OpenRouter model slug.
  It defaults to `google/gemini-3.1-flash-lite`.

The generated text is validated before GitHub is updated. OpenRouter failures
do not block versioning, tests, or PyPI publication; the original English notes
remain in place. Release note text derived from commit messages is sent to
OpenRouter for processing.

## One-time PyPI setup

Create a pending Trusted Publisher for the `blackbone` project on PyPI with:

- Owner: `smarthome-wroclaw`
- Repository: `blackbone`
- Workflow: `release-please.yml`
- Environment: `pypi`

Create a GitHub environment named `pypi` as well. Protection rules and required
reviewers are recommended. No `PYPI_API_TOKEN` secret is needed.

If release pull requests must trigger other GitHub Actions workflows, configure
a fine-grained token as `RELEASE_PLEASE_TOKEN`; the workflow will use it
automatically. The default `GITHUB_TOKEN` is sufficient for the release and
publication workflow implemented here.

# Polski

## Wydawanie `blackbone`

Wydaniami zarządza Release Please na podstawie konwencjonalnych commitów
scalonych do `main`. Użyj `fix:` dla wydania poprawkowego, `feat:` dla wydania
minor oraz stopki `BREAKING CHANGE:` (lub `feat!:`) dla wydania major.

Release Please utrzymuje PR wydania zawierający zmianę wersji oraz aktualizację
`CHANGELOG.md`. Scalenie tego PR-a tworzy wydanie GitHub `vX.Y.Z`, buduje
dystrybucje Pythona i publikuje je w PyPI jako `blackbone`.

Śledzenie wersji rozpoczyna się od `0.0.0`; pierwszym wydaniem funkcjonalnym
będzie `0.1.0`.

## Dwujęzyczne informacje o wydaniu

Release Please zarządza kanonicznym angielskim plikiem `CHANGELOG.md`. Po
utworzeniu lub zaktualizowaniu PR-a wydania OpenRouter generuje semantycznie
równoważne opisy angielskie i polskie oraz zapisuje wersjonowany polski wpis w
`CHANGELOG.pl.md` na gałęzi wydania. Ten sam proces aktualizuje informacje o
wydaniu GitHub po utworzeniu wydania.

Skonfiguruj następujące ustawienia GitHub:

- Sekret repozytorium `OPENROUTER_API_KEY`: klucz API OpenRouter z odpowiednim
  limitem wydatków.
- Opcjonalna zmienna repozytorium `OPENROUTER_MODEL`: identyfikator modelu
  OpenRouter. Domyślna wartość to `google/gemini-3.1-flash-lite`.

Wygenerowany tekst jest walidowany przed aktualizacją GitHub. Błędy OpenRouter
nie blokują wersjonowania, testów ani publikacji do PyPI; oryginalne angielskie
informacje pozostają bez zmian. Tekst informacji o wydaniu pochodzący z
komunikatów commitów jest wysyłany do OpenRouter w celu przetworzenia.

## Jednorazowa konfiguracja PyPI

Utwórz oczekującego Trusted Publishera dla projektu `blackbone` w PyPI z
następującymi wartościami:

- Owner: `smarthome-wroclaw`
- Repository: `blackbone`
- Workflow: `release-please.yml`
- Environment: `pypi`

Utwórz również środowisko GitHub o nazwie `pypi`. Zalecane są reguły ochrony i
wymagani recenzenci. Sekret `PYPI_API_TOKEN` nie jest potrzebny.

Jeśli PR-y wydania mają uruchamiać inne workflowy GitHub Actions, skonfiguruj
token o ograniczonych uprawnieniach jako `RELEASE_PLEASE_TOKEN`; workflow użyje
go automatycznie. Domyślny `GITHUB_TOKEN` jest wystarczający dla zaimplementowanego
workflow wydania i publikacji.
