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
    this.trustScore = 1.0,
    this.hopDistance = 1,
  });

  final String id;
  final String name;
  final bool isConnected;
  final bool isConnecting;
  final double trustScore;
  final int hopDistance;
}

class MeshPacketHeader {
  const MeshPacketHeader({
    required this.sourceId,
    required this.destinationId,
    required this.packetId,
    required this.ttl,
    required this.hopCount,
    required this.payloadSizeBytes,
    required this.routeHistory,
    required this.isLargePacket,
  });

  final String sourceId;
  final String destinationId;
  final String packetId;
  final int ttl;
  final int hopCount;
  final int payloadSizeBytes;
  final List<String> routeHistory;
  final bool isLargePacket;
}

class DirectMessage {
  DirectMessage({
    required this.id,
    required this.peerId,
    required this.text,
    required this.sentAt,
    required this.outgoing,
    required this.delivery,
    this.meshHeader,
    this.failureReason,
  });

  final String id;
  final String peerId;
  final String text;
  final DateTime sentAt;
  final bool outgoing;
  MessageDelivery delivery;
  final MeshPacketHeader? meshHeader;
  String? failureReason;
}

class TransportSettings {
  // EAURP 20% energy-gating threshold (base.pdf 3.5)
  int minimumSendBattery = 20;
  int maximumMessageBytes = 2048;
  bool deliveryReceipts = true;

  // AR-EAURP Threat Model & Protocol Emulation
  bool simulateGrayHoleDrop = false; // Drops large data packets (>= 700B)
  int grayHoleThresholdBytes = 700;
  bool arEaurpTrustGating = true;
}
