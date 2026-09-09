<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/blackbone-white.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/blackbone-black.svg">
    <img alt="BlackBone" src="docs/assets/blackbone-black.svg" width="320">
  </picture>
</p>

# BlackBone

**BlackBone** is a fork of [boneIO](https://boneio.eu) ([boneIO-eu/app_bbb](https://github.com/boneIO-eu/app_bbb)),
maintained by [SmartHome Wrocław](https://smarthome.wroclaw.pl). It adds features that
were missing in the original project, developed for and proven in real client installations.

> **smarthome-wroclaw is not affiliated with, endorsed by, or officially connected to the
> original boneIO authors.** BlackBone is released under the same GNU GPLv3 license as upstream.
>
> **Use at your own risk.** BlackBone is provided "as is", without warranty of any kind.
> smarthome-wroclaw accepts no liability for any damage or loss resulting from the use of this
> software.

## Example usage

```
boneio run -dd -c config.yaml
```

## Installation

```
sudo apt install -y libopenjp2-7-dev python3-venv libjpeg-dev docker-compose docker.io fonts-dejavu-core fonts-dejavu-extra libffi-dev libfreetype-dev libtiff6 libxcb1 mosquitto
mkdir ~/boneio
python3 -m venv ~/boneio/venv
source ~/boneio/venv/bin/activate
pip3 install --upgrade blackbone
cp ~/venv/lib/python3.13/site-packages/boneio/example_config/*.yaml ~/boneio/
```

Edit `config.yaml`

### Start app

```
source ~/boneio/venv/bin/activate
boneio run -c ~/boneio/config.yaml -dd
```

```bash
sed -i 's/^- id:/- name:/' *.yaml
```

## Upgrading an existing controller to BlackBone

Already have a controller running the original boneIO app? [SSH into it](https://boneio.eu/docs/black/advanced/ssh-connection)
and run the BlackBone installer:

```bash
ssh <user>@<controller-ip>
curl -fsSL https://raw.githubusercontent.com/smarthome-wroclaw/blackbone/main/install.sh | bash
```

The installer is interactive: it auto-detects your existing virtual environment, offers to back
up your current configuration and installed app before touching anything, installs BlackBone,
and restarts the `boneio` service. Your existing config files are left in place.

### Controllers running a pre-0.1 BlackBone build

BlackBone restarted its version numbering at `0.1.0`, below the `1.x` line inherited from boneIO.
A controller still running an early BlackBone build (for example `1.6.0.dev1`) therefore never
sees newer releases under **System → Software Update**: pip treats `0.1.x` as a downgrade. Upgrade
such a controller once over SSH:

```bash
"$HOME/boneio/venv/bin/pip" install --force-reinstall blackbone
sudo systemctl restart boneio
```

From then on in-app updates work normally.

## Returning to the original boneIO app

The migration is reversible. The safest option is to restore the application backup created by
the BlackBone installer. This returns the app to the exact version installed before migration.

SSH into the controller and set the paths below. The examples use the default locations. If the
installer reported different paths, use those instead. Replace the timestamp in `BACKUP_DIR` with
the directory created during migration.

```bash
VENV_DIR="$HOME/boneio/venv"
BACKUP_DIR="$HOME/boneio/backups/blackbone_migration_YYYYMMDD_HHMMSS"
APP_BACKUP="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'stock_black_app_*.tar.gz' -print -quit)"
test -n "$APP_BACKUP" || { echo "Application backup not found"; exit 1; }

sudo systemctl stop boneio
"$VENV_DIR/bin/pip" uninstall --yes blackbone
tar -C "$VENV_DIR" -xzf "$APP_BACKUP"
```

The installer does not change your YAML configuration. If you changed it after migration and also
want to restore the old configuration, inspect and extract its backup before starting the service.
Extraction overwrites YAML files with their backed-up copies.

```bash
CONFIG_BACKUP="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'configuration_*.tar.gz' -print -quit)"
test -n "$CONFIG_BACKUP" || { echo "Configuration backup not found"; exit 1; }
tar -tzf "$CONFIG_BACKUP"
tar -C "$(dirname "$VENV_DIR")" -xzf "$CONFIG_BACKUP"
```

Verify the restored package, then start the service:

```bash
"$VENV_DIR/bin/python" -c 'from importlib.metadata import version; print(version("boneio"))'
"$VENV_DIR/bin/pip" check
sudo systemctl start boneio
sudo systemctl is-active boneio
```

If you did not create an application backup, reinstall the latest official boneIO release from
PyPI instead:

```bash
VENV_DIR="$HOME/boneio/venv"
sudo systemctl stop boneio
"$VENV_DIR/bin/pip" uninstall --yes blackbone
"$VENV_DIR/bin/pip" install --upgrade --force-reinstall boneio
sudo systemctl start boneio
sudo systemctl is-active boneio
```

To install a specific official release, use `boneio==VERSION` instead of `boneio`. Review the
[official boneIO releases](https://github.com/boneIO-eu/app_black/releases) and
[update instructions](https://boneio.eu/en/docs/black/products/black_32x10a/software_setup/update-controller)
before choosing a version.

## Contributing

Found a bug or have a feature you'd like to see? Issues and pull requests are welcome at
[smarthome-wroclaw/blackbone](https://github.com/smarthome-wroclaw/blackbone).

---

## Polski

**BlackBone** to fork [boneIO](https://boneio.eu) ([boneIO-eu/app_bbb](https://github.com/boneIO-eu/app_bbb)),
utrzymywany przez [SmartHome Wrocław](https://smarthome.wroclaw.pl). Dodaje funkcje,
których brakowało w oryginalnym projekcie, wypracowane i sprawdzone w realnych instalacjach u
klientów.

> **smarthome-wroclaw nie jest powiązane z autorami oryginalnej aplikacji boneIO ani przez nich
> wspierane.** BlackBone jest wydawane na tej samej licencji GNU GPLv3 co projekt źródłowy.
>
> **Używasz na własną odpowiedzialność.** BlackBone jest dostarczane w stanie „tak jak jest",
> bez żadnych gwarancji. smarthome-wroclaw nie ponosi odpowiedzialności za jakiekolwiek szkody
> lub straty wynikające z użytkowania tego oprogramowania.

### Przykład użycia

```
boneio run -dd -c config.yaml
```

### Instalacja

```
sudo apt install -y libopenjp2-7-dev python3-venv libjpeg-dev docker-compose docker.io fonts-dejavu-core fonts-dejavu-extra libffi-dev libfreetype-dev libtiff6 libxcb1 mosquitto
mkdir ~/boneio
python3 -m venv ~/boneio/venv
source ~/boneio/venv/bin/activate
pip3 install --upgrade blackbone
cp ~/venv/lib/python3.13/site-packages/boneio/example_config/*.yaml ~/boneio/
```

Edytuj `config.yaml`

#### Uruchomienie aplikacji

```
source ~/boneio/venv/bin/activate
boneio run -c ~/boneio/config.yaml -dd
```

```bash
sed -i 's/^- id:/- name:/' *.yaml
```

### Aktualizacja istniejącego sterownika do BlackBone

Masz już sterownik z zainstalowaną oryginalną aplikacją boneIO? [Połącz się z nim przez SSH](https://boneio.eu/pl/docs/black/advanced/ssh-connection)
i uruchom instalator BlackBone:

```bash
ssh <user>@<adres-sterownika>
curl -fsSL https://raw.githubusercontent.com/smarthome-wroclaw/blackbone/main/install.sh | bash
```

Instalator działa interaktywnie: sam wykrywa istniejące środowisko wirtualne, proponuje kopię
zapasową aktualnej konfiguracji i zainstalowanej aplikacji zanim cokolwiek zmieni, instaluje
BlackBone i restartuje usługę `boneio`. Istniejące pliki konfiguracyjne pozostają nietknięte.

#### Sterowniki z buildem BlackBone sprzed 0.1

BlackBone zaczyna numerację wersji od `0.1.0`, czyli poniżej linii `1.x` odziedziczonej po boneIO.
Sterownik z wczesnym buildem BlackBone (na przykład `1.6.0.dev1`) nigdy nie zobaczy więc nowszych
wydań w **System → Aktualizacja oprogramowania** — pip traktuje `0.1.x` jako cofnięcie wersji. Taki
sterownik podnieś jednorazowo przez SSH:

```bash
"$HOME/boneio/venv/bin/pip" install --force-reinstall blackbone
sudo systemctl restart boneio
```

Od tego momentu aktualizacje z poziomu aplikacji działają normalnie.

### Powrót do oryginalnej aplikacji boneIO

Migrację można cofnąć. Najbezpieczniej przywrócić kopię aplikacji utworzoną przez instalator
BlackBone. Pozwala to wrócić dokładnie do wersji zainstalowanej przed migracją.

Połącz się ze sterownikiem przez SSH i ustaw poniższe ścieżki. Przykład używa domyślnych
lokalizacji. Jeżeli instalator wyświetlił inne ścieżki, użyj ich. W `BACKUP_DIR` zastąp znacznik
czasu nazwą katalogu utworzonego podczas migracji.

```bash
VENV_DIR="$HOME/boneio/venv"
BACKUP_DIR="$HOME/boneio/backups/blackbone_migration_YYYYMMDD_HHMMSS"
APP_BACKUP="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'stock_black_app_*.tar.gz' -print -quit)"
test -n "$APP_BACKUP" || { echo "Nie znaleziono kopii aplikacji"; exit 1; }

sudo systemctl stop boneio
"$VENV_DIR/bin/pip" uninstall --yes blackbone
tar -C "$VENV_DIR" -xzf "$APP_BACKUP"
```

Instalator nie zmienia konfiguracji YAML. Jeśli konfiguracja została zmieniona po migracji i
chcesz również przywrócić jej starszą wersję, sprawdź i rozpakuj kopię przed uruchomieniem usługi.
Rozpakowanie nadpisze pliki YAML ich kopiami zapasowymi.

```bash
CONFIG_BACKUP="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'configuration_*.tar.gz' -print -quit)"
test -n "$CONFIG_BACKUP" || { echo "Nie znaleziono kopii konfiguracji"; exit 1; }
tar -tzf "$CONFIG_BACKUP"
tar -C "$(dirname "$VENV_DIR")" -xzf "$CONFIG_BACKUP"
```

Sprawdź przywrócony pakiet, a następnie uruchom usługę:

```bash
"$VENV_DIR/bin/python" -c 'from importlib.metadata import version; print(version("boneio"))'
"$VENV_DIR/bin/pip" check
sudo systemctl start boneio
sudo systemctl is-active boneio
```

Jeżeli kopia aplikacji nie została utworzona, zainstaluj najnowsze oficjalne wydanie boneIO z
PyPI:

```bash
VENV_DIR="$HOME/boneio/venv"
sudo systemctl stop boneio
"$VENV_DIR/bin/pip" uninstall --yes blackbone
"$VENV_DIR/bin/pip" install --upgrade --force-reinstall boneio
sudo systemctl start boneio
sudo systemctl is-active boneio
```

Aby zainstalować wybrane oficjalne wydanie, użyj `boneio==WERSJA` zamiast `boneio`. Przed wyborem
wersji sprawdź [oficjalne wydania boneIO](https://github.com/boneIO-eu/app_black/releases) oraz
[instrukcję aktualizacji](https://boneio.eu/pl/docs/black/products/black_32x10a/software_setup/update-controller).

### Kontrybuowanie

Znalazłeś błąd albo masz pomysł na funkcję? Zgłoszenia (issues) i pull requesty są mile widziane
w repozytorium [smarthome-wroclaw/blackbone](https://github.com/smarthome-wroclaw/blackbone).
