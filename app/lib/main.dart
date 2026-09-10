import 'dart:convert';

import 'package:flutter/material.dart';

import 'transport/offline_transport.dart';
import 'transport/transport_models.dart';

void main() => runApp(const RelayMeshApp());

const signalBlue = Color(0xff2c6bed);
const pageColor = Color(0xfff7f7f8);
const darkInk = Color(0xff1b1b1f);

class RelayMeshApp extends StatelessWidget {
  const RelayMeshApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'RelayMesh',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: signalBlue,
          primary: signalBlue,
          surface: Colors.white,
        ),
        scaffoldBackgroundColor: pageColor,
        appBarTheme: const AppBarTheme(
          backgroundColor: pageColor,
          foregroundColor: darkInk,
          elevation: 0,
          centerTitle: false,
          titleTextStyle: TextStyle(
            color: darkInk,
            fontSize: 25,
            fontWeight: FontWeight.w800,
            letterSpacing: -.5,
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xffeeeeef),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(22),
            borderSide: BorderSide.none,
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(22),
            borderSide: BorderSide.none,
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(22),
            borderSide: const BorderSide(color: signalBlue, width: 1.5),
          ),
        ),
      ),
      home: const MessengerHome(),
    );
  }
}

class MessengerHome extends StatefulWidget {
  const MessengerHome({super.key});

  @override
  State<MessengerHome> createState() => _MessengerHomeState();
}

class _MessengerHomeState extends State<MessengerHome> {
  final transport = NearbyTransport();
  final search = TextEditingController();
  var selectedPage = 0;

  @override
  void initState() {
    super.initState();
    transport.initialize();
    search.addListener(_refresh);
  }

  void _refresh() => setState(() {});

  @override
  void dispose() {
    search
      ..removeListener(_refresh)
      ..dispose();
    transport.dispose();
    super.dispose();
  }

  Future<void> _openNearby() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => NearbyDevicesPage(transport: transport),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: transport,
      builder: (context, _) => Scaffold(
        appBar: AppBar(
          title: Text(selectedPage == 0 ? 'RelayMesh' : 'Settings'),
          actions: [
            if (selectedPage == 0)
              IconButton(
                tooltip: 'Find nearby devices',
                onPressed: _openNearby,
                icon: const Icon(Icons.person_add_alt_1_outlined),
              ),
            const SizedBox(width: 8),
          ],
        ),
        body: AnimatedSwitcher(
          duration: const Duration(milliseconds: 220),
          child: selectedPage == 0
              ? _ChatsPage(
                  key: const ValueKey('chats'),
                  transport: transport,
                  search: search,
                  onFindNearby: _openNearby,
                )
              : _SettingsPage(
                  key: const ValueKey('settings'),
                  transport: transport,
                ),
        ),
        floatingActionButton: selectedPage == 0
            ? FloatingActionButton(
                key: const Key('newChatButton'),
                onPressed: _openNearby,
                backgroundColor: signalBlue,
                foregroundColor: Colors.white,
                child: const Icon(Icons.edit_outlined),
              )
            : null,
        bottomNavigationBar: NavigationBar(
          height: 68,
          selectedIndex: selectedPage,
          onDestinationSelected: (value) =>
              setState(() => selectedPage = value),
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.chat_bubble_outline),
              selectedIcon: Icon(Icons.chat_bubble),
              label: 'Chats',
            ),
            NavigationDestination(
              icon: Icon(Icons.settings_outlined),
              selectedIcon: Icon(Icons.settings),
              label: 'Settings',
            ),
          ],
        ),
      ),
    );
  }
}

class _ChatsPage extends StatelessWidget {
  const _ChatsPage({
    super.key,
    required this.transport,
    required this.search,
    required this.onFindNearby,
  });

  final NearbyTransport transport;
  final TextEditingController search;
  final VoidCallback onFindNearby;

