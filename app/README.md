# RelayMesh

RelayMesh is a Flutter peer-to-peer text messenger for nearby phones. It sends
text directly between devices without a backend, mobile data, internet, or a
Wi-Fi router.

## Real transport

- **Android to Android:** Wi-Fi Direct. The Wi-Fi radio must be enabled, but the
  phones do not join a Wi-Fi network and no internet connection is used.
- **iPhone to iPhone / Apple device:** Multipeer Connectivity. Apple chooses
  peer-to-peer Wi-Fi or Bluetooth; it can operate with Wi-Fi turned off.
- Android and Apple devices cannot currently communicate with each other
  because these platform transports use different protocols.
- Chrome is UI preview only and cannot discover physical peers.

Only devices returned by the operating system's live peer-discovery stream are
shown. There are no generated devices or simulated deliveries.

## Run on the connected iPhone

From the repository root:

```bash
cd app
flutter run -d 00008150-001C212836C0401C
```

To test communication, install and run the app on a second iPhone. On one phone
open **Nearby devices → Find**. On the other select **Be visible**. Connect,
accept the invitation, and open the chat.

## Run on Android

Connect a physical Android phone with USB debugging enabled, then run:

```bash
cd app
flutter devices
flutter run -d <android-device-id>
```

Wi-Fi Direct is normally unavailable in Android emulators, so two physical
Android phones are required for an end-to-end test. If the Android build needs
SDK setup, first run `flutter doctor --android-licenses`.

## Browser preview

```bash
cd app
flutter run -d chrome
```

## Independent settings

- minimum actual battery level required to send
- maximum UTF-8 message size
- delivery receipts

Each setting is independent and changing one does not modify another.

## Verification

```bash
flutter analyze
flutter test
flutter build ios --debug --no-codesign
```

The senior notebook does not contain a physical communication medium. It is a
Python metric generator in which packet delivery is decided by random
probability, so none of its networking code is used by this application.
