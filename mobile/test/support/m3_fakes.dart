import 'package:fixflow_tech/features/jobs/job_actions_repository.dart';
import 'package:fixflow_tech/features/notifications/notifications_repository.dart';
import 'package:fixflow_tech/features/profile/availability.dart';

/// Records calls; each method can be told to throw.
class FakeActionsRepository implements JobActionsRepository {
  final calls = <String>[];
  final uploads = <({String path, String commandId, int index})>[];
  final consumes = <({String commandId, String itemId, String quantity})>[];
  Object? error;

  /// When set, every call waits for it (to test in-flight states).
  Future<void>? gate;
  Object? uploadError;
  Object? completeError;
  Object? consumeError;
  List<InventoryItem> items = const [
    InventoryItem(
      id: 'i1',
      code: 'CABLE-2.5',
      name: 'Copper cable 2.5 mm2',
      unit: 'm',
      stock: '293.500',
    ),
    InventoryItem(
      id: 'i2',
      code: 'BREAKER-16A',
      name: 'Circuit breaker 16 A',
      unit: 'pcs',
      stock: '22.000',
    ),
  ];

  Future<void> _rec(String c, [Object? e]) async {
    calls.add(c);
    if (gate != null) await gate;
    final err = e ?? error;
    if (err != null) throw err;
  }

  @override
  Future<void> accept(String id) => _rec('accept');
  @override
  Future<void> decline(String id, String reason) => _rec('decline:$reason');
  @override
  Future<void> start(String id) => _rec('start');
  @override
  Future<void> block(String id, String reason) => _rec('block:$reason');
  @override
  Future<void> resume(String id, String note) => _rec('resume:$note');
  @override
  Future<void> complete(String id, String note) =>
      _rec('complete:$note', completeError);

  @override
  Future<String> uploadCompletionPhoto(
    String requestId, {
    required String path,
    required String commandId,
    required int index,
  }) async {
    uploads.add((path: path, commandId: commandId, index: index));
    calls.add('upload');
    if (uploadError != null) throw uploadError!;
    return 'file-${uploads.length}';
  }

  @override
  Future<List<InventoryItem>> inventory() async => items;

  @override
  Future<MaterialRecord> consumeMaterial(
    String requestId, {
    required String commandId,
    required String itemId,
    required String quantity,
  }) async {
    consumes.add((commandId: commandId, itemId: itemId, quantity: quantity));
    if (consumeError != null) throw consumeError!;
    return MaterialRecord(
      id: 'u1',
      code: 'CABLE-2.5',
      name: 'Copper cable 2.5 mm2',
      unit: 'm',
      quantity: quantity,
      clientCommandId: commandId,
    );
  }
}

class FakeNotificationsRepository implements NotificationsRepository {
  FakeNotificationsRepository([List<NotificationItem>? items])
    : items = items ?? [];
  List<NotificationItem> items;
  final marked = <String>[];
  int markAllCalls = 0;
  int unreadCalls = 0;

  @override
  Future<List<NotificationItem>> list({int pageSize = 50}) async =>
      List.of(items);

  @override
  Future<int> unreadCount() async {
    unreadCalls++;
    return items.where((i) => i.unread).length;
  }

  @override
  Future<NotificationItem> markRead(String id) async {
    marked.add(id);
    final i = items.indexWhere((n) => n.id == id);
    items[i] = items[i].asRead(DateTime.utc(2026, 11, 15, 10));
    return items[i];
  }

  @override
  Future<void> markAllRead() async {
    markAllCalls++;
    items = [for (final i in items) i.asRead(DateTime.utc(2026, 11, 15, 10))];
  }
}

NotificationItem notif(
  String id, {
  bool unread = true,
  String? requestId = 'r1',
  String type = 'ASSIGNMENT_CREATED',
  String title = 'New job assigned',
}) => NotificationItem(
  id: id,
  type: type,
  title: title,
  body: 'Body of $id',
  requestId: requestId,
  readAt: unread ? null : DateTime.utc(2026, 11, 14),
  createdAt: DateTime.utc(2026, 11, 15, 4),
);

class FakeTechnicianRepository implements TechnicianRepository {
  FakeTechnicianRepository(this.profile);
  final TechnicianProfile profile;
  @override
  Future<TechnicianProfile> me() async => profile;
}