  @override
  Widget build(BuildContext context) {
    final peerIds = <String>{
      if (transport.connectedPeerId != null) transport.connectedPeerId!,
      ...transport.messages.map((message) => message.peerId),
    };
    final query = search.text.trim().toLowerCase();
    final visibleIds = peerIds
        .where((id) => transport.peerName(id).toLowerCase().contains(query))
        .toList();

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 10),
          child: TextField(
            controller: search,
            decoration: const InputDecoration(
              hintText: 'Search',
              prefixIcon: Icon(Icons.search),
              isDense: true,
            ),
          ),
        ),
        _TransportBanner(transport: transport, onPressed: onFindNearby),
        Expanded(
          child: visibleIds.isEmpty
              ? _NoConversations(onFindNearby: onFindNearby)
              : ListView.separated(
                  padding: const EdgeInsets.only(top: 6),
                  itemCount: visibleIds.length,
                  separatorBuilder: (_, _) =>
                      const Divider(height: 1, indent: 82, endIndent: 16),
                  itemBuilder: (context, index) {
                    final id = visibleIds[index];
                    final messages = transport.messagesFor(id);
                    final last = messages.isEmpty ? null : messages.last;
                    final connected =
                        transport.connectedPeerId == id &&
                        transport.isConnected;
                    return ListTile(
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 5,
                      ),
                      leading: _Avatar(name: transport.peerName(id)),
                      title: Text(
                        transport.peerName(id),
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 17,
                        ),
                      ),
                      subtitle: Text(
                        last?.text ??
                            (connected
                                ? 'Connected directly'
                                : 'Not currently reachable'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: connected
                          ? const Icon(
                              Icons.circle,
                              size: 11,
                              color: Color(0xff26a269),
                            )
                          : null,
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => ChatPage(
                            transport: transport,
                            peerId: id,
                            peerName: transport.peerName(id),
                          ),
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}

class _TransportBanner extends StatelessWidget {
  const _TransportBanner({required this.transport, required this.onPressed});
  final NearbyTransport transport;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final (icon, title, subtitle, color) = switch (transport.state) {
      TransportState.connected => (
        Icons.bluetooth_connected,
        'Connected nearby',
        'Messages stay between the two phones',
        const Color(0xffe4f3ea),
      ),
      TransportState.scanning || TransportState.connecting => (
        Icons.radar,
        'Looking nearby',
        'Scanning device radios—no internet used',
        const Color(0xffe8efff),
      ),
      TransportState.unsupported => (
        Icons.phone_android,
        'Open this on a phone',
        'Chrome cannot discover nearby phones',
        const Color(0xfffff0d7),
      ),
      TransportState.radioRequired => (
        Icons.wifi_tethering_off,
        'Peer-to-peer radio is off',
        'Turn on Wi-Fi Direct; no router is needed',
        const Color(0xffffe5e2),
      ),
      TransportState.permissionRequired => (
        Icons.location_disabled_outlined,
        'Nearby permission required',
        'Grant access so reachable phones can appear',
        const Color(0xffffe5e2),
      ),
      TransportState.error => (
        Icons.error_outline,
        'Nearby connection needs attention',
        transport.errorMessage ?? 'Tap to retry',
        const Color(0xffffe5e2),
      ),
      _ => (
        Icons.wifi_off,
        'Offline ready',
        'Find a nearby phone to start a direct chat',
        const Color(0xffe8efff),
      ),
    };
    return InkWell(
      onTap: onPressed,
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: [
            Icon(icon, color: darkInk),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right),
          ],
        ),
      ),
    );
  }
}

class _NoConversations extends StatelessWidget {
  const _NoConversations({required this.onFindNearby});
  final VoidCallback onFindNearby;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(36),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 94,
              height: 94,
              decoration: const BoxDecoration(
                color: Color(0xffe8efff),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.forum_outlined,
                size: 45,
                color: signalBlue,
              ),
            ),
            const SizedBox(height: 22),
            const Text(
              'No conversations yet',
              style: TextStyle(fontSize: 21, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            const Text(
              'Find another phone running RelayMesh and connect directly.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.black54, height: 1.4),
            ),
            const SizedBox(height: 22),
            FilledButton.icon(
              onPressed: onFindNearby,
              icon: const Icon(Icons.radar),
              label: const Text('Find nearby devices'),
            ),
          ],
        ),
      ),
    );
  }
}

class NearbyDevicesPage extends StatefulWidget {
  const NearbyDevicesPage({super.key, required this.transport});
  final NearbyTransport transport;

  @override
  State<NearbyDevicesPage> createState() => _NearbyDevicesPageState();
}

class _NearbyDevicesPageState extends State<NearbyDevicesPage> {
  NearbyTransport get transport => widget.transport;

  @override
  void initState() {
    super.initState();
    if (transport.isSupported &&
        transport.state != TransportState.radioRequired &&
        transport.state != TransportState.permissionRequired) {
      transport.startDiscovery();
    }
  }

