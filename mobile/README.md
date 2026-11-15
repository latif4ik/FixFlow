# FixFlow Tech (Flutter, Android)

Technician app for FixFlow. See `ARCHITECTURE_NOTES.md` for the design.

## Prerequisites
- Flutter 3.47.9 stable (`export PATH="$HOME/Flutter/flutter/bin:$PATH"`); do not upgrade.
- Android SDK (`~/Library/Android/sdk`, licenses accepted).
- Java 21 (e.g. JetBrains JBR 21). If Gradle cannot find Java:
  `export JAVA_HOME=/Users/<you>/Library/Java/JavaVirtualMachines/jbr-21.0.11/Contents/Home`.
- Backend running at http://localhost:8000.

## API base URL (no secrets in the APK)
- Default: `http://10.0.2.2:8000` (Android emulator -> host machine).
- Compile time: `flutter build apk --debug --dart-define=API_BASE_URL=http://192.168.1.20:8000`
- Runtime (physical device): sign-in screen -> **Server** -> enter `http://<computer LAN IP>:8000` -> Save server
  (validated and persisted; "Use default" resets). Phone and computer must be on the same network.
- Cleartext HTTP is allowed (`android/.../network_security_config.xml`, `usesCleartextTraffic`) because the demo
  backend is local HTTP. Production must use HTTPS and remove it.

## Commands (run from `mobile/`)
```
flutter pub get
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build apk --debug          # -> build/app/outputs/flutter-apk/app-debug.apk
dart run build_runner build --delete-conflicting-outputs   # only after changing lib/core/db/tables.dart
LIVE_API_URL=http://localhost:8000 flutter test test/live   # real-backend offline-queue test (writes demo data)
```
Install on a running emulator/device: `adb install -r build/app/outputs/flutter-apk/app-debug.apk`.

## Demo technician accounts (password `demo1234`, disposable)
technician1@northwind.demo ... technician4@northwind.demo, technician1@alatoo.demo

## Build notes
- `pubspec.yaml` overrides `path_provider_foundation: 2.5.1`: newer versions pull the `objective_c` native-asset
  hook, which fails to link on hosts whose macOS Command Line Tools SDK is broken (macOS 27 beta SDK), breaking
  `flutter test`. The package is iOS/macOS-only and unused by this Android app.
- Fonts: platform default; nothing is fetched at runtime and no TTFs are bundled.
- App id `kg.fixflow.tech`, app name "FixFlow Tech".
