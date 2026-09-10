import 'package:flutter/foundation.dart';

import 'transport_models.dart';

class NearbyTransport extends ChangeNotifier {
  final settings = TransportSettings();
  final List<ReachableDevice> peers = [];
  final List<DirectMessage> messages = [];
  final Map<String, String> knownPeerNames = {};

  TransportState state = TransportState.unsupported;
  String? errorMessage;
  String? connectedPeerId;
  int batteryLevel = 100;
  bool browserMode = true;

  bool get isApple => false;
  bool get isSupported => false;
  bool get isConnected => false;
  bool get canSend => false;
  ReachableDevice? get connectedPeer => null;
  String peerName(String id) => knownPeerNames[id] ?? 'Nearby device';

  Future<void> initialize() async => notifyListeners();
  Future<void> startDiscovery() async => notifyListeners();
  Future<void> stopDiscovery() async => notifyListeners();
  Future<void> setBrowserMode(bool value) async {
    browserMode = value;
    notifyListeners();
  }

  Future<void> connect(ReachableDevice peer) async {}
  Future<void> disconnect() async {}
  Future<bool> sendMessage(String text) async => false;
  Future<void> openRadioSettings() async {}
  Future<void> refreshBattery() async {}
  void settingsChanged() => notifyListeners();

  List<DirectMessage> messagesFor(String peerId) =>
      messages.where((message) => message.peerId == peerId).toList();
}