  Future<void> _connect(ReachableDevice peer) async {
    await transport.connect(peer);
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AnimatedBuilder(
        animation: transport,
        builder: (context, _) {
          final connected = transport.isConnected;
          final failed = transport.state == TransportState.error;
          return AlertDialog(
            title: Text(
              connected
                  ? 'Connected to ${peer.name}'
                  : failed
                  ? 'Could not connect'
                  : 'Connecting to ${peer.name}',
            ),
            content: Row(
              children: [
                if (!connected && !failed)
                  const Padding(
                    padding: EdgeInsets.only(right: 16),
                    child: SizedBox.square(
                      dimension: 24,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    ),
                  ),
                Expanded(
                  child: Text(
                    connected
                        ? 'A direct peer-to-peer radio channel is ready.'
                        : failed
                        ? transport.errorMessage ?? 'Connection failed.'
                        : 'Keep both phones nearby and accept the request on the other phone.',
                  ),
                ),
              ],
            ),
            actions: [
              if (!connected && !failed)
                TextButton(
                  onPressed: () async {
                    await transport.disconnect();
                    if (context.mounted) Navigator.pop(context);
                  },
                  child: const Text('Cancel'),
                ),
              if (failed)
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Close'),
                ),
              if (connected)
                FilledButton(
                  onPressed: () {
                    Navigator.pop(context);
                    Navigator.of(this.context).pushReplacement(
                      MaterialPageRoute<void>(
                        builder: (_) => ChatPage(
                          transport: transport,
                          peerId: peer.id,
                          peerName: peer.name,
                        ),
                      ),
                    );
                  },
                  child: const Text('Open chat'),
                ),
            ],
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: transport,
      builder: (context, _) => Scaffold(
        appBar: AppBar(
          title: const Text('Nearby devices'),
          actions: [
            if (transport.state == TransportState.scanning)
              IconButton(
                tooltip: 'Stop scanning',
                onPressed: transport.stopDiscovery,
                icon: const Icon(Icons.stop_circle_outlined),
              )
            else if (transport.isSupported)
              IconButton(
                tooltip: 'Scan again',
                onPressed: transport.startDiscovery,
                icon: const Icon(Icons.refresh),
              ),
          ],
        ),
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (transport.isApple)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 6, 16, 12),
                child: SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(
                      value: true,
                      icon: Icon(Icons.search),
                      label: Text('Find'),
                    ),
                    ButtonSegment(
                      value: false,
                      icon: Icon(Icons.visibility_outlined),
                      label: Text('Be visible'),
                    ),
                  ],
                  selected: {transport.browserMode},
                  onSelectionChanged: (value) =>
                      transport.setBrowserMode(value.first),
                ),
              ),
            _RadioExplanation(transport: transport),
            if (transport.state == TransportState.scanning ||
                transport.state == TransportState.connecting)
              const LinearProgressIndicator(minHeight: 2),
            Expanded(child: _deviceList()),
          ],
        ),
      ),
    );
  }

  Widget _deviceList() {
    if (!transport.isSupported) {
      return const _DiscoveryMessage(
        icon: Icons.phone_android,
        title: 'A physical phone is required',
        body:
            'Web browsers cannot access this peer-to-peer transport. Run RelayMesh on two Android phones or two Apple devices.',
      );
    }
    if (transport.state == TransportState.radioRequired ||
        transport.state == TransportState.permissionRequired) {
      return _DiscoveryMessage(
        icon: Icons.settings_suggest_outlined,
        title: transport.state == TransportState.radioRequired
            ? 'Enable the peer-to-peer radio'
            : 'Allow nearby-device access',
        body: transport.state == TransportState.radioRequired
            ? 'Android uses Wi-Fi Direct. The Wi-Fi radio must be on, but no router or internet connection is used.'
            : 'RelayMesh needs the system nearby/location permission to discover physical devices.',
        action: FilledButton(
          onPressed: transport.state == TransportState.radioRequired
              ? transport.openRadioSettings
              : transport.initialize,
          child: Text(
            transport.state == TransportState.radioRequired
                ? 'Open settings'
                : 'Request access',
          ),
        ),
      );
    }
    if (transport.peers.isEmpty) {
      final visibleCopy = transport.isApple && !transport.browserMode;
      return _DiscoveryMessage(
        icon: visibleCopy ? Icons.visibility_outlined : Icons.radar,
        title: visibleCopy
            ? 'Visible to nearby Apple devices'
            : 'No reachable devices yet',
        body: visibleCopy
            ? 'On the other Apple device, open RelayMesh and choose Find.'
            : 'Open RelayMesh on the other phone. Both devices must use the same platform family.',
        action: transport.state != TransportState.scanning
            ? FilledButton.icon(
                onPressed: transport.startDiscovery,
                icon: const Icon(Icons.refresh),
                label: const Text('Scan again'),
              )
            : null,
      );
    }
    return ListView.separated(
      itemCount: transport.peers.length,
      separatorBuilder: (_, _) => const Divider(height: 1, indent: 82),
      itemBuilder: (context, index) {
        final peer = transport.peers[index];
        return ListTile(
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 18,
            vertical: 7,
          ),
          leading: _Avatar(name: peer.name),
          title: Text(
            peer.name,
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
          ),
          subtitle: Text(
            peer.isConnected
                ? 'Connected'
                : peer.isConnecting
                ? 'Connecting…'
                : 'Reachable now',
          ),
          trailing: const Icon(Icons.chevron_right),
          onTap: peer.isConnecting ? null : () => _connect(peer),
        );
      },
    );
  }
}

