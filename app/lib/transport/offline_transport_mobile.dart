import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:battery_plus/battery_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:nearby_service/nearby_service.dart';

import 'transport_models.dart';

class NearbyTransport extends ChangeNotifier {
  final settings = TransportSettings();
  final List<ReachableDevice> peers = [];
  final List<DirectMessage> messages = [];
  final Map<String, String> knownPeerNames = {};

  final _battery = Battery();
  final Map<String, NearbyDevice> _nativePeers = {};
  NearbyService? _service;
  NearbyDevice? _connectedDevice;
  StreamSubscription<List<NearbyDevice>>? _peersSubscription;
  StreamSubscription<NearbyDevice?>? _connectionSubscription;
  StreamSubscription<BatteryState>? _batterySubscription;
  bool _channelStarted = false;
  bool _initialized = false;

  TransportState state = TransportState.idle;
  String? errorMessage;
  String? connectedPeerId;
  int batteryLevel = 100;
  bool browserMode = true;

  bool get isApple => Platform.isIOS || Platform.isMacOS;
  bool get isSupported => Platform.isAndroid || Platform.isIOS;
  bool get isConnected => state == TransportState.connected;
  bool get canSend =>
      isConnected && batteryLevel >= settings.minimumSendBattery;

  ReachableDevice? get connectedPeer {
    for (final peer in peers) {
      if (peer.id == connectedPeerId) return peer;
    }
    if (_connectedDevice == null) return null;
    return _toPeer(_connectedDevice!);
  }

  String peerName(String id) => knownPeerNames[id] ?? 'Nearby device';

  @override
  void dispose() {
    _peersSubscription?.cancel();
    _connectionSubscription?.cancel();
    _batterySubscription?.cancel();
    _service?.endCommunicationChannel();
    _service?.stopDiscovery();
    super.dispose();
  }

  Future<void> initialize() async {
    if (_initialized || !isSupported) {
      if (!isSupported) state = TransportState.unsupported;
      notifyListeners();
      return;
    }
    state = TransportState.preparing;
    notifyListeners();
    try {
      await refreshBattery();
      _batterySubscription = _battery.onBatteryStateChanged.listen((_) {
        refreshBattery();
      });
      _service = NearbyService.getInstance(
        logLevel: kDebugMode
            ? NearbyServiceLogLevel.info
            : NearbyServiceLogLevel.error,
      );
      final model = await _service!.getPlatformModel();
      await _service!.initialize(
        data: NearbyInitializeData(
          darwinDeviceName: model == null ? 'RelayMesh' : 'RelayMesh · $model',
        ),
      );
      if (Platform.isAndroid) {
        final granted = await _service!.android!.requestPermissions();
        if (!granted) {
          state = TransportState.permissionRequired;
          return;
        }
        final enabled = await _service!.android!.checkWifiService();
        if (!enabled) {
          state = TransportState.radioRequired;
          return;
        }
      }
      _initialized = true;
      state = TransportState.idle;
    } catch (error) {
      state = TransportState.error;
      errorMessage = _readableError(error);
    } finally {
      notifyListeners();
    }
  }

  Future<void> startDiscovery() async {
    if (!_initialized) await initialize();
    if (!_initialized || _service == null) return;
    try {
      errorMessage = null;
      await _peersSubscription?.cancel();
      _peersSubscription = _service!.getPeersStream().listen(
        _replacePeers,
        onError: (Object error) => _setError(error),
      );
      final started = await _service!.discover();
      state = started ? TransportState.scanning : TransportState.error;
      if (!started) {
        errorMessage = 'The phone could not start nearby discovery.';
      }
    } catch (error) {
      _setError(error);
    }
    notifyListeners();
  }

  Future<void> stopDiscovery() async {
    try {
      await _service?.stopDiscovery();
      await _peersSubscription?.cancel();
      _peersSubscription = null;
      if (!isConnected) state = TransportState.idle;
    } catch (error) {
      _setError(error);
    }
    notifyListeners();
  }

  Future<void> setBrowserMode(bool value) async {
    if (!isApple || browserMode == value) return;
    await stopDiscovery();
    browserMode = value;
    _service?.darwin?.setIsBrowser(value: value);
    peers.clear();
    _nativePeers.clear();
    notifyListeners();
    await startDiscovery();
  }

  Future<void> connect(ReachableDevice peer) async {
    final native = _nativePeers[peer.id];
    if (native == null || _service == null) return;
    state = TransportState.connecting;
    connectedPeerId = peer.id;
    errorMessage = null;
    notifyListeners();
    try {
      await _connectionSubscription?.cancel();
      _connectionSubscription = _service!
          .getConnectedDeviceStreamById(peer.id)
          .listen(
            _handleConnection,
            onError: (Object error) => _setError(error),
          );
      final requested = await _service!.connectById(peer.id);
      if (!requested) throw StateError('Connection request was rejected.');
    } catch (error) {
      _setError(error);
    }
  }

