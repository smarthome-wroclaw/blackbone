# BlackBone Add-ons design

## English

BlackBone Add-ons v1 installs data-only Modbus device packs. An add-on is the user-facing extension; a pack is declarative and cannot execute code; an app is a future container extension with a separate trust and permission model. The v1 installer never imports `boneio.extensions`, runs hooks, copies to caller-selected destinations, or accepts commands, images, environment variables, device mounts, or executable entry points.

Installed content is private to `addons/installed/<id>/<version>/`. Enabled `files/modbus_devices/*.json` directories are read-only inputs to the existing Modbus registry, which reports their ownership as `addon:<id>`. Built-in and user-created definitions have priority, and conflicts fail validation instead of shadowing another source.

Repository, installed, and operation state uses strict versioned JSON models. All writes use a sibling temporary file, file flush and `fsync`, atomic rename, and a parent-directory `fsync` on POSIX. One filesystem lock serializes repository and lifecycle mutations. Every lifecycle mutation creates a local tar snapshot before changing an installed directory or `state.json`. Startup restores snapshots for interrupted applying or reloading operations before accepting another mutation.

Repository fetches require HTTPS and same-origin package URLs. Credentials, fragments, traversal, cross-origin redirects, and DNS results in private, loopback, link-local, multicast, reserved, or unspecified ranges are rejected. Response sizes and timeouts are bounded. Successful repository indexes are cached with ETags and remain available as last-known-good data while a repository is offline.

### Manifest v1

```yaml
schema_version: 1
id: community.eastron-sdm72d
name: Eastron SDM72D
version: 1.0.0
type: modbus_device_pack
blackbone:
  version: ">=0.1.0,<1.0.0"
author:
  name: Example Maintainer
license: MIT
files:
  - path: modbus_devices/sdm72d.json
    sha256: <64 lowercase hexadecimal characters>
```

Logical paths map only to the pack's private `files/modbus_devices/` directory. Versions are exact PEP 440-compatible three-part public releases. The index pins every manifest hash; the manifest pins every file hash. A preview confirmation token binds repository, add-on ID, exact version, manifest hash, action, and expiry. Install/update re-download and re-check the manifest before applying it.

The API is under `/api/addons`. Mutations require configured dashboard credentials and return stable `{code, message, details}` errors. Long lifecycle operations persist progress before background execution. The feature and its navigation item are disabled by default and enabled with `BONEIO_ADDONS=true` for the experimental release.

## Polski

BlackBone Add-ons v1 instaluje wyłącznie deklaratywne pakiety urządzeń Modbus. „Dodatek” jest nazwą rozszerzenia widoczną dla użytkownika; „pakiet” zawiera tylko dane i nie wykonuje kodu; „aplikacja” oznacza przyszłe rozszerzenie kontenerowe z osobnym modelem zaufania i uprawnień. Instalator v1 nigdy nie importuje `boneio.extensions`, nie uruchamia hooków, nie kopiuje plików do miejsc wybranych przez klienta i nie akceptuje poleceń, obrazów, zmiennych środowiskowych, montowania urządzeń ani wykonywalnych punktów wejścia.

Zainstalowana zawartość pozostaje prywatna w `addons/installed/<id>/<version>/`. Katalogi włączonych pakietów `files/modbus_devices/*.json` są źródłami tylko do odczytu dla istniejącego rejestru Modbus, który zgłasza właściciela jako `addon:<id>`. Definicje wbudowane i utworzone przez użytkownika mają pierwszeństwo, a konflikt zatrzymuje walidację zamiast przesłaniać inne źródło.

Stan repozytoriów, instalacji i operacji używa ścisłych, wersjonowanych modeli JSON. Każdy zapis korzysta z sąsiedniego pliku tymczasowego, opróżnienia bufora i `fsync`, atomowej zmiany nazwy oraz `fsync` katalogu nadrzędnego na POSIX. Jedna blokada systemu plików serializuje mutacje. Każda operacja cyklu życia tworzy lokalną migawkę tar przed zmianą katalogu instalacji lub `state.json`. Po starcie BlackBone przywraca migawkę operacji przerwanej na etapie stosowania lub przeładowania, zanim dopuści kolejną mutację.

Repozytoria wymagają HTTPS, a wszystkie adresy pakietu muszą pozostać w tym samym originie. Dane logowania, fragmenty, traversal, przekierowania do innego originu oraz wyniki DNS z zakresów prywatnych, loopback, link-local, multicast, zastrzeżonych lub nieokreślonych są odrzucane. Limity rozmiaru i czasu są wymuszane. Poprawny indeks jest buforowany z ETag i pozostaje ostatnią znaną dobrą wersją podczas awarii repozytorium.

Schemat manifestu v1 jest identyczny z przykładem angielskim powyżej. Ścieżki logiczne mapują się wyłącznie do prywatnego katalogu `files/modbus_devices/` pakietu. Wersje są dokładnymi, publicznymi, trzyczęściowymi wydaniami zgodnymi z PEP 440. Indeks przypina hash manifestu, a manifest przypina hashe plików. Token potwierdzenia podglądu wiąże repozytorium, ID dodatku, dokładną wersję, hash manifestu, akcję i czas wygaśnięcia. Instalacja i aktualizacja ponownie pobiera i sprawdza manifest przed zastosowaniem zmian.

API znajduje się pod `/api/addons`. Mutacje wymagają skonfigurowanych danych logowania panelu i zwracają stabilne błędy `{code, message, details}`. Długie operacje zapisują postęp przed uruchomieniem w tle. Funkcja i pozycja nawigacji są domyślnie wyłączone; wydanie eksperymentalne włącza je przez `BONEIO_ADDONS=true`.
