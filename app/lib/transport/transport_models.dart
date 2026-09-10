enum TransportState {
  idle,
  preparing,
  permissionRequired,
  radioRequired,
  scanning,
  connecting,
  connected,
  unsupported,
  error,
}

enum MessageDelivery { sending, sent, delivered, failed, received }

class ReachableDevice {
  const ReachableDevice({
    required this.id,
    required this.name,
    required this.isConnected,
    required this.isConnecting,
  });

  final String id;
  final String name;
  final bool isConnected;
  final bool isConnecting;
}

class DirectMessage {
  DirectMessage({
    required this.id,
    required this.peerId,
    required this.text,
    required this.sentAt,
    required this.outgoing,
    required this.delivery,
  });

  final String id;
  final String peerId;
  final String text;
  final DateTime sentAt;
  final bool outgoing;
  MessageDelivery delivery;
}

class TransportSettings {
  int minimumSendBattery = 10;
  int maximumMessageBytes = 2048;
  bool deliveryReceipts = true;
}