class ChatPage extends StatefulWidget {
  const ChatPage({
    super.key,
    required this.transport,
    required this.peerId,
    required this.peerName,
  });

  final NearbyTransport transport;
  final String peerId;
  final String peerName;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final composer = TextEditingController();

  @override
  void dispose() {
    composer.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = composer.text.trim();
    if (text.isEmpty) return;
    composer.clear();
    await widget.transport.sendMessage(text);
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.transport,
      builder: (context, _) {
        final messages = widget.transport.messagesFor(widget.peerId);
        final connected =
            widget.transport.isConnected &&
            widget.transport.connectedPeerId == widget.peerId;
        return Scaffold(
          backgroundColor: Colors.white,
          appBar: AppBar(
            backgroundColor: Colors.white,
            titleSpacing: 0,
            title: Row(
              children: [
                _Avatar(name: widget.peerName, radius: 18),
                const SizedBox(width: 10),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.peerName,
                      style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      connected ? 'Connected directly' : 'Not reachable',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w400,
                        color: connected
                            ? const Color(0xff258b55)
                            : Colors.black45,
                      ),
                    ),
                  ],
                ),
              ],
            ),
            actions: [
              if (connected)
                IconButton(
                  tooltip: 'Disconnect',
                  onPressed: widget.transport.disconnect,
                  icon: const Icon(Icons.link_off),
                ),
              const SizedBox(width: 5),
            ],
          ),
          body: SafeArea(
            top: false,
            child: Column(
              children: [
                Container(
                  width: double.infinity,
                  color: const Color(0xfff1f4fb),
                  padding: const EdgeInsets.symmetric(
                    vertical: 7,
                    horizontal: 16,
                  ),
                  child: const Text(
                    'Direct peer-to-peer channel · no server or internet',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Color(0xff4f5f85)),
                  ),
                ),
                Expanded(
                  child: messages.isEmpty
                      ? _ChatIntro(name: widget.peerName)
                      : ListView.builder(
                          reverse: true,
                          padding: const EdgeInsets.fromLTRB(12, 18, 12, 10),
                          itemCount: messages.length,
                          itemBuilder: (context, index) => _MessageBubble(
                            message: messages[messages.length - 1 - index],
                          ),
                        ),
                ),
                _Composer(
                  controller: composer,
                  enabled: connected && widget.transport.canSend,
                  onSend: _send,
                  disabledReason: connected && !widget.transport.canSend
                      ? 'Battery is below the send limit'
                      : 'Connect to this device to send',
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.enabled,
    required this.onSend,
    required this.disabledReason,
  });
  final TextEditingController controller;
  final bool enabled;
  final VoidCallback onSend;
  final String disabledReason;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: TextField(
              key: const Key('messageField'),
              controller: controller,
              enabled: enabled,
              minLines: 1,
              maxLines: 5,
              decoration: InputDecoration(
                hintText: enabled ? 'RelayMesh message' : disabledReason,
                prefixIcon: const Icon(Icons.add_circle_outline),
              ),
            ),
          ),
          const SizedBox(width: 8),
          SizedBox.square(
            dimension: 48,
            child: FilledButton(
              key: const Key('sendButton'),
              onPressed: enabled ? onSend : null,
              style: FilledButton.styleFrom(
                padding: EdgeInsets.zero,
                shape: const CircleBorder(),
              ),
              child: const Icon(Icons.arrow_upward_rounded),
            ),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});
  final DirectMessage message;

  @override
  Widget build(BuildContext context) {
    final mine = message.outgoing;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 310),
        margin: EdgeInsets.only(
          left: mine ? 56 : 0,
          right: mine ? 0 : 56,
          bottom: 6,
        ),
        padding: const EdgeInsets.fromLTRB(13, 9, 11, 7),
        decoration: BoxDecoration(
          color: mine ? signalBlue : const Color(0xffe9e9eb),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(18),
            topRight: const Radius.circular(18),
            bottomLeft: Radius.circular(mine ? 18 : 5),
            bottomRight: Radius.circular(mine ? 5 : 18),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                message.text,
                style: TextStyle(
                  fontSize: 16,
                  color: mine ? Colors.white : darkInk,
                  height: 1.25,
                ),
              ),
            ),
            const SizedBox(height: 3),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  _time(message.sentAt),
                  style: TextStyle(
                    fontSize: 10,
                    color: mine ? Colors.white70 : Colors.black45,
                  ),
                ),
                if (mine) ...[
                  const SizedBox(width: 4),
                  Icon(
                    _deliveryIcon(message.delivery),
                    size: 13,
                    color: message.delivery == MessageDelivery.failed
                        ? const Color(0xffffc4be)
                        : Colors.white70,
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _SettingsPage extends StatelessWidget {
  const _SettingsPage({super.key, required this.transport});
  final NearbyTransport transport;

  @override
  Widget build(BuildContext context) {
    final settings = transport.settings;
    return ListView(
      padding: const EdgeInsets.only(bottom: 28),
      children: [
        _SettingsHeader(transport: transport),
        const _SectionLabel('OFFLINE TRANSPORT'),
        _SettingsTile(
          icon: Icons.radio_outlined,
          title: !transport.isSupported
              ? 'Physical phone required'
              : transport.isApple
              ? 'Multipeer Connectivity'
              : 'Wi-Fi Direct',
          subtitle: !transport.isSupported
              ? 'Browser preview cannot access peer-to-peer phone radios'
              : transport.isApple
              ? 'Peer-to-peer Wi-Fi or Bluetooth; no internet'
              : 'Direct radio link; no router or internet',
        ),
        const _SettingsTile(
          icon: Icons.devices_other,
          title: 'Reachable devices only',
          subtitle: 'The chat list never invents or simulates nearby phones',
        ),
        const _SectionLabel('INDEPENDENT LIMITS'),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Minimum battery to send',
                    style: TextStyle(fontWeight: FontWeight.w600),
                  ),
                  Text(
                    '${settings.minimumSendBattery}%',
                    style: const TextStyle(
                      color: signalBlue,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
              Slider(
                value: settings.minimumSendBattery.toDouble(),
                min: 0,
                max: 50,
                divisions: 10,
                onChanged: (value) {
                  settings.minimumSendBattery = value.round();
                  transport.settingsChanged();
                },
              ),
              const Text(
                'Uses this phone’s actual battery reading. It does not change any other setting.',
                style: TextStyle(fontSize: 12, color: Colors.black54),
              ),
            ],
          ),
        ),
        ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 20),
          leading: const Icon(Icons.data_object),
          title: const Text('Maximum message size'),
          subtitle: const Text('Independent byte limit per message'),
          trailing: DropdownButton<int>(
            value: settings.maximumMessageBytes,
            underline: const SizedBox.shrink(),
            items: const [512, 1024, 2048, 4096]
                .map(
                  (value) => DropdownMenuItem(
                    value: value,
                    child: Text(
                      '${value ~/ 1024 == 0 ? value : value ~/ 1024} ${value < 1024 ? 'B' : 'KB'}',
                    ),
                  ),
                )
                .toList(),
            onChanged: (value) {
              if (value == null) return;
              settings.maximumMessageBytes = value;
              transport.settingsChanged();
            },
          ),
        ),
        SwitchListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 20),
          secondary: const Icon(Icons.done_all),
          title: const Text('Delivery receipts'),
          subtitle: const Text(
            'Acknowledge messages after they reach this phone',
          ),
          value: settings.deliveryReceipts,
          onChanged: (value) {
            settings.deliveryReceipts = value;
            transport.settingsChanged();
          },
        ),
        const _SectionLabel('ABOUT THIS BUILD'),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: Text(
            'This build sends real text over a direct device-to-device link. The senior notebook did not implement any communication medium; it generated delivery metrics from random probability only.',
            style: TextStyle(color: Colors.black54, height: 1.45),
          ),
        ),
      ],
    );
  }
}

