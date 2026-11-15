import 'dart:io';

import 'package:drift/native.dart';
import 'package:fixflow_tech/core/api/api_client.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/core/providers.dart';
import 'package:fixflow_tech/features/outbox/outbox_providers.dart';
import 'package:fixflow_tech/features/outbox/outbox_repository.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/harness.dart';
import 'support/outbox_support.dart';

class _Sim extends SimulateOffline {
  @override
  bool build() => true;
}

Future<void> until(bool Function() cond) async {
  for (var i = 0; i < 100 && !cond(); i++) {
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
}

void main() {
  test(
    'SyncController: nothing is sent while simulated offline; the queue is '
    'delivered once when the switch goes online; SYNCING reset at start',
    () async {
      final db = AppDatabase(NativeDatabase.memory());
      addTearDown(db.close);
      await seedJob(db);
      final dir = Directory.systemTemp.createTempSync('ff_ctrl_');
      addTearDown(() => dir.deleteSync(recursive: true));
      final server = FakeServer();
      final container = ProviderContainer(
        overrides: [
          appDatabaseProvider.overrideWithValue(db),
          sessionProvider.overrideWith(() => FakeSession(technicianSession())),
          connectivityProvider.overrideWith((ref) => Stream.value(true)),
          simulateOfflineProvider.overrideWith(_Sim.new),
          outboxRootProvider.overrideWithValue(() async => dir),
          apiClientProvider.overrideWithValue(
            ApiClient(
              ApiClient.buildDio(
                baseUrl: 'http://fake',
                authContext: () => (token: 't', orgId: 'o1'),
                adapter: server.adapter,
              ),
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      final repo = container.read(outboxRepositoryProvider);
      final item = await repo.enqueueNote(
        orgId: 'o1',
        userId: 'u',
        requestId: 'r1',
        body: 'offline note',
        images: [PickedImage(path: writeImage(dir, 'p.png').path)],
      );
      await repo.markSyncing(item.commandId); // left over from a killed process

      container.read(syncControllerProvider); // app start
      await until(
        () => false == (container.read(syncControllerProvider).running),
      );
      await Future<void>.delayed(const Duration(milliseconds: 100));
      expect(server.allRequests, 0, reason: 'simulated offline sends nothing');
      final rows = await repo.all();
      expect(rows.single.status.name, 'pending'); // crash recovery

      container.read(simulateOfflineProvider.notifier).set(false);
      await until(() => server.notes.isNotEmpty);
      expect(server.notes.keys, [item.commandId]);
      await until(() => false);
      await Future<void>.delayed(const Duration(milliseconds: 100));
      expect(await repo.all(), isEmpty);
      expect(server.noteRequests, 1);
      expect(server.files.length, 1);
    },
  );
}
