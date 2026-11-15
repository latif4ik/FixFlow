import 'dart:async';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/providers.dart';
import '../jobs/jobs_providers.dart';
import 'outbox_models.dart';
import 'outbox_repository.dart';
import 'sync_engine.dart';

/// App documents directory resolver (tests override with a temp dir).
final outboxRootProvider = Provider<Future<Directory> Function()>(
  (ref) =>
      () async => getApplicationDocumentsDirectory(),
);

final outboxRepositoryProvider = Provider<OutboxRepository>(
  (ref) => OutboxRepository(
    ref.watch(appDatabaseProvider),
    ref.watch(outboxRootProvider),
  ),
);

final currentUserIdProvider = Provider<String?>(
  (ref) => ref.watch(sessionProvider.select((s) => s.user?.id)),
);

/// Queued notes of the signed-in user in the selected organization (all
/// statuses), oldest first.
final outboxItemsProvider = StreamProvider<List<OutboxItem>>((ref) {
  final org = ref.watch(selectedOrgIdProvider);
  final user = ref.watch(currentUserIdProvider);
  if (org == null || user == null) return Stream.value(const []);
  return ref.watch(outboxRepositoryProvider).watchFor(org, user);
});

/// Queued commands belonging to other users (shown as a count only).
final otherUsersOutboxCountProvider = StreamProvider<int>((ref) {
  final user = ref.watch(currentUserIdProvider);
  if (user == null) return Stream.value(0);
  return ref.watch(outboxRepositoryProvider).watchOtherUsersCount(user);
});

/// Items of one job (inline in the job's notes list).
final outboxForRequestProvider = Provider.family<List<OutboxItem>, String>(
  (ref, requestId) => [
    for (final i in ref.watch(outboxItemsProvider).asData?.value ?? const [])
      if (i.requestId == requestId) i,
  ],
);

/// Badge count for the inbox app bar.
final outboxBadgeCountProvider = Provider<int>(
  (ref) => ref.watch(outboxItemsProvider).asData?.value.length ?? 0,
);

/// Camera/gallery access, replaceable in tests.
abstract class PhotoPicker {
  Future<List<PickedImage>> fromCamera();
  Future<List<PickedImage>> fromGallery();
}

class ImagePickerPhotoPicker implements PhotoPicker {
  final _picker = ImagePicker();

  @override
  Future<List<PickedImage>> fromCamera() async {
    final f = await _picker.pickImage(source: ImageSource.camera);
    return f == null ? const [] : [PickedImage(path: f.path, name: f.name)];
  }

  @override
  Future<List<PickedImage>> fromGallery() async {
    final fs = await _picker.pickMultiImage(limit: OutboxRepository.maxPhotos);
    return [for (final f in fs) PickedImage(path: f.path, name: f.name)];
  }
}

final photoPickerProvider = Provider<PhotoPicker>(
  (ref) => ImagePickerPhotoPicker(),
);

/// Sync only needs the radio + the dev switch: NOT `networkReachableProvider`,
/// otherwise a failed attempt would block every later attempt.
bool canSyncNow(Ref ref) {
  if (ref.read(simulateOfflineProvider)) return false;
  return ref.read(connectivityProvider).asData?.value ?? true;
}

final syncEngineProvider = Provider<OutboxSyncEngine>(
  (ref) => OutboxSyncEngine(
    repo: ref.watch(outboxRepositoryProvider),
    api: ref.watch(apiClientProvider),
    canSync: () => canSyncNow(ref),
    userId: () => ref.read(currentUserIdProvider),
    orgId: () => ref.read(selectedOrgIdProvider),
  ),
);

/// How often queued items are retried while online (also the backoff check).
final syncIntervalProvider = Provider<Duration>(
  (ref) => const Duration(seconds: 30),
);

class SyncState {
  const SyncState({this.running = false, this.lastOutcome, this.lastRunAt});
  final bool running;
  final SyncOutcome? lastOutcome;
  final DateTime? lastRunAt;
}

/// Starts the sync engine: on app start, when connectivity returns, after a
/// sign-in / org switch, manually (Retry) and periodically while there is
/// queued work. Watch it once from the app root.
class SyncController extends Notifier<SyncState> {
  Timer? _timer;
  bool _started = false;

  @override
  SyncState build() {
    ref.onDispose(() => _timer?.cancel());
    // Back online (or the demo "Simulate offline" switched off).
    ref.listen(isOfflineProvider, (prev, next) {
      if (prev == true && next == false) syncNow();
    });
    ref.listen(simulateOfflineProvider, (prev, next) {
      if (prev == true && next == false) syncNow();
    });
    ref.listen(connectivityProvider, (prev, next) {
      if (next.asData?.value == true) syncNow();
    });
    // Sign-in / org switch.
    ref.listen(sessionProvider.select((s) => (s.user?.id, s.selectedOrgId)), (
      prev,
      next,
    ) {
      syncNow();
    });
    ref.listen(outboxItemsProvider, (prev, next) => _reschedule());
    // App start: crash recovery SYNCING -> PENDING, then a first run.
    Future<void>(() async {
      if (_started || !ref.mounted) return;
      _started = true;
      try {
        await ref.read(outboxRepositoryProvider).resetSyncing();
      } catch (_) {
        return;
      }
      if (ref.mounted) await syncNow();
    });
    return const SyncState();
  }

  /// Timer runs only while items wait and the radio is up.
  void _reschedule() {
    final waiting = (ref.read(outboxItemsProvider).asData?.value ?? const [])
        .any((i) => i.status == OutboxStatus.pending);
    if (!waiting) {
      _timer?.cancel();
      _timer = null;
      return;
    }
    _timer ??= Timer.periodic(ref.read(syncIntervalProvider), (_) {
      if (canSyncNow(ref)) syncNow(manual: false);
    });
  }

  /// [manual] ignores backoff timestamps (user pressed Retry).
  Future<SyncReport> syncNow({bool manual = true}) async {
    final engine = ref.read(syncEngineProvider);
    if (!ref.mounted) return const SyncReport(SyncOutcome.skipped);
    state = SyncState(running: true, lastRunAt: state.lastRunAt);
    final SyncReport report;
    try {
      report = await engine.runOnce(force: manual);
    } catch (_) {
      if (ref.mounted) {
        state = SyncState(running: engine.isRunning, lastRunAt: DateTime.now());
      }
      return const SyncReport(SyncOutcome.skipped);
    }
    if (!ref.mounted) return report;
    state = SyncState(
      running: engine.isRunning,
      lastOutcome: report.outcome,
      lastRunAt: DateTime.now(),
    );
    for (final id in report.syncedRequestIds) {
      ref.invalidate(jobDetailProvider(id));
    }
    return report;
  }
}

final syncControllerProvider = NotifierProvider<SyncController, SyncState>(
  SyncController.new,
);