class _SettingsHeader extends StatelessWidget {
  const _SettingsHeader({required this.transport});
  final NearbyTransport transport;
  @override
  Widget build(BuildContext context) => Container(
    color: Colors.white,
    padding: const EdgeInsets.fromLTRB(20, 14, 20, 18),
    child: Row(
      children: [
        const _Avatar(name: 'My device', radius: 29),
        const SizedBox(width: 15),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'My device',
                style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700),
              ),
              Text(
                '${transport.batteryLevel}% battery · ${transport.isSupported ? 'phone radio available' : 'preview mode'}',
              ),
            ],
          ),
        ),
        IconButton(
          tooltip: 'Refresh battery',
          onPressed: transport.refreshBattery,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
  );
}

class _RadioExplanation extends StatelessWidget {
  const _RadioExplanation({required this.transport});
  final NearbyTransport transport;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(18, 4, 18, 14),
    child: Text(
      transport.isApple
          ? 'Only Apple devices physically discovered by Multipeer Connectivity appear here. Wi-Fi may be off; the framework can use Bluetooth.'
          : 'Only Android devices physically discovered through Wi-Fi Direct appear here. The radio must be on, but no access point or internet is used.',
      style: const TextStyle(color: Colors.black54, height: 1.4),
    ),
  );
}

