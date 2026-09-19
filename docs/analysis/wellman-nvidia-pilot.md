---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "wellman-nvidia-pilot",
  "kind": "analysis",
  "version": 2,
  "title": "Pilotaż NVIDIA: poprawność kontroli standardów Wellman",
  "status": "current",
  "owner": "wellmanifest/wellman",
  "created": "2026-09-19",
  "updated": "2026-09-19",
  "affected_repositories": [
    "wellmanifest/wellman",
    "semcod/koru"
  ],
  "source_revision": "56258269a51f69fae5f787c1d6cf229d2473e5ba"
}
---

# Pilotaż NVIDIA: poprawność kontroli standardów Wellman

## Cel

Zweryfikowano, czy `wellman` może zastąpić lokalne, powielane kontrolery
standardów w repozytoriach Wellmanifest. Pilotaż wykonano na hoście z NVIDIA
GeForce RTX 4060 (8 GiB) i driverem 580.159.03, na bazie `semcod/koru`.

## Obserwacje

1. Polecenie źródłowe `uv run wellman check --root /home/tom/github/semcod/koru`
   zakończyło się kodem 0 i nie zwróciło ustaleń.
2. Powłoka hosta ma `/home/tom/.local/bin` na `PATH`, lecz nie ma tam
   zainstalowanego launchera `wellman`. Zainstalowano lokalny wheel `0.20.36`
   przez `uv tool`; udostępnia on `/home/tom/.local/bin/wellman` i powtórzył
   zielony audyt Koru.
3. Przed poprawką zarówno `wellman check --standard wellmanifest/nope`, jak i
   `wellman adopt unknown-standard` kończyły się kodem 0. Pierwsze polecenie
   uruchamiało niepowiązany pełny skan, a drugie tworzyło manifest z nieznanym
   identyfikatorem.
4. `wellman adopt` zapisywał stałą wersję `0.20.32`, mimo że pakiet ma wersję
   `0.20.35`, oraz nadpisywał istniejący manifest bez jawnej zgody.

## Poprawki

- `check --standard` rozpoznaje identyfikator z katalogu i uruchamia wyłącznie
  jego kontrolę; brak implementacji konkretnej kontroli jest błędem
  `GOV-STANDARD-NOT-IMPLEMENTED`, a nie zielonym wynikiem.
- Nieznany standard zwraca `GOV-STANDARD-UNKNOWN` i kod 1.
- `adopt` sprawdza standard lub profil przed utworzeniem `.governance/`;
  istniejący manifest wymaga `--force`, a wersja manifestu pochodzi z wersji
  uruchomionego pakietu.
- Walidator odrzuca zapisany manifest z nieznanym standardem lub profilem.

## Ocena

Pilot potwierdza przydatność Wellman jako deterministycznej warstwy kontroli
dla zaimplementowanych rodzin standardów: bootstrapu projektu, Git,
worktree, ticketów i kontraktu agenta. Nie potwierdza jeszcze pełnej
zgodności całego katalogu 25 standardów: pozostałe pozycje katalogu nie mają
w tej wersji osobnych kontroli wykonawczych. Poprawka zmienia ten brak z
fałszywego sukcesu w jawny, fail-closed wynik.

## Dowody

- `uv run --extra dev --group dev python -m pytest -q`
- `uv run --locked python -m build`
- `uv run --locked twine check dist/*`
- `uv run wellman check --root /home/tom/github/semcod/koru`
- `wellman --version` → `0.20.36`
- lokalny wheel SHA-256: `84184f92d1ca6411656a4339a33461b2f4e8ab6c387ab83e61b9f69834d99821`

## Rekomendacja

Wdrażać Wellman etapami: najpierw jako lokalny audyt dla rodzin z konkretną
kontrolą, potem jako wymagany check CI po niezależnym potwierdzeniu. Zainstalować
wydany pakiet na kolejnych hostach przez `uv tool install wellman` lub
równoważny zarządzany mechanizm. Instalacja `0.20.36` na tym hoście jest
lokalnym pilotem z weryfikowanego wheelu i nie jest dowodem publikacji PyPI ani
akceptacji dla wdrożenia floty.
