# Changelog

## [2.2.0-alt1] - 2026-06-04

### Added

- Полная реализация pc-test на **Python 3**:
  - точка входа `pc-test`, главный цикл и CLI;
  - пакет `pc_test` в `%python3_sitelibdir` с модулями шагов (`pc_test/steps/`);
  - GUI: `pc_test/gui/forms.py` (tkinter, fallback yad/dialog);
  - конфигурация плана тестов: `pc_test/gui/config_forms.py`;
  - экспресс-тест: `pc_test/steps/express.py`;
  - автозапуск: `launcher.py`, `resume.py`.
- Зависимость RPM: `python3`, `python3-base`.
- Список сохраняемых настроек: `pc_test/internal_vars.py`.
- Из upstream 2.1.7: поддержка ALT SP 10.2.2, ALT Virtualization 11 PVE,
  улучшенная работа в Wayland-сессии.
- Из upstream 2.1.8: исправлены зависимости для экспресс-теста
  (`xdg-utils`, `pulseaudio-utils`).

### Changed

- `check-scripts.sh` проверяет Python (`compileall`) и только l10n `*.sh`.
- Desktop и autostart используют `launcher.py` / `resume.py`.
- Тонкие обёртки `launcher.sh` / `resume.sh` вызывают Python-скрипты.

### Removed

- Удалены устаревшие bash-модули: `common.sh`, `parser.sh`, `defaults.sh`,
  `internal.sh`, `step-gui.sh`, все `steps/*.sh` (логика перенесена в Python).
- Локализация по-прежнему в `l10n/*/*.sh` (загрузка через `pc_test/l10n.py`).
- Из upstream 2.1.7: удалены ссылки на заблокированные VK-видео.

[2.2.0-alt1]: https://github.com/klark973/pc-test/releases/tag/2.2.0-alt1

## [2.1.8-alt1] - 2026-03-23

### Fixed

- install dependencies for express test
- improved CHANGELOG

[2.1.8-alt1]: https://github.com/klark973/pc-test/releases/tag/2.1.8-alt1

## [2.1.7-alt1] - 2026-03-15

### Added

- support for ALT PVE 11 and ALT SP 10.2.2

### Fixed

- improved support of the wayland server

### Removed

- deleted links to blocked VK videos

[2.1.7-alt1]: https://github.com/klark973/pc-test/releases/tag/2.1.7-alt1

## [2.1.6-alt1] - 2025-09-08

### Fixed

- sudo configuration success check
- added the ability to cancel testing
- install dependencies for express test

## [2.1.5-alt1] - 2025-08-11

### Added

- support for ALT SP 10.2.1 distro
- support for archives c9f2 and c10f2

### Fixed

- improve generic way to detecting distro
- add workaround when system-report hangs
- express test: make checks more verbosely

### Removed

- support for UsrMerge in Sisyphus

## [2.1.4-alt2] - 2025-03-01

### Added

- Added 36 new video samples and switch to VK video

### Fixed

- Now the .config/autostart directory will be created automatically if it does not exist

[2.1.4-alt2]: https://github.com/klark973/pc-test/releases/tag/2.1.4-alt2

## [2.1.4-alt1] - 2025-02-10

### Added

- Added support for ALT Workstaion 11 (alpha)
- Added support for ALT Workstaion K 11 (alpha)
- Added support for Gnome Shell and KDE6 Plasma
- Added support for Wayland and PipeWire
- Added support for new Adwaita icon theme
- Added check to non-informative kernel messages

### Fixed

- Now used XDG_RUNTIME_DIR for collect some logs
- Completely removed control of the browser window
- Removed dependency on xdotool and wmctrl
- Fixed autostart on some distributions

[2.1.4-alt1]: https://github.com/klark973/pc-test/releases/tag/2.1.4-alt1

## [2.1.3-alt1] - 2025-02-02

### Added

- Added support for p11 and ALT SP 10.2 (c10f2)
- Added the ability to replace a set of videos
- Added 20 new video samples and switch to RuTube
- Added the ability to use custom sets of video

### Fixed

- Removed player control in the browser window
- Install some pulseaudio packages for sound tests
- Closed bug: https://bugzilla.altlinux.org/52843

[2.1.3-alt1]: https://github.com/klark973/pc-test/releases/tag/2.1.3-alt1

## [2.1.2-alt2] - 2024-11-28

### Fixed

- Added 15 sec timeout for slow Wi-Fi connections
- Do not check monitors for express testing anymore
- Added and increased timeouts between operations

[2.1.2-alt2]: https://github.com/klark973/pc-test/releases/tag/2.1.2-alt2

## [2.1.2-alt1] - 2024-06-26

### Added

- Ability to reset subtest results
- Possibility to retest a previously completed test
- Collect PulseAudio and PipeWire configuration

### Fixed

- Now all pc-test results are also saved
- Pack input data into gzip archives safer
- Show and save pc-test version earlier

[2.1.2-alt1]: https://github.com/klark973/pc-test/releases/tag/2.1.2-alt1

## [2.1.1-alt1] - 2024-06-16

### Added

- Test of CPU Performance Scaling modes according to section 10.1
- An express test according to section 9
- Possibility of manual testing
- Testing methodology v2.1 (HTML5) and Changelog
- Ability to use personal settings by the regular user
- Automatic OS updates are now disabled during testing
- Ability to show subtest results
- Many improvements in logging output

### Fixed

- Fix to not skip glmark test on ALT SP Server
- Fix a very strange fault when saving status
- Fix to reload en_US messages correctly

[2.1.1-alt1]: https://github.com/klark973/pc-test/releases/tag/2.1.1-alt1

## [2.1.0-alt5] - 2024-05-05

_Initial build for Sisyphus_.

[2.1.0-alt5]: https://github.com/klark973/pc-test/releases/tag/2.1.0-alt5