class _DiscoveryMessage extends StatelessWidget {
  const _DiscoveryMessage({
    required this.icon,
    required this.title,
    required this.body,
    this.action,
  });
  final IconData icon;
  final String title;
  final String body;
  final Widget? action;
  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(36),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 58, color: signalBlue),
          const SizedBox(height: 18),
          Text(
            title,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          Text(
            body,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.black54, height: 1.45),
          ),
          if (action != null) ...[const SizedBox(height: 20), action!],
        ],
      ),
    ),
  );
}

class _ChatIntro extends StatelessWidget {
  const _ChatIntro({required this.name});
  final String name;
  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(34),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _Avatar(name: name, radius: 38),
          const SizedBox(height: 15),
          Text(
            name,
            style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 7),
          const Text(
            'You connected directly to this device. Messages do not pass through a server.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.black54, height: 1.4),
          ),
        ],
      ),
    ),
  );
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.name, this.radius = 25});
  final String name;
  final double radius;
  @override
  Widget build(BuildContext context) {
    final colors = [
      const Color(0xff5c6bc0),
      const Color(0xff00897b),
      const Color(0xff7e57c2),
      const Color(0xffef6c5b),
    ];
    final color =
        colors[name.codeUnits.fold(0, (a, b) => a + b) % colors.length];
    return CircleAvatar(
      radius: radius,
      backgroundColor: color,
      foregroundColor: Colors.white,
      child: Text(
        name.isEmpty ? '?' : name[0].toUpperCase(),
        style: TextStyle(fontSize: radius * .72, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 24, 20, 7),
    child: Text(
      text,
      style: const TextStyle(
        color: signalBlue,
        fontSize: 12,
        fontWeight: FontWeight.w700,
        letterSpacing: .5,
      ),
    ),
  );
}

class _SettingsTile extends StatelessWidget {
  const _SettingsTile({
    required this.icon,
    required this.title,
    required this.subtitle,
  });
  final IconData icon;
  final String title;
  final String subtitle;
  @override
  Widget build(BuildContext context) => ListTile(
    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 2),
    leading: Icon(icon),
    title: Text(title),
    subtitle: Text(subtitle),
  );
}

String _time(DateTime value) =>
    '${value.hour.toString().padLeft(2, '0')}:${value.minute.toString().padLeft(2, '0')}';

IconData _deliveryIcon(MessageDelivery delivery) => switch (delivery) {
  MessageDelivery.sending => Icons.schedule,
  MessageDelivery.sent => Icons.check,
  MessageDelivery.delivered => Icons.done_all,
  MessageDelivery.failed => Icons.error_outline,
  MessageDelivery.received => Icons.done,
};

int messageBytes(String text) => utf8.encode(text).length;
