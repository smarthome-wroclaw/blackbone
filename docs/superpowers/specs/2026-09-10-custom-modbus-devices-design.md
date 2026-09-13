# Własne urządzenia Modbus — design

Data: 2026-09-10
Status: zatwierdzony do planowania implementacji

## Problem

Definicje urządzeń Modbus to pliki JSON w katalogu pakietu
`boneio/modbus/devices/{energy_meters,hvac,inverters,sensors,other}/*.json`.
Podłączenie urządzenia spoza tej listy jest dziś niemożliwe bez modyfikacji
zainstalowanego pakietu:

- runtime ładuje definicje przez `open_json()` (`boneio/core/utils/util.py:60`,
  wołane z `boneio/modbus/coordinator.py:117`) — skanuje wyłącznie katalog pakietu;
- lista modeli jest wstrzykiwana do schematu cerberus jako `allowed`
  (`boneio/core/config/yaml_util.py:83`), więc model spoza listy nie przechodzi
  walidacji `config.yaml`;
- katalog dla frontendu jest generowany na etapie builda
  (`frontend/src/generated/modbusDeviceCatalog.ts`);
- `/schema` jest serwowane jako statyczny mount z katalogu pakietu
  (`boneio/webui/app.py:796,891`), więc edytor YAML zna tylko modele z builda;
- istniejący `ModbusDeviceCreator` (frontend) potrafi zbudować definicję i
  przetestować rejestry na żywo przez `/api/modbus/get`, ale umie ją tylko
  pobrać albo skopiować do schowka.

Plik wrzucony ręcznie do katalogu pakietu ginie przy `pip install --upgrade`,
a w instalacji systemowej katalog bywa tylko do odczytu.

## Decyzje

| Decyzja | Wybór |
|---|---|
| Sposób dodawania | Zapis z kreatora **oraz** import gotowego pliku JSON |
| Relacja do wbudowanych | Fork wbudowanego jako punkt startowy tak; nadpisanie wbudowanego nie |
| Cykl życia | Auto-reload po zapisie; usunięcie definicji w użyciu zablokowane |
| Zakres formatu w kreatorze | Metadane + odczyt rejestrów (bez edycji encji zapisywalnych i pochodnych) |
| Magazyn | Katalog użytkownika obok `config.yaml` + centralny rejestr modeli |

### Odrzucone warianty

**Definicje inline w `config.yaml`** (sekcja `modbus_models:`) — wymaga schematu
cerberus dla całego formatu rejestrów, rozdmuchuje config o setki linii na
urządzenie i zrywa wymienialność plików JSON ze społecznością.

**Zapis do katalogu pakietu** (`boneio/modbus/devices/custom/`) — najmniej kodu,
bo wszystkie skany już tam patrzą, ale aktualizacja pakietu kasuje pracę
użytkownika bez ostrzeżenia, katalog bywa read-only, a dane użytkownika mieszają
się z kodem.

## 1. Magazyn i rejestr modeli

**Lokalizacja.** `<katalog_config.yaml>/modbus_devices/`, tworzony leniwie przy
pierwszym zapisie. Płasko, jeden plik na model, nazwa pliku = klucz modelu
(`mojlicznik.json`). Wbudowane trzymają kategorię w podkatalogu *i* w polu
`category` (mają je wszystkie 27 plików), więc dla własnych wystarczy samo pole —
bez podkatalogów nie ma dwóch źródeł prawdy o kategorii.

Klucz walidowany wzorcem `^[a-z0-9][a-z0-9_-]{1,63}$`, co jednocześnie odcina
path traversal.

**Nowy moduł `boneio/modbus/device_registry.py`** — jedyne miejsce w kodzie,
które wie, gdzie leżą definicje:

```python
configure(custom_dir: str | None) -> None   # raz przy starcie
list_models() -> list[ModelRef]             # ModelRef(key, path, source: "builtin"|"custom")
load_model(key: str) -> dict                # ModelNotFoundError gdy brak
```

