# ticket-110: Pomiń dzierżawy alokacyjne Worktrees v5 w kontroli authority-lifecycle

- **ID**: ticket-110
- **Owner**: agent:coding-agent
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

## Goal and scope

Kontrola authority-lifecycle rozpoznaje brak wymaganego dokumentu także wtedy, gdy katalog dzierżaw zawiera wyłącznie rekordy alokacyjne Worktrees v5.

SESSION_EXECUTION_AUTHORIZATION: validated native ticket PLF-28770; Willman request 3a27db9d-e0af-4f18-b1f8-8d09afe7a811; protected publication only.

## Acceptance criteria

- [x] AC-01: Gdy katalog .subactor/leases zawiera wyłącznie pliki JSON ze schematem wellmanifest.worktrees/v5, check_authority_lifecycle() zwraca dokładnie jedno zgłoszenie GOV-AUTHORITY-LIFECYCLE-MISSING. Brak plików kandydujących nadal daje ten sam wynik.
- [x] AC-02: Współistnienie dzierżawy Worktrees v5 z poprawnym dokumentem authority-lifecycle lub change-lease daje wynik bez zgłoszeń. Niepoprawne pozostałe pliki zachowują dotychczasowe diagnostyki, w tym INVALID dla uszkodzonego JSON, nieznanego schematu i schematu Worktrees v5 w ścieżce profilu.
- [ ] AC-03: Testy regresyjne przechodzą przez ConformanceRunner. Pełny pytest i ./project/governance-check.sh --actor ci kończą się kodem 0.

## Weryfikacja

- Zatwierdzony runtime Wellmana z pinu `d8c7a0ad558e6edb702a4c6d1a507841b0384000` uruchomił `python -m pytest -q -p no:wellmanifest_governance -o cache_dir=.subactor/cache/pytest tests/test_catalog_pack_checkers.py` w checkoutcie zgłoszenia z jawnym użyciem `.venv` głównego checkoutu. Wynik to 21 zaliczonych testów, kod 0. Potwierdzenie wykonania jest w `.subactor/cache/execution/e873b898ba9645cda08464ceb5395682/context.json`.
- Pierwsze uruchomienie pytest wywołało automatyczną bramkę, która zgłosiła `GOV-SECRET-001` dla obecnej wcześniej atrapy tokena. Jawny znacznik testowy zachowuje asercję `GOV-ACCOUNT-RUNTIME-SECRET`. Dedykowany przebieg regresji wyłączył automatyczne wywołanie bramki.
- Runner jest właścicielem dzierżawy `receipt:project-lease/3a27db9d-e0af-4f18-b1f8-8d09afe7a811` (rewizja i token fencing `1`) dla `ticket/110-project-job-3a27db9d`, `.worktrees/ticket-110--project-job-3a27db9d`, HEAD i `acceptedBaseSha` `e5187a6f9577601f6580aba9cad971a936d0dd57`. Plan i wycinek wiąże checkpoint runnera `receipt:continuity.ticket-110.3.9f3436f6f00a9f2098733d0f98a43c640d6f0b45c18516292e117d53e6244253`.
- Runner przejmuje zmiany do zapisania nowego checkpointu i weryfikacji pełnym `pytest` oraz `./project/governance-check.sh --actor ci` przed chronioną publikacją PLF-28770.
