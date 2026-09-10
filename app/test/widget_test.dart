import 'package:app/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows the messenger and phone-only discovery state', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(430, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(const RelayMeshApp());
    await tester.pumpAndSettle();

    expect(find.text('RelayMesh'), findsOneWidget);
    expect(find.text('No conversations yet'), findsOneWidget);

    await tester.tap(find.text('Find nearby devices'));
    await tester.pumpAndSettle();

    expect(find.text('Nearby devices'), findsOneWidget);
    expect(find.text('A physical phone is required'), findsOneWidget);
  });

  test('message size is measured in UTF-8 bytes', () {
    expect(messageBytes('hello'), 5);
    expect(messageBytes('₹'), 3);
  });
}