Wbudowane skanowane raz (niezmienne w czasie życia procesu), własne indeksowane
z unieważnianiem po `mtime` katalogu — tanio na BeagleBone, a zapis przez WebUI
jest widoczny natychmiast bez restartu.

**Kolizje kluczy.** Zapis pod nazwą istniejącego modelu wbudowanego jest
odrzucany (409). Dodatkowo przy odczycie wbudowany wygrywa i loguje ostrzeżenie,
więc plik wrzucony ręcznie przez SSH też niczego po cichu nie przesłoni.

**Punkty wpięcia.** `configure()` wołane na początku `load_config_from_file()`
(`yaml_util.py:1211`) — przechodzą przez nie wszystkie ścieżki startu i
przeładowania, a ścieżka configu jest tam znana. Na rejestr przechodzą:

- `open_json()` (`core/utils/util.py:60`) — sygnatura zachowana
- `_get_modbus_device_models()` (`yaml_util.py:83`)
- `/modbus/models` i `/modbus/models/{m}/entities` (`webui/routes/modbus.py:527,585`)
- `boneio/modbus/mock_coordinator.py`
- `boneio/webui/routes/dev_fake_device.py`
- `boneio/modbus/cli.py`

Wyjątkiem zostaje `boneio/core/config/schema_converter.py` — działa na etapie
builda w CI, gdzie żaden katalog użytkownika nie istnieje; jego kopia logiki
skanującej pozostaje bez zmian (patrz sekcja 3).

**Cache.** Fingerprint pickle'a schematu (`yaml_util.py:108`) już zawiera listę
modeli, więc gdy `_get_modbus_device_models()` zacznie widzieć katalog
użytkownika, unieważnianie cache po dodaniu modelu działa bez dodatkowej pracy.

## 2. API

Jeden zasób REST w `boneio/webui/routes/modbus.py`:

| Metoda | Ścieżka | Zachowanie |
|---|---|---|
| `GET` | `/api/modbus/device_definitions` | lista wszystkich modeli (wbudowane + własne) z metadanymi, `source` i `used_by` (ID urządzeń z `config.yaml`) |
| `GET` | `/api/modbus/device_definitions/{key}` | pełny JSON dowolnego modelu — ścieżka forka: pobierz wbudowany, zmień nazwę, `POST` |
| `POST` | `/api/modbus/device_definitions` | tworzy własną; 409 gdy klucz zajęty (wbudowany lub własny) |
| `PUT` | `/api/modbus/device_definitions/{key}` | nadpisuje własną; 403 gdy klucz wskazuje na wbudowaną |
| `DELETE` | `/api/modbus/device_definitions/{key}` | 409 z listą `used_by`, gdy model jest używany; 403 dla wbudowanej |

Istniejące `/modbus/models` i `/modbus/models/{m}/entities` zostają (używa ich
`ThermostatForm.tsx:57`) — zmieniają tylko źródło danych na rejestr, więc od razu
widzą własne modele.

**Auto-reload.** `POST`/`PUT` kończą się wywołaniem nowej metody
`ManagerModbus.reload_modbus_model(model_key)`: znajduje koordynatory zbudowane
na tym modelu, zdejmuje ich HA discovery, usuwa je i odtwarza z niezmienionego
wpisu w `config.yaml`.

Istniejące `reload_modbus_devices()` (`core/manager/modbus.py:279`) tu nie
wystarcza — przebudowuje koordynator wyłącznie przy zmianie `area` lub `name`, a
edycja definicji nie zmienia `config.yaml`.

Wymaga to zapamiętania w koordynatorze klucza modelu: dziś `coordinator.py:118`
trzyma w `self._model` nazwę wyświetlaną z JSON-a (`self._db[MODEL]`), a nie
klucz pliku, więc dochodzi `self._model_key = model`.

Gdy przebudowa się nie powiedzie (np. rejestr, którego urządzenie nie
obsługuje), zapis pliku i tak zostaje utrwalony, a odpowiedź niesie ostrzeżenie —
inaczej strojenie rejestrów metodą prób i błędów potrafiłoby zablokować zapis.