  Future<void> disconnect() async {
    final id = connectedPeerId;
    try {
      await _service?.endCommunicationChannel();
      await _service?.disconnectById(id);
    } catch (error) {
      errorMessage = _readableError(error);
    }
    await _connectionSubscription?.cancel();
    _connectionSubscription = null;
    _connectedDevice = null;
    connectedPeerId = null;
    _channelStarted = false;
    state = TransportState.idle;
    notifyListeners();
  }

  Future<bool> sendMessage(String text) async {
    final peer = _connectedDevice;
    if (peer == null || _service == null || !canSend) return false;
    if (utf8.encode(text).length > settings.maximumMessageBytes) {
      errorMessage =
          'This message exceeds the ${settings.maximumMessageBytes}-byte limit.';
      notifyListeners();
      return false;
    }
    final request = NearbyMessageTextRequest.create(value: text);
    final local = DirectMessage(
      id: request.id,
      peerId: peer.info.id,
      text: text,
      sentAt: DateTime.now(),
      outgoing: true,
      delivery: MessageDelivery.sending,
    );
    messages.add(local);
    notifyListeners();
    try {
      final sent = await _service!.send(
        OutgoingNearbyMessage(content: request, receiver: peer.info),
      );
      local.delivery = sent ? MessageDelivery.sent : MessageDelivery.failed;
      notifyListeners();
      return sent;
    } catch (error) {
      local.delivery = MessageDelivery.failed;
      errorMessage = _readableError(error);
      notifyListeners();
      return false;
    }
  }

  Future<void> openRadioSettings() async => _service?.openServicesSettings();

  Future<void> refreshBattery() async {
    try {
      batteryLevel = await _battery.batteryLevel;
      notifyListeners();
    } catch (_) {
      batteryLevel = 100;
    }
  }

  void settingsChanged() => notifyListeners();

  List<DirectMessage> messagesFor(String peerId) =>
      messages.where((message) => message.peerId == peerId).toList();

  void _replacePeers(List<NearbyDevice> nativePeers) {
    knownPeerNames.addEntries(
      nativePeers.map((peer) => MapEntry(peer.info.id, peer.info.displayName)),
    );
    _nativePeers
      ..clear()
      ..addEntries(nativePeers.map((peer) => MapEntry(peer.info.id, peer)));
    peers
      ..clear()
      ..addAll(
        nativePeers
            .where(
              (peer) => !peer.status.isUnavailable && !peer.status.isFailed,
            )
            .map(_toPeer),
      );
    notifyListeners();
  }

  ReachableDevice _toPeer(NearbyDevice device) => ReachableDevice(
    id: device.info.id,
    name: device.info.displayName,
    isConnected: device.status.isConnected,
    isConnecting: device.status.isConnecting,
  );

  Future<void> _handleConnection(NearbyDevice? device) async {
    if (device == null) {
      if (isConnected) await disconnect();
      return;
    }
    _connectedDevice = device;
    connectedPeerId = device.info.id;
    if (device.status.isConnected && !_channelStarted) {
      _channelStarted = true;
      await _startCommunicationChannel(device);
    } else if (device.status.isConnecting) {
      state = TransportState.connecting;
      notifyListeners();
    }
  }

  Future<void> _startCommunicationChannel(NearbyDevice device) async {
    try {
      await _service!.startCommunicationChannel(
        NearbyCommunicationChannelData(
          device.info.id,
          messagesListener: NearbyServiceMessagesListener(
            onCreated: () {
              state = TransportState.connected;
              notifyListeners();
            },
            onData: _handleIncoming,
            onError: (Object error, [StackTrace? stack]) => _setError(error),
          ),
        ),
      );
      state = TransportState.connected;
    } catch (error) {
      _channelStarted = false;
      _setError(error);
    }
    notifyListeners();
  }

  void _handleIncoming(ReceivedNearbyMessage message) {
    message.content.byType(
      onTextRequest: (request) {
        messages.add(
          DirectMessage(
            id: request.id,
            peerId: message.sender.id,
            text: request.value,
            sentAt: DateTime.now(),
            outgoing: false,
            delivery: MessageDelivery.received,
          ),
        );
        if (settings.deliveryReceipts) {
          _service!.send(
            OutgoingNearbyMessage(
              content: NearbyMessageTextResponse(id: request.id),
              receiver: message.sender,
            ),
          );
        }
      },
      onTextResponse: (response) {
        for (final item in messages) {
          if (item.id == response.id && item.outgoing) {
            item.delivery = MessageDelivery.delivered;
          }
        }
      },
    );
    notifyListeners();
  }

  void _setError(Object error) {
    state = TransportState.error;
    errorMessage = _readableError(error);
    notifyListeners();
  }

  String _readableError(Object error) {
    final value = error.toString().replaceFirst('Exception: ', '');
    return value.length > 140 ? '${value.substring(0, 140)}…' : value;
  }
}
