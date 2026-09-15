# BlackBone Add-ons

## English

Add-ons let an installer add community Modbus device definitions from the dashboard. A v1 pack contains JSON mappings only: it cannot run code or directly control hardware.

Enable the experimental feature with `BONEIO_ADDONS=true` and configure dashboard username/password credentials. Open **Add-ons**, add an HTTPS repository if needed, refresh, and review a pack before installing it. The preview shows repository trust, the exact version, every pinned file, and its SHA-256 hash. Official repositories are marked separately from unreviewed custom repositories.

Install, update, enable, disable, remove, and rollback actions appear as persisted operations. The dialog can be reopened after a browser refresh using the operation ID. BlackBone blocks disabling or removing a pack while active configuration uses one of its models. Installed packs and their pinned files are included in configuration backups; transient downloads, operation logs, and rollback snapshots are excluded.

If a repository is offline, installed packs continue to work and the last successfully cached catalog remains visible. A failed validation or reload automatically restores the pre-operation snapshot. A `recovery_required` health state means automatic recovery could not complete and further mutations remain disabled.

## Polski

Dodatki pozwalają instalatorowi dodawać społecznościowe definicje urządzeń Modbus z panelu. Pakiet v1 zawiera wyłącznie mapowania JSON: nie może wykonywać kodu ani bezpośrednio sterować sprzętem.

Włącz funkcję eksperymentalną przez `BONEIO_ADDONS=true` i skonfiguruj nazwę użytkownika oraz hasło panelu. Otwórz **Dodatki**, w razie potrzeby dodaj repozytorium HTTPS, odśwież katalog i sprawdź pakiet przed instalacją. Podgląd pokazuje zaufanie do repozytorium, dokładną wersję, każdy przypięty plik i jego hash SHA-256. Repozytoria oficjalne są wyraźnie odróżnione od niezweryfikowanych repozytoriów własnych.

Instalacja, aktualizacja, włączenie, wyłączenie, usunięcie i wycofanie są trwałymi operacjami. Po odświeżeniu przeglądarki postęp można ponownie odczytać przez ID operacji. BlackBone blokuje wyłączenie lub usunięcie pakietu, gdy aktywna konfiguracja używa jednego z jego modeli. Zainstalowane pakiety i ich przypięte pliki trafiają do kopii konfiguracji; przejściowe pobrania, dzienniki operacji i migawki wycofania są pomijane.

Gdy repozytorium jest offline, zainstalowane pakiety nadal działają, a ostatni poprawnie zapisany katalog pozostaje widoczny. Nieudana walidacja lub przeładowanie automatycznie przywraca migawkę sprzed operacji. Stan `recovery_required` oznacza, że automatyczne odzyskiwanie nie zakończyło się i dalsze mutacje pozostają zablokowane.