**Import pliku.** Bez osobnego endpointu — frontend parsuje wgrany JSON i wysyła
go tym samym `POST`-em. Walidacja zostaje w jednym miejscu, a plik z forum i
definicja z kreatora przechodzą identyczną ścieżkę.

## 3. Walidacja — trzy warstwy

**Definicja urządzenia (POST/PUT).** Modele pydantic w nowym
`boneio/modbus/device_definition.py` (nie w routes — korzystają z nich też import
i testy): `ModbusDeviceDefinition` → `RegisterBlock` → `RegisterDef`.

Model pokrywa **wszystkie** pola występujące w 27 wbudowanych plikach, także te,
których kreator nie edytuje (`write_address`, `entity_type`, `payload_on`,
`payload_off`, `x_mapping`, `step`, `write_filters`, `entity_category`,
`ha_filter`, `additional_entities`) — jako opcjonalne. Dzięki temu import cudzego
pliku z encjami zapisywalnymi przechodzi i działa w runtime, choć kreator pokaże
do edycji tylko część pól.

`extra="forbid"`, żeby literówka w nazwie pola nie przeszła po cichu i nie
objawiła się dopiero brakiem encji.

Kotwicą jest test parametryzowany po wszystkich wbudowanych JSON-ach: każdy musi
przejść walidację tym modelem. Nowe wbudowane urządzenie z nieznanym polem od
razu zapali test.

**Konfiguracja (cerberus).** `_get_modbus_device_models()` przechodzi na rejestr,
więc `allowed` dla pola `model` obejmuje własne modele i `config.yaml` je
przepuszcza.

**JSON Schema dla edytora.** Statyczny mount `/schema` (`webui/app.py:796,891`)
zostaje zastąpiony routerem czytającym te same pliki z dysku i łatającym w locie
`enum` pola `modbus_devices[].model` listą z rejestru. Router zamiast wyjątku
zarejestrowanego przed mountem — dwie ścieżki serwowania tego samego katalogu to
subtelność kolejności rejestracji, którą potem trudno zdiagnozować. Nazwa pliku
dopasowywana do listy plików faktycznie obecnych w katalogu, więc nie ma miejsca
na wyjście poza niego.

## 4. UI

**Round-trip bez strat.** `parseDeviceConfig` (`ModbusDeviceCreator/types.ts:105`)
zachowuje dziś tylko pola, które kreator umie edytować — import cudzego pliku i
zapis skasowałby encje zapisywalne oraz `additional_entities`.

`Register` w `types.ts` dostaje pole `passthrough: Record<string, unknown>` na
nieedytowalne pola rejestru, a `CreatorState` — analogiczne na nieznane pola
najwyższego poziomu i całe `additional_entities`. `parseDeviceConfig` zbiera do
nich resztę, `generateJSON()` rozwija z powrotem. Kreator pokazuje baner: „ta
definicja zawiera encje sterujące, których kreator nie edytuje — zostaną
zachowane".

**Kreator** (`ModbusDeviceCreator`, wpięty w `ModbusHelper.tsx:1195`):

- `DeviceInfoSection` zyskuje `manufacturer`, `description`, `default_address`,
  `default_update_interval` (kategoria już jest); `generateJSON()` je emituje
- nowy przycisk **Zapisz na urządzeniu** obok istniejących Pobierz/Kopiuj — te
  zostają, bo dzielenie się plikiem to nadal sensowny scenariusz
- **Wczytaj model** — lista wbudowanych i własnych; wczytanie wbudowanego czyści
  klucz pliku i wymusza nową nazwę (fork), wczytanie własnego wchodzi w tryb
  edycji (`PUT`)
- draft w `localStorage` zostaje bez zmian; po udanym zapisie jest czyszczony

**Lista własnych definicji.** Nowa sekcja w `ModbusHelper` obok kreatora: klucz,
model, producent, kategoria, liczba urządzeń w użyciu. Akcje: Edytuj, Duplikuj,
Pobierz, Usuń — Usuń nieaktywne gdy `used_by` niepuste, z wypisaniem blokujących
urządzeń.

**Katalog w kreatorze urządzeń.** Nowy hook `useModbusCatalog()`: startuje z
wygenerowanego `MODBUS_DEVICE_CATALOG` (natychmiastowy render, zero migotania),
po odpowiedzi `/api/modbus/device_definitions` scala i oznacza własne
znacznikiem. Na hook przechodzą `AddModbusDeviceWizard.tsx:189` i
`ModbusHelper.tsx:1224`. Statyczny katalog zostaje jako fallback, więc awaria
endpointu degraduje UI do dzisiejszego zachowania zamiast do pustej listy.

**i18n**: komplet kluczy `pl` i `en` zgodnie z układem `frontend/src/locales/`.

## 5. Testy

Kolejność TDD: test czerwony przed implementacją każdego elementu.

**Backend**

- `tests/unit/modbus/test_device_registry.py` — listowanie wbudowanych,
  listowanie własnych, kolizja klucza (wbudowany wygrywa + ostrzeżenie),
  nieznany klucz → `ModelNotFoundError`, odrzucenie kluczy z `../` i wielkimi
  literami, wykrycie nowego pliku po zmianie `mtime`, `configure(None)` → tylko
  wbudowane
- `tests/unit/modbus/test_device_definition.py` — parametryzowany po wszystkich
  wbudowanych JSON-ach: każdy przechodzi walidację pydantic; osobno odrzucenie
  nieznanego pola i pustego `registers_base`
- `tests/unit/webui/test_modbus_device_definitions.py` — CRUD przez `TestClient`
  na tymczasowym katalogu: duplikat 409, edycja wbudowanej 403, usunięcie
  używanej 409 z `used_by`, usunięcie nieużywanej 200, `POST` woła
  `reload_modbus_model`, nieudany reload nie wycofuje zapisu
- `tests/unit/webui/test_schema_router.py` — serwowany `config.schema.json` ma
  własny model w `enum`, nieznana nazwa pliku → 404
- `tests/unit/core/config/test_config_validation.py` — rozszerzenie:
  `config.yaml` z własnym modelem przechodzi walidację cerberus

**Frontend** (vitest, obok `frontend/src/components/UISettings/__tests__/modbusWizard.test.ts`)

- round-trip `parseDeviceConfig` → `generateJSON` na wbudowanych plikach z polami
  sterującymi (`esp32_relay_x4_modbus.json`, `thessla.json` z
  `additional_entities`) — wynik równoważny wejściu
- scalanie katalogu w `useModbusCatalog()` i degradacja do statycznego katalogu
  przy błędzie API

## 6. Zgodność wsteczna i ryzyka

**Zgodność.** Format `config.yaml` bez zmian. Instalacja bez katalogu własnych
zachowuje się dokładnie jak dziś (ścieżka `configure(None)`). Sygnatura
`open_json()` zostaje. Wygenerowany `modbusDeviceCatalog.ts` i jego generator
zostają, więc `modbusWizard.test.ts` przechodzi bez modyfikacji.

**Ryzyka**

- `bonecli modbus` nie ma dziś argumentu `-c/--config` (`bonecli.py:63`), więc
  samo z siebie nie znajdzie katalogu użytkownika. Dokładamy tam `-c/--config` z
  tym samym domyślnym `./config.yaml` co `run` — inaczej narzędzie CLI widziałoby
  inny zestaw modeli niż WebUI.
- Wydajność na BeagleBone: rejestr trzyma indeks w pamięci; przy braku katalogu
  własnych koszt startu nie zmienia się względem dzisiejszego.

**Dokumentacja.** `docs/MODBUS_CUSTOM_DEVICES.md` — format pliku, lokalizacja,
fork wbudowanego, ograniczenia kreatora. Commity konwencjonalne `feat(modbus):`,
changelog PL/EN generuje release-please.
